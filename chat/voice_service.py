# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/voice_service.py
"""
H37 (S138). Voice messages of the platform chat rooms: transcription
with Gemini.

---

H37 (S138). Mensajes de voz de las salas de chat: transcripción con
Gemini (`gemini-3.5-flash`, directriz 4.1). Valen igual los grabados
en la web de la sala que las notas de voz de WhatsApp. El texto sale
debajo del audio, en el push y por WhatsApp (para cuando hay ruido y
no se puede escuchar), y Alia lo entiende como si se hubiera escrito.
"""
import logging

from google.genai.types import (
    GenerateContentConfig,
    HttpOptions,
    Part,
    ThinkingConfig,
)

from ai_services.document_vision_service import _generate_content_with_retry
from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {
    "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a",
    "audio/mpeg": "mp3", "audio/aac": "aac", "audio/amr": "amr",
    "audio/x-m4a": "m4a", "audio/wav": "wav",
}
# Audio WhatsApp can play as media (webm is not one of them).
# Audio que WhatsApp reproduce como adjunto (webm no lo es).
WHATSAPP_AUDIO = (
    "audio/ogg", "audio/mpeg", "audio/mp4", "audio/aac", "audio/amr",
)
# Gemini name of each type (S138: mp4 from iPhone is read as m4a).
# Nombre para Gemini de cada tipo (el mp4 del iPhone se lee como m4a).
GEMINI_TYPES = {"audio/x-m4a": "audio/m4a", "audio/mp4": "audio/m4a"}
MAX_AUDIO_BYTES = 15 * 1024 * 1024
TIMEOUT_MS = 60_000
PROMPT = (
    "Transcribe literalmente en español este mensaje de voz de un "
    "trabajador de una empresa de grúas y asistencia en carretera. "
    "Devuelve solo el texto dicho, sin comillas ni comentarios. Si no "
    "se entiende nada, devuelve una cadena vacía."
)


def base_type(content_type):
    """
    MIME type without parameters ("audio/ogg; codecs=opus" -> ogg).

    ---

    Tipo MIME sin parámetros, en minúsculas.
    """
    return (content_type or "").split(";")[0].strip().lower()


def is_audio(content_type):
    """
    Whether a file is a voice message.

    ---

    Si un archivo es un mensaje de voz.
    """
    return base_type(content_type).startswith("audio/")


def transcribe(data, content_type):
    """
    Text of a voice message ("" if it cannot be read).

    ---

    Texto de un mensaje de voz, o "" si no se puede leer (el audio se
    publica igual, sin texto). Nunca lanza.
    """
    if not data or len(data) > MAX_AUDIO_BYTES:
        return ""
    mime = base_type(content_type)
    mime = GEMINI_TYPES.get(mime, mime)
    try:
        response = _generate_content_with_retry(
            get_gemini_client(),
            model=DEFAULT_MODEL,
            contents=[Part.from_bytes(data=data, mime_type=mime), PROMPT],
            config=GenerateContentConfig(
                http_options=HttpOptions(timeout=TIMEOUT_MS),
                thinking_config=ThinkingConfig(thinking_level="low"),
                temperature=0.0,
            ),
        )
    except Exception:  # noqa: BLE001 -- el audio sale sin texto
        logger.exception("# [CHAT VOZ] Transcripción fallida (%s).", mime)
        return ""
    text = (getattr(response, "text", "") or "").strip().strip('"')
    logger.info("# [CHAT VOZ] Transcrito (%s): %d caracteres.", mime,
                len(text))
    return text
