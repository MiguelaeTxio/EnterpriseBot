# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/management/commands/trigger_outbound_call.py
"""
Django management command to trigger an outbound validation call via Twilio.

Reads the active ngrok tunnel URL from DOCS/SESSION/NGROK_URL.txt and uses
it as the TwiML webhook for the outbound call. Falls back to the production
PythonAnywhere URL if no local tunnel is active.

Usage (from project root, inside EnterpriseBot_venv):
    python -m dotenv run python manage.py trigger_outbound_call
    python -m dotenv run python manage.py trigger_outbound_call --to +34XXXXXXXXX
---
Comando de gestión Django para disparar una llamada saliente de validación
vía Twilio.

Lee la URL activa del túnel ngrok desde DOCS/SESSION/NGROK_URL.txt y la usa
como webhook TwiML para la llamada saliente. Cae al fallback de la URL de
producción de PythonAnywhere si no hay ningún túnel local activo.

Uso (desde la raíz del proyecto, dentro de EnterpriseBot_venv):
    python -m dotenv run python manage.py trigger_outbound_call
    python -m dotenv run python manage.py trigger_outbound_call --to +34XXXXXXXXX
"""

import os

from django.core.management.base import BaseCommand, CommandError
from twilio.rest import Client as TwilioClient


# ---------------------------------------------------------------------------
# CONSTANTS / CONSTANTES
# ---------------------------------------------------------------------------

# Default destination number for outbound validation calls.
# Override with --to argument when invoking the command.
# Número de destino por defecto para llamadas de validación salientes.
# Sobreescribir con el argumento --to al invocar el comando.
DEFAULT_TO_NUMBER = "+34688360595"

# Production fallback webhook URL used when no local ngrok tunnel is active.
# URL de webhook de producción de fallback usada cuando no hay túnel ngrok local activo.
PRODUCTION_WEBHOOK_URL = (
    "https://enterprisebot-miguelaetxio.pythonanywhere.com/api/vox/inbound/"
)

# Path to the shared session file where voice_orchestrator.py writes the
# active ngrok HTTPS URL after successfully establishing the tunnel.
# Ruta al archivo de sesión compartido donde voice_orchestrator.py escribe
# la URL HTTPS activa de ngrok tras establecer el túnel correctamente.
NGROK_URL_FILE = (
    "/home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/SESSION/NGROK_URL.txt"
)


