"""
Controle do OBS Studio via obs-websocket (API v5) — usado pela aba
"Entrevista" para expor um arquivo de vídeo em loop como câmera virtual do
macOS, de forma que qualquer app (Chrome, Zoom, Meet, FaceTime...) possa
selecioná-la como se fosse uma webcam normal.

Por que controlar o OBS em vez de implementar uma câmera virtual própria:
desde o macOS 12.3, a Apple substituiu o mecanismo antigo de plugins DAL
(CoreMediaIO) — cada vez mais bloqueado em apps com sandbox, como o Chrome —
por "Camera Extensions": um tipo de extensão de sistema que precisa ser
desenvolvida nativamente (Swift/Xcode), assinada e, pra rodar fora da App
Store, notarizada com uma conta paga da Apple Developer Program (US$99/ano).
Isso é um projeto à parte, fora do stack Python deste app. O OBS Studio já
resolveu esse problema (a "OBS Virtual Camera", desde a v28, usa exatamente
esse mecanismo, já assinada/notarizada pela equipe do OBS) — então, em vez
de reimplementar, este módulo só controla um OBS já instalado e aberto:
cria/atualiza uma Fonte de Mídia com o vídeo escolhido (em loop contínuo) e
liga a câmera virtual do OBS.

Pré-requisitos (ver README, seção "Aba Entrevista"):
- OBS Studio instalado (`brew install --cask obs`) e **aberto** antes de usar
  esta aba (sem o OBS rodando, a conexão falha com "connection refused").
- Servidor WebSocket do OBS **habilitado manualmente** em Ferramentas >
  WebSocket Server Settings (vem **desligado** por padrão, mesmo em
  instalações novas da v28+) e a senha copiada de lá ("Show Connect Info")
  colada no campo "Senha do WebSocket:" desta aba — sem isso, a conexão
  falha com "authentication enabled but no password provided".
- Na primeira vez que a câmera virtual for iniciada, o macOS pede aprovação
  manual da extensão de sistema do OBS (Ajustes > Privacidade e Segurança)
  — isso só acontece uma vez por instalação do OBS.
"""

import logging

import obsws_python as obsws
from obsws_python.error import OBSSDKError

# O obsws_python loga internamente (via logging.exception) quando a conexão
# falha — como nós já convertemos isso numa mensagem amigável em
# OBSConnectionError, silenciamos esse logger pra não imprimir tracebacks
# assustadores no terminal por baixo da mensagem já tratada.
logging.getLogger('obsws_python').setLevel(logging.CRITICAL)

DEFAULT_HOST = 'localhost'
DEFAULT_PORT = 4455
CONNECT_TIMEOUT_S = 5

# Nomes fixos da cena/fonte que este módulo gerencia no OBS — reaproveitados
# (criados uma vez, depois só atualizados) a cada troca de vídeo, em vez de
# acumular cenas/fontes novas a cada uso.
SCENE_NAME = 'SpeakTranslate - Entrevista'
SOURCE_NAME = 'SpeakTranslate - Vídeo em loop'

# "ffmpeg_source" é o tipo interno (kind) da Fonte de Mídia do OBS — o mesmo
# em Windows/macOS/Linux, parte do plugin obs-ffmpeg do libobs.
MEDIA_SOURCE_KIND = 'ffmpeg_source'


class OBSConnectionError(RuntimeError):
    """Erro amigável pra mostrar na interface — já com mensagem pronta, sem
    o chamador precisar interpretar exceções internas do obsws_python."""


def connect(host=DEFAULT_HOST, port=DEFAULT_PORT, password='', timeout=CONNECT_TIMEOUT_S):
    """Conecta e autentica no servidor WebSocket do OBS. Levanta
    OBSConnectionError (com mensagem pronta pra UI) se o OBS não estiver
    aberto/acessível ou a senha estiver errada."""
    try:
        return obsws.ReqClient(host=host, port=port, password=password, timeout=timeout)
    except OBSSDKError as exc:
        raise OBSConnectionError(
            f'Falha ao autenticar no OBS — confira a senha do servidor WebSocket '
            f'(Ferramentas > WebSocket Server Settings no OBS). Detalhe: {exc}') from exc
    except Exception as exc:
        raise OBSConnectionError(
            'Não foi possível conectar ao OBS — verifique se ele está aberto, com o '
            'servidor WebSocket habilitado (Ferramentas > WebSocket Server Settings), '
            f'e se o host/porta estão corretos ({host}:{port}).') from exc


def _scene_exists(client, name):
    return any(scene['sceneName'] == name for scene in client.get_scene_list().scenes)


def _input_exists(client, name):
    return any(item['inputName'] == name for item in client.get_input_list().inputs)


def set_video_file(client, video_path, scene_name=SCENE_NAME, source_name=SOURCE_NAME):
    """
    Garante que existe, no OBS, uma cena com uma Fonte de Mídia apontando
    para `video_path` em loop contínuo, e deixa essa cena ativa no
    programa — cria a cena/fonte na primeira vez; nas vezes seguintes (ou
    ao trocar de vídeo) só atualiza o arquivo da fonte já existente, sem
    acumular cenas/fontes novas a cada uso.
    """
    settings = {
        'is_local_file': True,
        'local_file': video_path,
        'looping': True,
        'restart_on_activate': True,
    }

    if not _scene_exists(client, scene_name):
        client.create_scene(scene_name)

    if not _input_exists(client, source_name):
        # obsws_python (nesta versão) não tem um wrapper próprio pra
        # "CreateInput" — chamamos a requisição crua do protocolo v5
        # (client.send cobre qualquer request, documentado ou não).
        client.send('CreateInput', {
            'sceneName': scene_name,
            'inputName': source_name,
            'inputKind': MEDIA_SOURCE_KIND,
            'inputSettings': settings,
            'sceneItemEnabled': True,
        })
    else:
        client.set_input_settings(source_name, settings, True)

    client.set_current_program_scene(scene_name)


def start_virtual_cam(client):
    if not client.get_virtual_cam_status().output_active:
        client.start_virtual_cam()


def stop_virtual_cam(client):
    if client.get_virtual_cam_status().output_active:
        client.stop_virtual_cam()


def virtual_cam_active(client):
    return client.get_virtual_cam_status().output_active
