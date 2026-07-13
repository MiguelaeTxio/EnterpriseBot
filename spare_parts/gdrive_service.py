# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/spare_parts/gdrive_service.py
"""
Google Drive persistence for supplier delivery note photos/PDFs
(S014-H10). Replaces the email-based persistence
(spare_parts/tasks.py, up to S014).

---

## Why OAuth delegated to a user, NOT a Service Account

Verified online 2026-07-13 (Directriz 4.4/SINE QUA NON) against
Google's own documentation and multiple real-world reports of the
exact failure this avoids: a Service Account has NO storage quota of
its own outside a Google Workspace Shared Drive (confirmed empirically
by Google's own error response for a Service Account with an empty
Drive: `storageQuota: {limit: '0', usage: '0'}`). Grupo Álvarez's
Google account for this project (billing account "Grúas Álvarez",
GCP project `gen-lang-client-0961484137`, same one used for
Vertex AI/Gemini) is a **personal Google account, not a Google
Workspace** (confirmed by Miguel Ángel: only "Mi unidad" in the Drive
sidebar, no "Unidades compartidas") -- so a Service Account uploading
there would hit `storageQuotaExceeded` on the very first real file.

The correct mechanism for this exact scenario (Google's own
recommendation): OAuth 2.0 authorization delegated to the human
account, so uploaded files are owned by that account and count
against its own storage (100GB plan, per Miguel Ángel), not against
any Service Account quota.

## Why `drive.file` scope, and why the root folder is created by the
## OAuth callback itself, never by a human via the Drive UI

`drive.file` (least-privilege scope, vs. the full `drive` scope) only
grants the app access to files/folders **it created itself** via the
API. A folder created manually by a human in the Drive UI would be
invisible to the app under this scope. So the one-time authorization
flow (panel/views_gdrive_setup.py) creates the root folder itself,
right after obtaining the token -- see `ensure_root_folder()` below,
called once from that view. Never grant the broader `drive` scope to
work around this; create the folder via the API instead.

## Why the OAuth consent screen MUST be "In production", not "Testing"

Verified online 2026-07-13: an OAuth consent screen left in "Testing"
publishing status issues refresh tokens that expire in exactly 7 days,
regardless of use -- confirmed by Google's own support documentation.
For a personal-use app with a single authorizing account (this one),
switching Publishing status to "In production" in Google Cloud Console
removes that 7-day expiry WITHOUT requiring Google's formal
verification process (that's only mandatory past ~100 users or for
sensitive/restricted-scope apps at scale) -- the only visible
consequence is an "unverified app" interstitial screen during the
one-time authorization, which Miguel Ángel clicks through once.

---

## Env vars required (set directly in .env on the server, never in code)

- `GDRIVE_OAUTH_CLIENT_ID` / `GDRIVE_OAUTH_CLIENT_SECRET`: from the
  OAuth 2.0 Client ID (type "Web application") created in the same GCP
  project as Vertex AI. Authorized redirect URI must be exactly
  `https://enterprisebot-miguelaetxio.pythonanywhere.com/panel/gdrive/oauth-callback/`.
- `GDRIVE_OAUTH_REFRESH_TOKEN`: obtained once from the one-time
  authorization flow (panel/views_gdrive_setup.py) -- never expires
  under normal use once the consent screen is "In production" (Google
  docs: 6 months of total inactivity, explicit revocation, or a
  100-live-token-per-client cap are the only other expiry conditions,
  none of which apply to a single actively-used integration).
- `GDRIVE_ROOT_FOLDER_ID`: the id of the "EnterpriseBot - Albaranes"
  root folder, created automatically by the one-time authorization
  flow and shown on screen once for Miguel Ángel to copy.
"""
import io
import logging
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger(__name__)

# Least-privilege scope -- see module docstring. Must match exactly
# the scope requested during the one-time authorization
# (views_gdrive_setup.py) -- OAuth 2.0 credentials cannot request
# additional scopes after authorization without a brand new consent.
SCOPES = ['https://www.googleapis.com/auth/drive.file']

TOKEN_URI = 'https://oauth2.googleapis.com/token'

ROOT_FOLDER_NAME = 'EnterpriseBot - Albaranes'

