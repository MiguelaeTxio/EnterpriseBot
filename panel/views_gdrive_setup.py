# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_gdrive_setup.py
"""
One-time OAuth 2.0 authorization flow for Google Drive persistence
(S014-H10, see spare_parts/gdrive_service.py for the full design
rationale -- OAuth delegated to a human account, not a Service
Account, and why the root folder is created here instead of by a
human via the Drive UI).

Only ever run once per refresh token (a new run is only needed again
if Miguel Ángel revokes access or the token is otherwise invalidated
-- see gdrive_service.py docstring for the conditions). Gated to
ADMIN role -- this exposes a refresh token on screen once, equivalent
in sensitivity to any other credential in this project.

---

Flujo de autorización OAuth 2.0 de un solo uso para la persistencia en
Google Drive (S014-H10, ver spare_parts/gdrive_service.py para el
razonamiento completo del diseño -- OAuth delegado a una cuenta
humana, no un Service Account, y por qué la carpeta raíz se crea aquí
en vez de por un humano vía la interfaz de Drive).

Solo se ejecuta una vez por refresh token (solo hace falta repetirlo
si Miguel Ángel revoca el acceso o el token se invalida por otro
motivo -- ver el docstring de gdrive_service.py para las condiciones).
Restringido al rol ADMIN -- esto muestra un refresh token en pantalla
una vez, sensibilidad equivalente a cualquier otra credencial de este
proyecto.
"""
import os

from django.shortcuts import redirect, render
from django.views import View
from google_auth_oauthlib.flow import Flow

from panel.mixins import AdminRoleRequiredMixin
from spare_parts.gdrive_service import (
    SCOPES,
    TOKEN_URI,
    ensure_root_folder,
    get_drive_service,
)

# Debe coincidir EXACTAMENTE con el "Authorized redirect URI" configurado
# en el OAuth Client ID de Google Cloud Console -- cualquier diferencia
# (barra final, http vs https) produce redirect_uri_mismatch.
# ---
# Must match EXACTLY the "Authorized redirect URI" configured on the
# OAuth Client ID in Google Cloud Console -- any difference (trailing
# slash, http vs https) produces redirect_uri_mismatch.
REDIRECT_URI = (
    'https://enterprisebot-miguelaetxio.pythonanywhere.com'
    '/panel/gdrive/oauth-callback/'
)


def _build_flow() -> Flow:
    client_id = os.environ.get('GDRIVE_OAUTH_CLIENT_ID')
    client_secret = os.environ.get('GDRIVE_OAUTH_CLIENT_SECRET')
    client_config = {
        'web': {
            'client_id': client_id,
            'client_secret': client_secret,
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': TOKEN_URI,
            'redirect_uris': [REDIRECT_URI],
        }
    }
    return Flow.from_client_config(
        client_config, scopes=SCOPES, redirect_uri=REDIRECT_URI,
    )


class GDriveAuthorizeView(AdminRoleRequiredMixin, View):
    """
    Starts the one-time OAuth flow: redirects to Google's consent
    screen. access_type='offline' + prompt='consent' guarantee a
    refresh_token is issued even if this Google account already
    authorized this app before (Google only issues a refresh_token on
    the FIRST consent otherwise).
    ---
    Arranca el flujo OAuth de un solo uso: redirige a la pantalla de
    consentimiento de Google. access_type='offline' + prompt='consent'
    garantizan que se emita un refresh_token incluso si esta cuenta de
    Google ya autorizó esta app antes (si no, Google solo emite
    refresh_token en el PRIMER consentimiento).
    """

    def get(self, request):
        flow = _build_flow()
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            prompt='consent',
            include_granted_scopes='true',
        )
        return redirect(auth_url)


class GDriveOAuthCallbackView(AdminRoleRequiredMixin, View):
    """
    Handles Google's redirect back after consent: exchanges the
    authorization code for a refresh token, creates the root folder
    with that token (ensure_root_folder(), idempotent), and shows both
    on screen ONCE for Miguel Ángel to copy into .env
    (GDRIVE_OAUTH_REFRESH_TOKEN, GDRIVE_ROOT_FOLDER_ID) -- never
    persisted anywhere by this view, purely a one-time display.
    ---
    Gestiona la redirección de vuelta de Google tras el consentimiento:
    intercambia el código de autorización por un refresh token, crea la
    carpeta raíz con ese token (ensure_root_folder(), idempotente), y
    muestra ambos en pantalla UNA VEZ para que Miguel Ángel los copie a
    .env (GDRIVE_OAUTH_REFRESH_TOKEN, GDRIVE_ROOT_FOLDER_ID) -- esta
    vista no los persiste en ningún sitio, es solo una visualización de
    un solo uso.
    """

    def get(self, request):
        flow = _build_flow()
        flow.fetch_token(authorization_response=request.build_absolute_uri())
        refresh_token = flow.credentials.refresh_token

        drive_service = get_drive_service(refresh_token=refresh_token)
        root_folder_id = ensure_root_folder(drive_service)

        return render(request, 'panel/gdrive_setup_result.html', {
            'refresh_token': refresh_token,
            'root_folder_id': root_folder_id,
        })
