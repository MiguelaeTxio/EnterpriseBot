"""
Gemini operations of the demo agent on Vertex AI: client, speech
transcription, element location on screenshots and verification of
the composed mail before sending.

---

Operaciones Gemini del agente demo en Vertex AI: cliente,
transcripcion de voz, localizacion de elementos en capturas y
verificacion del correo redactado antes de enviarlo.
"""

import json
import os
from pathlib import Path

from common import DEFAULT_KEY_PATH
from common import GEMINI_LOCATION
from common import GEMINI_MODEL
from common import log

_BOX_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'found': {'type': 'BOOLEAN'},
        'label': {'type': 'STRING'},
        'box_2d': {'type': 'ARRAY', 'items': {'type': 'INTEGER'}},
    },
    'required': ['found'],
}

_VERIFY_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'to_ok': {'type': 'BOOLEAN'},
        'subject_ok': {'type': 'BOOLEAN'},
        'body_ok': {'type': 'BOOLEAN'},
        'notes': {'type': 'STRING'},
    },
    'required': ['to_ok', 'subject_ok', 'body_ok'],
}


def build_client():
    """
    Builds a Vertex AI Gemini client from the local service key.

    ---

    Construye un cliente Gemini de Vertex AI con la clave local.
    """
    from google import genai
    from google.genai import types

    key_path = Path(os.environ.get('H28_AGENT_KEY_PATH', DEFAULT_KEY_PATH))
    log('Clave de servicio: %s' % key_path)
    if not key_path.is_file():
        raise FileNotFoundError('no existe la clave %s' % key_path)
    with open(key_path, encoding='utf-8') as handle:
        key_data = json.load(handle)
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(key_path)
    log('Proyecto: %s | cuenta: %s' % (
        key_data.get('project_id'), key_data.get('client_email')))
    return genai.Client(
        vertexai=True,
        project=key_data.get('project_id'),
        location=GEMINI_LOCATION,
        http_options=types.HttpOptions(api_version='v1'),
    )


def transcribe(client, wav_path):
    """
    Transcribes a WAV recording with Gemini.

    ---

    Transcribe una grabacion WAV con Gemini.
    """
    from google.genai import types

    log('Transcribiendo con %s' % GEMINI_MODEL)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(
                data=Path(wav_path).read_bytes(), mime_type='audio/wav'),
            'Transcribe literalmente este audio en castellano, con '
            'puntuacion correcta. Devuelve solo el texto transcrito, sin '
            'comentarios. Si no se oye voz, devuelve exactamente: '
            '(sin voz)',
        ],
    )
    text = (response.text or '').strip()
    log('Transcripcion: "%s"' % text)
    return '' if text == '(sin voz)' else text


def locate(client, png_path, region, description):
    """
    Asks Gemini where a UI element is on a screenshot of a screen
    region and returns its centre in physical screen coordinates.

    ---

    Pregunta a Gemini donde esta un elemento en la captura de una
    region de pantalla y devuelve su centro en coordenadas fisicas.
    """
    from google.genai import types

    left, top, width, height = region
    log('Buscando con vision: %s' % description)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(
                data=Path(png_path).read_bytes(), mime_type='image/png'),
            'Esta es una captura de pantalla de Microsoft Outlook. '
            'Localiza: %s. Devuelve found, el texto visible del '
            'elemento en label (vacio si no tiene) y su caja en box_2d '
            'como [ymin, xmin, ymax, xmax] normalizada de 0 a 1000.'
            % description,
        ],
        config=types.GenerateContentConfig(
            response_mime_type='application/json',
            response_schema=_BOX_SCHEMA,
        ),
    )
    result = json.loads(response.text)
    log('  Gemini: %s' % json.dumps(result, ensure_ascii=False))
    box = result.get('box_2d') or []
    if not result.get('found') or len(box) != 4:
        return None
    return {
        'label': result.get('label', ''),
        'x': left + int((box[1] + box[3]) / 2 / 1000 * width),
        'y': top + int((box[0] + box[2]) / 2 / 1000 * height),
    }


def verify_compose(client, png_path, recipient, subject, body):
    """
    Asks Gemini whether the compose window shows the expected
    recipient, subject and body before pressing Send.

    ---

    Pregunta a Gemini si la ventana de redaccion muestra el
    destinatario, asunto y cuerpo esperados antes de pulsar Enviar.
    """
    from google.genai import types

    log('Verificando con vision el correo antes de enviarlo')
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(
                data=Path(png_path).read_bytes(), mime_type='image/png'),
            'Esta es una captura de una ventana de redaccion de correo de '
            'Microsoft Outlook. Comprueba: to_ok si el campo Para '
            'contiene %s (o un destinatario ya resuelto con esa '
            'direccion); subject_ok si el Asunto es exactamente "%s"; '
            'body_ok si el cuerpo contiene el texto "%s" por encima de '
            'la firma (la firma de correo debajo es normal y no cuenta '
            'como error). Explica en notes lo que no cuadre.'
            % (recipient, subject, body[:60]),
        ],
        config=types.GenerateContentConfig(
            response_mime_type='application/json',
            response_schema=_VERIFY_SCHEMA,
        ),
    )
    result = json.loads(response.text)
    log('  Gemini: %s' % json.dumps(result, ensure_ascii=False))
    return result