_MIME_TYPES = {
    '.pdf': 'application/pdf',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
}

_FOLDER_MIME_TYPE = 'application/vnd.google-apps.folder'


class GDriveNotConfigured(Exception):
    """
    Raised when the required env vars for Drive access are missing --
    distinct from a real API failure, so callers (the Celery task) can
    tell "not set up yet" apart from "Google returned an error" in
    logs.
    ---
    Se lanza cuando faltan las variables de entorno necesarias para
    acceder a Drive -- distinto de un fallo real de la API, para que
    quien la llame (la tarea Celery) pueda distinguir en los logs "aún
    no configurado" de "Google devolvió un error".
    """


def _get_credentials(refresh_token: str | None = None) -> Credentials:
    """
    Builds OAuth 2.0 Credentials from the client id/secret env vars
    plus a refresh token. If refresh_token is not given, reads it from
    GDRIVE_OAUTH_REFRESH_TOKEN (the normal case, every call after the
    one-time authorization). The one-time authorization callback
    (views_gdrive_setup.py) passes the freshly-obtained refresh_token
    explicitly instead, since it isn't in the env yet at that point.

    ---

    Construye Credentials OAuth 2.0 a partir de las variables de
    entorno client id/secret más un refresh token. Si no se pasa
    refresh_token, lo lee de GDRIVE_OAUTH_REFRESH_TOKEN (el caso
    normal, cada llamada tras la autorización de un solo uso). El
    callback de autorización de un solo uso (views_gdrive_setup.py)
    pasa el refresh_token recién obtenido explícitamente en su lugar,
    ya que todavía no está en el entorno en ese momento.
    """
    client_id = os.environ.get('GDRIVE_OAUTH_CLIENT_ID')
    client_secret = os.environ.get('GDRIVE_OAUTH_CLIENT_SECRET')
    refresh_token = refresh_token or os.environ.get('GDRIVE_OAUTH_REFRESH_TOKEN')

    if not client_id or not client_secret or not refresh_token:
        raise GDriveNotConfigured(
            'Faltan GDRIVE_OAUTH_CLIENT_ID / GDRIVE_OAUTH_CLIENT_SECRET '
            '/ GDRIVE_OAUTH_REFRESH_TOKEN en el entorno -- completar el '
            'flujo de autorización de un solo uso en '
            '/panel/gdrive/authorize/ primero.'
        )

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def get_drive_service(refresh_token: str | None = None):
    """
    Returns an authenticated googleapiclient Drive v3 service object.
    ---
    Devuelve un objeto de servicio Drive v3 de googleapiclient ya
    autenticado.
    """
    creds = _get_credentials(refresh_token=refresh_token)
    return build('drive', 'v3', credentials=creds, cache_discovery=False)


def ensure_root_folder(drive_service) -> str:
    """
    Finds the root folder by name, creating it if it doesn't exist yet
    (idempotent -- safe to call every time, e.g. from the one-time
    authorization view). Returns its Drive file id.

    ---

    Busca la carpeta raíz por nombre, creándola si todavía no existe
    (idempotente -- seguro llamarlo siempre, p. ej. desde la vista de
    autorización de un solo uso). Devuelve su id de Drive.
    """
    query = (
        f"name='{ROOT_FOLDER_NAME}' and mimeType='{_FOLDER_MIME_TYPE}' "
        f"and 'root' in parents and trashed=false"
    )
    results = drive_service.files().list(
        q=query, spaces='drive', fields='files(id, name)',
    ).execute()
    matches = results.get('files', [])
    if matches:
        return matches[0]['id']

    folder = drive_service.files().create(
        body={'name': ROOT_FOLDER_NAME, 'mimeType': _FOLDER_MIME_TYPE},
        fields='id',
    ).execute()
    logger.info(
        '# [gdrive_service] Carpeta raíz "%s" creada (id=%s).',
        ROOT_FOLDER_NAME, folder['id'],
    )
    return folder['id']


