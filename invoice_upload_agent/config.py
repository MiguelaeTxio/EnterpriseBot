# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/invoice_upload_agent/config.py
"""Settings of the supplier invoice upload agent (Ani's PC, S151).
---
Configuracion del agente de subida de facturas de proveedor (PC de
Ani, H28, S151, sesion invasora).

Agente analogo al H28 (Miguel Angel): vigila la carpeta que Ani le
indique y sube las facturas al cubo, a FACTURACION PROVEEDORES/
FACTURAS NUEVAS. Desde ahi el servidor las indexa, las procesa
(supplier_invoices) y las pasa a FACTURAS PROCESADAS.
"""
import os

# Cubo y carpeta de destino. Debe coincidir con
# supplier_invoices/invoice_service.py (NEW_FOLDER).
BUCKET_NAME = "cgs_grupo_alvarez"
UPLOAD_PREFIX = "FACTURACION PROVEEDORES/FACTURAS NUEVAS"

ALLOWED_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic")
TRANSIENT_PREFIXES = ("~$", ".~lock.", ".")
TRANSIENT_SUFFIXES = (".tmp", ".crdownload", ".partial")

# Cada cuanto se revisa la carpeta.
SCAN_INTERVAL_SECONDS = 60
HASH_CHUNK_SIZE_BYTES = 1024 * 1024

APP_NAME = "Agente de facturas"
DATA_DIR_NAME = os.path.join("EnterpriseBot", "AgenteFacturas")
KEY_FILE_NAME = "service_account_key.json"
KEY_PATH_ENV_VAR = "INVOICE_AGENT_KEY_PATH"
SETTINGS_FILE_NAME = "settings.json"
STATE_FILE_NAME = "uploaded.json"
LOG_FILE_NAME = "agente_facturas.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3


def get_data_dir():
    """Persistent data folder (LOCALAPPDATA), created if needed.
    ---
    Carpeta de datos persistente (LOCALAPPDATA), igual que el agente
    H28: no depende de donde se ejecute el .exe.
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
