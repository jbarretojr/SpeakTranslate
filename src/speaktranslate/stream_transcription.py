import logging
import os
import time
from pathlib import Path

import numpy as np

SENTENCE_END_CHARS = ('.', '!', '?', '…')

# Modo de diagnóstico: rode o app com SPEAKTRANSLATE_DEBUG=1 para registrar,
# a cada passagem, idioma detectado/confiança, palavras aceitas/descartadas e
# o que foi confirmado — e salvar o áudio capturado em .wav ao parar — em
# ~/.cache/speaktranslate/debug/. Útil para reproduzir offline um problema
# que só acontece com um áudio específico.
DEBUG_ENABLED = bool(os.environ.get('SPEAKTRANSLATE_DEBUG'))
DEBUG_DIR = Path.home() / '.cache' / 'speaktranslate' / 'debug'
_log = logging.getLogger('speaktranslate.stream')
if DEBUG_ENABLED:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    _handler = logging.FileHandler(DEBUG_DIR / 'transcription.log', encoding='utf-8')
    _handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    _log.addHandler(_handler)
    _log.setLevel(logging.DEBUG)


class LocalAgreementTranscriber:
    """
    Transcrição incremental para streaming, usando faster-whisper com a
    política LocalAgreement-2 (a mesma técnica usada pelo projeto
    whisper_streaming): a cada nova leva de áudio, re-transcreve toda a
    janela acumulada e só "comita" (confirma definitivamente) as palavras que
    permanecem idênticas entre duas passagens consecutivas. O restante fica
    "provisório" — pode ser mostrado, mas ainda pode mudar até a próxima
    passagem.

    Isso permite começar a mostrar texto em segundos, sem esperar uma pausa
    na fala de quem está falando.
    """

    def __init__(self, model, sample_rate=16000, language=None,
                 min_chunk_s=1.0, max_buffer_s=25.0, silence_gap_s=1.0,
                 min_word_probability=0.3, max_unpunctuated_words=20,
                 lang_lock_min_s=2.0, lang_lock_min_probability=0.5, lang_lock_fallback_s=3.5,
                 target_peak=0.5, max_gain=1000.0, min_peak_for_gain=4e-4):
        self.model = model
        # Normalização de volume: áudio capturado de um driver de loopback
        # (BlackHole) pode chegar dezenas de dB abaixo do normal, conforme o
        # volume do dispositivo/navegador. Nesse nível, o filtro de voz (VAD)
        # do whisper não reconhece fala em janelas curtas e o trecho é tratado
        # como silêncio. Por isso o buffer é amplificado até `target_peak`
        # antes de transcrever (limitado a `max_gain`); silêncio digital
        # (zeros) continua sendo silêncio.
        # Abaixo de `min_peak_for_gain` (~-68 dBFS) não amplifica: é ruído
        # de fundo, não fala, e amplificá-lo faz o whisper "alucinar" texto.
        self.target_peak = target_peak
        self.max_gain = max_gain
        self.min_peak_for_gain = min_peak_for_gain
        self.sample_rate = sample_rate
        self.language = language
        # Detecção automática (language=None): detectar o idioma de novo a
        # cada passagem, com só 1-2s de áudio, erra com frequência (quase
        # sempre para inglês) — e com o idioma errado o whisper "traduz" a
        # fala para inglês em vez de transcrevê-la, além de impedir a
        # concordância entre passagens. Por isso, dentro de uma frase, o
        # idioma é detectado só até haver áudio suficiente com confiança
        # (`lang_lock_min_s` / `lang_lock_min_probability`) e então fica
        # travado até a frase fechar; a próxima frase detecta de novo (a
        # conversa pode trocar de idioma). Antes de travar, nada é confirmado
        # pela via normal — só por pausa (frases curtinhas, ex.: "Sim.").
        # Com `lang_lock_fallback_s` de áudio, trava no idioma detectado
        # mesmo com confiança baixa: o modelo pode ficar dividido entre
        # idiomas próximos (ex.: português/espanhol/galego) indefinidamente,
        # e sem isso nada seria confirmado.
        self.lang_lock_min_s = lang_lock_min_s
        self.lang_lock_min_probability = lang_lock_min_probability
        self.lang_lock_fallback_s = lang_lock_fallback_s
        self._sentence_language = None
        self.min_chunk_s = min_chunk_s
        self.max_buffer_s = max_buffer_s
        # Segurança para fala contínua sem pontuação clara (o whisper às
        # vezes não pontua direito): se a frase pendente acumular esse tanto
        # de palavras sem fechar por pontuação nem por pausa, fecha assim
        # mesmo — evita esperar o corte de segurança de `max_buffer_s`
        # (bem mais lento) para dar algum retorno.
        self.max_unpunctuated_words = max_unpunctuated_words
        # O whisper pode "alucinar" palavras curtas (ex.: "Bye.", "Thank you.")
        # em trechos de silêncio/ruído, mesmo com vad_filter ativado — quase
        # sempre com probabilidade baixa. Descartamos palavras abaixo desse
        # limiar para não deixar esse tipo de lixo entrar na transcrição.
        self.min_word_probability = min_word_probability
        # Se o trecho de áudio depois da última palavra reconhecida (dentro
        # do próprio buffer, não relógio de parede) for maior que isso,
        # tratamos como pausa/fim de fala e forçamos a confirmação do que
        # sobrou. Medir pelo conteúdo do áudio (em vez de contar passagens ou
        # tempo de relógio) deixa isso imune tanto a oscilações do whisper
        # (uma palavra "piscando" entre passagens) quanto à variação de
        # quanto tempo cada passagem de re-transcrição demora.
        self.silence_gap_s = silence_gap_s

        self._audio = np.empty(0, dtype=np.float32)
        self._prev_words = []  # hipótese (lista de strings) da passagem anterior
        self._pending_sentence = ''  # palavras já comitadas, aguardando fim de frase p/ tradução
        self._last_committed_words = []  # últimas palavras comitadas, p/ deduplicar bordas de corte
        self._debug_audio = [] if DEBUG_ENABLED else None

    def feed(self, audio_int16):
        """Adiciona novo áudio (int16, mono) ao buffer de trabalho."""
        if audio_int16 is None or audio_int16.size == 0:
            return
        if self._debug_audio is not None:
            self._debug_audio.append(audio_int16.copy())
        self._audio = np.concatenate([self._audio, audio_int16.astype(np.float32) / 32768.0])

    def has_pending_audio(self):
        return self._audio.size >= int(self.min_chunk_s * self.sample_rate)

    def process(self):
        """
        Roda uma passagem de re-transcrição, se houver áudio suficiente
        acumulado. Retorna um dicionário:
          - 'committed': texto recém-confirmado nesta passagem (pode ser vazio)
          - 'preview': hipótese provisória atual (pode mudar na próxima passagem)
          - 'sentence': frase completa pronta para tradução, ou None
          - 'pending': frase ainda sendo formada (comitada, sem pontuação de fim)
          - 'language': idioma detectado nesta passagem
        """
        if not self.has_pending_audio():
            return {'committed': '', 'preview': '', 'sentence': None,
                    'pending': self._pending_sentence, 'language': self.language}

        buffer_duration = self._audio.size / self.sample_rate
        language = self.language or self._sentence_language

        audio = self._audio
        peak = float(np.abs(audio).max())
        gain = min(self.target_peak / peak, self.max_gain) if self.min_peak_for_gain <= peak < self.target_peak else 1.0
        if gain != 1.0:
            audio = audio * gain

        segments, info = self.model.transcribe(
            audio,
            language=language,
            word_timestamps=True,
            vad_filter=True,
            condition_on_previous_text=False,
            beam_size=1,
        )
        words = []
        dropped = []
        for segment in segments:
            for word in (segment.words or []):
                text = word.word.strip()
                if not text:
                    continue
                if word.probability >= self.min_word_probability:
                    words.append((text, word.start, word.end))
                else:
                    dropped.append(f'{text}({word.probability:.2f})')
        if DEBUG_ENABLED:
            _log.debug('buf=%.1fs gain=%.0fx forced_lang=%s detected=%s(%.2f) words=%s dropped=%s',
                       buffer_duration, gain, language, info.language, info.language_probability,
                       ' '.join(w[0] for w in words), ' '.join(dropped))

        # Silêncio depois da última palavra reconhecida (ou o buffer inteiro,
        # se nada foi reconhecido) — o sinal usado para detectar pausa/fim de
        # fala, ver `silence_gap_s` acima.
        trailing_silence = buffer_duration - (words[-1][2] if words else 0.0)

        if not words and dropped and self._audio.size < self.max_buffer_s * self.sample_rate:
            # Havia fala, mas todas as palavras ficaram abaixo do limiar de
            # confiança — típico do começo de uma frase, com pouco áudio ou
            # idioma ainda incerto. NÃO apaga o buffer (como no silêncio
            # abaixo): com mais áudio na próxima passagem o modelo costuma
            # acertar. Apagar aqui fazia o áudio nunca acumular o suficiente
            # e nada ser transcrito.
            self._prev_words = []
            sentence = None
            if self._pending_sentence and trailing_silence >= self.silence_gap_s:
                sentence = self._pending_sentence
                self._pending_sentence = ''
            return {'committed': '', 'preview': '', 'sentence': sentence,
                    'pending': self._pending_sentence, 'language': info.language}

        if not words:
            # Nada reconhecido no buffer inteiro (silêncio total). Não deixa
            # o buffer crescer sem limite esperando a próxima fala.
            self._audio = np.empty(0, dtype=np.float32)
            self._prev_words = []
            sentence = None
            if self._pending_sentence and trailing_silence >= self.silence_gap_s:
                sentence = self._pending_sentence
                self._pending_sentence = ''
            if not self._pending_sentence:
                self._sentence_language = None
            return {'committed': '', 'preview': '', 'sentence': sentence,
                    'pending': self._pending_sentence, 'language': info.language}

        language_locked = self.language is not None or self._sentence_language is not None
        if not language_locked and (
                (buffer_duration >= self.lang_lock_min_s
                 and info.language_probability >= self.lang_lock_min_probability)
                or buffer_duration >= self.lang_lock_fallback_s):
            self._sentence_language = info.language
            language_locked = True

        # Sem idioma travado, a hipótese ainda pode estar no idioma errado:
        # não confirma nada pela concordância normal (ver __init__).
        commit_len = self._agreement_length(words) if language_locked else 0
        forced = False

        # Pausa/fim de fala: sobrou silêncio real (medido no áudio) depois
        # da última palavra reconhecida — força a confirmação de tudo que
        # está pendente em vez de esperar o crescimento estável normal do
        # LocalAgreement (que só confirma quando a hipótese CRESCE).
        if commit_len == 0 and trailing_silence >= self.silence_gap_s:
            commit_len = len(words)
            forced = True

        # Corte de segurança: se o buffer ficou grande demais sem nenhum
        # ponto de concordância (ex.: fala contínua sem pausas por muito
        # tempo), força a confirmação de tudo transcrito até agora para não
        # deixar o custo de re-transcrição crescer sem limite.
        if commit_len == 0 and self._audio.size >= self.max_buffer_s * self.sample_rate:
            commit_len = len(words)
            forced = True

        committed_words = self._dedupe_boundary(words[:commit_len])
        committed_text = ' '.join(w[0] for w in committed_words)

        if words[:commit_len]:
            self._last_committed_words = [w[0] for w in words[:commit_len]][-3:]
            # Corta no início da próxima palavra ainda não confirmada (se
            # houver) em vez do fim da última confirmada, pra não deixar
            # sobras de áudio da palavra comitada no início do próximo
            # buffer (o que a faria ser "ouvida" de novo e duplicada).
            if commit_len < len(words):
                cut_time = words[commit_len][1]
            else:
                cut_time = words[commit_len - 1][2]
            cut_sample = int(cut_time * self.sample_rate)
            self._audio = self._audio[cut_sample:]
            self._prev_words = [w[0] for w in words[commit_len:]]
        else:
            self._prev_words = [w[0] for w in words]

        preview_text = ' '.join(w[0] for w in words[commit_len:])

        sentence = None
        if committed_text:
            self._pending_sentence = (self._pending_sentence + ' ' + committed_text).strip()

        too_long_unpunctuated = len(self._pending_sentence.split()) >= self.max_unpunctuated_words
        if self._pending_sentence and (
                forced or too_long_unpunctuated or self._pending_sentence.rstrip().endswith(SENTENCE_END_CHARS)):
            sentence = self._pending_sentence
            self._pending_sentence = ''

        result = {
            'committed': committed_text,
            'preview': preview_text,
            'sentence': sentence,
            'pending': self._pending_sentence,
            'language': info.language,
        }
        # Frase fechada e nada mais em andamento: a próxima frase detecta o
        # idioma de novo.
        if sentence and not self._prev_words:
            self._sentence_language = None
        return result

    def flush(self):
        """
        Força a finalização de qualquer frase pendente (ex.: ao parar a
        captura). Inclui também qualquer trecho ainda tentativo (que não
        teve tempo de ser confirmado pelo LocalAgreement nem pela detecção
        de silêncio) — ao parar, é melhor mostrar um texto possivelmente
        imperfeito do que perdê-lo silenciosamente.
        """
        self._save_debug_audio()
        if self._prev_words:
            tail = ' '.join(self._prev_words)
            self._pending_sentence = (self._pending_sentence + ' ' + tail).strip()
            self._prev_words = []
        sentence = self._pending_sentence.strip() or None
        self._pending_sentence = ''
        return sentence

    def _save_debug_audio(self):
        if not self._debug_audio:
            return
        import soundfile as sf
        path = DEBUG_DIR / f'capture-{time.strftime("%Y%m%d-%H%M%S")}.wav'
        sf.write(path, np.concatenate(self._debug_audio), self.sample_rate)
        _log.debug('áudio capturado salvo em %s', path)
        self._debug_audio = []

    def _dedupe_boundary(self, new_words):
        """
        Remove do início de `new_words` qualquer sobreposição com o final do
        que já foi comitado antes. Mitiga a duplicação de palavras que pode
        ocorrer na borda de corte do buffer (ex.: "...in in the 1950s"),
        uma limitação conhecida desse tipo de transcrição incremental.
        """
        if not self._last_committed_words or not new_words:
            return new_words

        def norm(token):
            return token.strip('.,!?…').lower()

        max_overlap = min(len(self._last_committed_words), len(new_words))
        for k in range(max_overlap, 0, -1):
            tail = [norm(t) for t in self._last_committed_words[-k:]]
            head = [norm(w[0]) for w in new_words[:k]]
            if tail == head:
                return new_words[k:]
        return new_words

    def _agreement_length(self, words):
        """
        Tamanho do maior prefixo comum entre a hipótese anterior e a atual.
        A última palavra "concordante" não é comitada (fica como margem de
        segurança, pois é a mais provável de ainda mudar com mais contexto).
        """
        agree_len = 0
        for (prev_text, (text, _start, _end)) in zip(self._prev_words, words):
            if prev_text != text:
                break
            agree_len += 1
        if agree_len == 0:
            return 0
        if agree_len == len(words) == len(self._prev_words):
            # hipótese não cresceu desde a última passagem (ex.: silêncio) —
            # não há nada de novo a confirmar ainda pela via normal (a
            # detecção de pausa por silêncio, acima, cuida de soltar isso).
            return 0
        return max(0, agree_len - 1)
