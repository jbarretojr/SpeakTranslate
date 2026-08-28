import numpy as np

SENTENCE_END_CHARS = ('.', '!', '?', '…')


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
                 min_chunk_s=1.0, max_buffer_s=25.0):
        self.model = model
        self.sample_rate = sample_rate
        self.language = language
        self.min_chunk_s = min_chunk_s
        self.max_buffer_s = max_buffer_s

        self._audio = np.empty(0, dtype=np.float32)
        self._prev_words = []  # hipótese (lista de strings) da passagem anterior
        self._pending_sentence = ''  # palavras já comitadas, aguardando fim de frase p/ tradução
        self._last_committed_words = []  # últimas palavras comitadas, p/ deduplicar bordas de corte

    def feed(self, audio_int16):
        """Adiciona novo áudio (int16, mono) ao buffer de trabalho."""
        if audio_int16 is None or audio_int16.size == 0:
            return
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
          - 'language': idioma detectado nesta passagem
        """
        if not self.has_pending_audio():
            return {'committed': '', 'preview': '', 'sentence': None, 'language': self.language}

        segments, info = self.model.transcribe(
            self._audio,
            language=self.language,
            word_timestamps=True,
            vad_filter=True,
            condition_on_previous_text=False,
            beam_size=1,
        )
        words = []
        for segment in segments:
            for word in (segment.words or []):
                text = word.word.strip()
                if text:
                    words.append((text, word.start, word.end))

        commit_len = self._agreement_length(words)

        # Corte de segurança: se o buffer ficou grande demais sem nenhum
        # ponto de concordância (ex.: fala contínua sem pausas por muito
        # tempo), força a confirmação de tudo transcrito até agora para não
        # deixar o custo de re-transcrição crescer sem limite.
        forced = False
        if commit_len == 0 and self._audio.size >= self.max_buffer_s * self.sample_rate and words:
            commit_len = len(words)
            forced = True

        committed_words = self._dedupe_boundary(words[:commit_len])
        committed_text = ' '.join(w[0] for w in committed_words)
        if words[:commit_len]:
            self._last_committed_words = [w[0] for w in words[:commit_len]][-3:]

        if words[:commit_len]:
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
            if forced or self._pending_sentence.rstrip().endswith(SENTENCE_END_CHARS):
                sentence = self._pending_sentence
                self._pending_sentence = ''

        return {
            'committed': committed_text,
            'preview': preview_text,
            'sentence': sentence,
            'language': info.language,
        }

    def flush(self):
        """Força a finalização de qualquer frase pendente (ex.: ao parar a captura)."""
        sentence = self._pending_sentence.strip() or None
        self._pending_sentence = ''
        return sentence

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
            # não há nada de novo a confirmar ainda.
            return 0
        return max(0, agree_len - 1)