def _ensure_month_folder(drive_service, root_folder_id: str, year_month: str) -> str:
    """
    Finds or creates the 'YYYY-MM' subfolder under the root folder for
    the given month -- one subfolder per year-month, per Miguel Ángel
    (S014).
    ---
    Busca o crea la subcarpeta 'AAAA-MM' bajo la carpeta raíz para el
    mes dado -- una subcarpeta por año-mes, según Miguel Ángel (S014).
    """
    query = (
        f"name='{year_month}' and mimeType='{_FOLDER_MIME_TYPE}' "
        f"and '{root_folder_id}' in parents and trashed=false"
    )
    results = drive_service.files().list(
        q=query, spaces='drive', fields='files(id, name)',
    ).execute()
    matches = results.get('files', [])
    if matches:
        return matches[0]['id']

    folder = drive_service.files().create(
        body={
            'name': year_month,
            'mimeType': _FOLDER_MIME_TYPE,
            'parents': [root_folder_id],
        },
        fields='id',
    ).execute()
    return folder['id']


def upload_delivery_note_file(delivery_note) -> dict:
    """
    Uploads delivery_note's source file (image or pdf_file) to the
    'YYYY-MM' subfolder (by delivery_note.created_at) under the root
    folder, sharing it as "anyone with the link can view" (S014,
    Miguel Ángel: same read access anyone already has who can see the
    delivery notes list -- no extra restriction).

    Does NOT delete the local file or touch the DeliveryNote model --
    that's the caller's job (spare_parts/tasks.py), same separation of
    concerns the email flow already had.

    Returns {'file_id': ..., 'web_link': ...}.

    ---

    Sube el archivo origen (image o pdf_file) de delivery_note a la
    subcarpeta 'AAAA-MM' (según delivery_note.created_at) bajo la
    carpeta raíz, compartido como "cualquiera con el enlace puede ver"
    (S014, Miguel Ángel: mismo acceso de lectura que ya tiene cualquiera
    que vea el listado de albaranes -- sin restricción adicional).

    NO borra el archivo local ni toca el modelo DeliveryNote -- eso es
    responsabilidad de quien llama (spare_parts/tasks.py), misma
    separación de responsabilidades que ya tenía el flujo de correo.

    Devuelve {'file_id': ..., 'web_link': ...}.
    """
    root_folder_id = os.environ.get('GDRIVE_ROOT_FOLDER_ID')
    if not root_folder_id:
        raise GDriveNotConfigured(
            'Falta GDRIVE_ROOT_FOLDER_ID en el entorno -- completar el '
            'flujo de autorización de un solo uso en '
            '/panel/gdrive/authorize/ primero.'
        )

    file_field = delivery_note.image or delivery_note.pdf_file
    if not file_field:
        raise ValueError(
            f'Albarán #{delivery_note.pk} sin archivo asociado -- '
            f'nada que subir.'
        )

    file_path = file_field.path
    file_name = os.path.basename(file_path)
    extension = os.path.splitext(file_name)[1].lower()
    mime_type = _MIME_TYPES.get(extension, 'application/octet-stream')

    drive_service = get_drive_service()
    year_month = delivery_note.created_at.strftime('%Y-%m')
    month_folder_id = _ensure_month_folder(drive_service, root_folder_id, year_month)

    drive_file_name = (
        f'{delivery_note.delivery_number or delivery_note.pk}_{file_name}'
    )
    with open(file_path, 'rb') as f:
        media = MediaIoBaseUpload(
            io.BytesIO(f.read()), mimetype=mime_type, resumable=True,
        )
    uploaded = drive_service.files().create(
        body={'name': drive_file_name, 'parents': [month_folder_id]},
        media_body=media,
        fields='id, webViewLink',
    ).execute()

    # "Cualquiera con el enlace puede ver" -- confirmado por Miguel
    # Ángel (S014): mismo acceso que ya tiene cualquiera que vea el
    # listado de albaranes, sin restricción adicional.
    drive_service.permissions().create(
        fileId=uploaded['id'],
        body={'type': 'anyone', 'role': 'reader'},
    ).execute()

    logger.info(
        '# [gdrive_service] Albarán #%d subido a Drive (file_id=%s, '
        'carpeta %s).',
        delivery_note.pk, uploaded['id'], year_month,
    )
    return {'file_id': uploaded['id'], 'web_link': uploaded['webViewLink']}
