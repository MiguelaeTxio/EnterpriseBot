# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/trigger_outbound_call.py
import os
import sys
from twilio.rest import Client
from dotenv import load_dotenv

# ---
# OUTBOUND CALL TRIGGER: EnterpriseBot Validation (March 2026)
# Bypasses local carrier restrictions by initiating a call from Twilio to the user.
# ---
# DISPARADOR DE LLAMADA SALIENTE: Validación EnterpriseBot (Marzo 2026)
# Salta las restricciones del operador local iniciando una llamada desde Twilio al usuario.
# ---

def trigger_validation_call():
    """
    Uses the Twilio SDK to call the verified terminal and link it to the Django Webhook.
    ---
    Utiliza el SDK de Twilio para llamar al terminal verificado y enlazarlo con el Webhook de Django.
    """
    # 1. Load project environment / Cargar entorno del proyecto
    project_root = "/home/MiguelAeTxio/PROJECTS/EnterpriseBot"
    load_dotenv(os.path.join(project_root, ".env"))

    # 2. Extract Secrets / Extraer Secretos
    # We use API Key SID/Secret for better security audit
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    api_key_sid = os.getenv('TWILIO_API_KEY_SID')
    api_key_secret = os.getenv('TWILIO_API_KEY_SECRET')
    
    # Numbers / Números
    from_number = os.getenv('TWILIO_PHONE_NUMBER')  # +1 260 346 6780
    to_number = "+34688360595"  # Tu móvil verificado
    
    # Webhook landing point / Punto de llegada del Webhook
    webhook_url = "https://MiguelAeTxio.pythonanywhere.com/api/vox/inbound/"

    if not all([account_sid, api_key_sid, api_key_secret, from_number]):
        print("# [ERROR] Faltan credenciales de Twilio en el archivo .env")
        return

    try:
        # 3. Initialize Twilio Client / Inicializar Cliente Twilio
        client = Client(api_key_sid, api_key_secret, account_sid)

        print(f"# [INFO] Iniciando llamada desde {from_number} hacia {to_number}...")
        print(f"# [INFO] Twilio consultará: {webhook_url}")

        # 4. Create Call / Crear Llamada
        call = client.calls.create(
            url=webhook_url,
            to=to_number,
            from_=from_number,
            method='POST'
        )

        print(f"\n# ########################################################")
        print(f"# [SUCCESS] LLAMADA DISPARADA CON ÉXITO")
        print(f"# SID de Llamada: {call.sid}")
        print(f"# ESTADO: {call.status}")
        print(f"# Por favor, permanece atento a tu móvil +34 688 36 05 95")
        print(f"# ########################################################\n")

    except Exception as e:
        print(f"# [CRITICAL ERROR] Fallo al conectar con la API de Twilio: {str(e)}")

if __name__ == "__main__":
    # Ensure stdout flush for real-time visibility in PA
    trigger_validation_call()
    sys.stdout.flush()