class Command(BaseCommand):
    """
    Triggers an outbound Twilio call to a target phone number, using the
    currently active ngrok tunnel as the TwiML webhook endpoint. If no
    local tunnel is detected, falls back to the production webhook URL.

    This command is intended for use during development and testing sessions
    to validate the full inbound call flow end-to-end without requiring a
    physical inbound call from an external phone.
    ---
    Dispara una llamada Twilio saliente a un número de teléfono objetivo,
    usando el túnel ngrok activo como endpoint de webhook TwiML. Si no se
    detecta ningún túnel local, cae al fallback de la URL de webhook de
    producción.

    Este comando está pensado para su uso durante sesiones de desarrollo y
    pruebas para validar el flujo completo de llamada entrante de extremo a
    extremo sin necesidad de una llamada entrante física desde un teléfono
    externo.
    """

    help = (
        "Dispara una llamada Twilio saliente de validación usando el túnel ngrok "
        "activo como webhook TwiML. Usar --to para especificar el número de destino."
    )

    def add_arguments(self, parser):
        """
        Registers optional command-line arguments for the command.
        ---
        Registra los argumentos de línea de comandos opcionales del comando.
        """
        parser.add_argument(
            "--to",
            type=str,
            default=DEFAULT_TO_NUMBER,
            help=(
                f"Número de teléfono de destino en formato E.164 "
                f"(por defecto: {DEFAULT_TO_NUMBER})."
            ),
        )

    def handle(self, *args, **options):
        """
        Entry point for the management command. Resolves the webhook URL,
        validates credentials, and triggers the outbound Twilio call.

        Raises CommandError on any unrecoverable failure.
        ---
        Punto de entrada del comando de gestión. Resuelve la URL del webhook,
        valida las credenciales y dispara la llamada Twilio saliente.

        Lanza CommandError ante cualquier fallo irrecuperable.
        """
        to_number = options["to"]

        # ------------------------------------------------------------------
        # STEP 1 — Validate required environment variables.
        # PASO 1 — Validar las variables de entorno requeridas.
        # ------------------------------------------------------------------
        required_env_vars = [
            "TWILIO_ACCOUNT_SID",
            "TWILIO_API_KEY_SID",
            "TWILIO_API_KEY_SECRET",
            "TWILIO_PHONE_NUMBER",
        ]
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            raise CommandError(
                f"Las siguientes variables de entorno son obligatorias y no están "
                f"definidas: {', '.join(missing_vars)}. "
                "Verifique el archivo .env del proyecto y ejecute con "
                "'python -m dotenv run python manage.py trigger_outbound_call'."
            )

        twilio_account_sid    = os.environ["TWILIO_ACCOUNT_SID"]
        twilio_api_key_sid    = os.environ["TWILIO_API_KEY_SID"]
        twilio_api_key_secret = os.environ["TWILIO_API_KEY_SECRET"]
        from_number           = os.environ["TWILIO_PHONE_NUMBER"]

        # ------------------------------------------------------------------
        # STEP 2 — Resolve the active webhook URL from the ngrok session file.
        # Falls back to the production URL if no local tunnel is active.
        # PASO 2 — Resolver la URL activa del webhook desde el archivo de sesión ngrok.
        # Cae al fallback de la URL de producción si no hay túnel local activo.
        # ------------------------------------------------------------------
        if os.path.exists(NGROK_URL_FILE):
            with open(NGROK_URL_FILE, "r", encoding="utf-8") as fh:
                raw_ngrok_url = fh.read().strip().rstrip("/")
            if raw_ngrok_url:
                webhook_url = f"{raw_ngrok_url}/api/vox/inbound/"
                self.stdout.write(
                    f"# [INFO] Usando túnel ngrok detectado: {webhook_url}"
                )
            else:
                webhook_url = PRODUCTION_WEBHOOK_URL
                self.stdout.write(
                    self.style.WARNING(
                        f"# [WARNING] Archivo de sesión ngrok vacío. "
                        f"Usando webhook de producción: {webhook_url}"
                    )
                )
        else:
            webhook_url = PRODUCTION_WEBHOOK_URL
            self.stdout.write(
                self.style.WARNING(
                    f"# [WARNING] No se detectó túnel local. "
                    f"Usando webhook de producción: {webhook_url}"
                )
            )

        # ------------------------------------------------------------------
        # STEP 3 — Instantiate the Twilio REST client using API Key credentials.
        # PASO 3 — Instanciar el cliente REST de Twilio usando API Key.
        # ------------------------------------------------------------------
        twilio_client = TwilioClient(
            twilio_api_key_sid,
            twilio_api_key_secret,
            twilio_account_sid,
        )
        self.stdout.write(
            f"# [INFO] Cliente Twilio instanciado. Cuenta: "
            f"{twilio_account_sid[:8]}...{twilio_account_sid[-4:]}"
        )

        # ------------------------------------------------------------------
        # STEP 4 — Trigger the outbound call.
        # PASO 4 — Disparar la llamada saliente.
        # ------------------------------------------------------------------
        self.stdout.write(
            f"# [AUDIT] Disparando llamada desde {from_number} a {to_number}..."
        )
        try:
            call = twilio_client.calls.create(
                url=webhook_url,
                to=to_number,
                from_=from_number,
                method="POST",
            )
        except Exception as exc:
            raise CommandError(
                f"Fallo en la API de Twilio al crear la llamada: "
                f"{type(exc).__name__}: {exc}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"# [SUCCESS] Llamada iniciada correctamente.\n"
                f"#           CallSid : {call.sid}\n"
                f"#           Desde   : {from_number}\n"
                f"#           Hacia   : {to_number}\n"
                f"#           Webhook : {webhook_url}"
            )
        )
