# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/mail_reader_agent/config.py
"""Settings of the Outlook mail reader agent (Yolanda's PC, S156).
---
Configuracion del agente lector de correos de Outlook (PC de Yolanda,
H31, S156). Lee la carpeta de Outlook elegida sin marcar nada como
leido ni mover nada, y sube cada correo nuevo (texto y adjuntos) al
cubo, a CORREOS DOCUMENTACION/NUEVOS, para que el servidor lo procese.
"""
import os

BUCKET_NAME = "cgs_grupo_alvarez"
UPLOAD_PREFIX = "CORREOS DOCUMENTACION/NUEVOS"
# Ficha del correo; se sube la ultima, cuando ya estan los adjuntos:
# su presencia en el cubo marca el correo como completo.
MAIL_JSON_NAME = "correo.json"

# Cada cuanto se revisa la carpeta y hasta cuantos dias atras se mira.
SCAN_INTERVAL_SECONDS = 60
LOOKBACK_DAYS = 7
# Lo ya subido se olvida pasado este plazo (el estado no crece sin fin).
STATE_RETENTION_DAYS = 30
# Limite de texto del cuerpo que va en la ficha.
MAX_BODY_CHARS = 200000

# Clases de elemento de Outlook (OlObjectClass) y adjuntos.
OL_MAIL_ITEM = 43
PR_INTERNET_MESSAGE_ID = (
    "http://schemas.microsoft.com/mapi/proptag/0x1035001F"
)
PR_ATTACHMENT_HIDDEN = (
    "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"
)
PR_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x39FE001F"

APP_NAME = "Agente de correos"
DATA_DIR_NAME = os.path.join("EnterpriseBot", "AgenteCorreos")
KEY_FILE_NAME = "service_account_key.json"
KEY_PATH_ENV_VAR = "MAIL_AGENT_KEY_PATH"
SETTINGS_FILE_NAME = "settings.json"
STATE_FILE_NAME = "uploaded.json"
LOG_FILE_NAME = "agente_correos.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3


def get_data_dir():
    """Persistent data folder (LOCALAPPDATA), created if needed.
    ---
    Carpeta de datos persistente (LOCALAPPDATA), como los demas
    agentes: no depende de donde se ejecute el .exe.
    """
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, DATA_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def get_key_path():
    """Service account key: env var, else the data folder.
    ---
    Clave de la cuenta de servicio: la variable de entorno si esta
    fijada; si no, `service_account_key.json` en la carpeta de datos.
    """
    return os.environ.get(KEY_PATH_ENV_VAR) or os.path.join(
        get_data_dir(), KEY_FILE_NAME,
    )
