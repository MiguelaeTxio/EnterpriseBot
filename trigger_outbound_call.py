# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/trigger_outbound_call.py
import os
import sys
from twilio.rest import Client
from dotenv import load_dotenv

"""
EnterpriseBot Outbound Call Trigger: Dynamic URL Resolution for Ngrok.
Refactored to read the active tunnel URL from NGROK_URL.txt.
---
Disparador de Llamadas Salientes de EnterpriseBot: Resolución Dinámica de URL para Ngrok.
Refactorizado para leer la URL activa del túnel desde NGROK_URL.txt.
"""

def trigger_validation_call():
    project_root = "/home/MiguelAeTxio/PROJECTS/EnterpriseBot"
    load_dotenv(os.path.join(project_root, ".env"))

    # Credential Resolution / Resolución de Credenciales
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    api_key_sid = os.getenv('TWILIO_API_KEY_SID')
    api_key_secret = os.getenv('TWILIO_API_KEY_SECRET')
    from_number = os.getenv('TWILIO_PHONE_NUMBER')
    to_number = "+34688360595"
    
    # ✅ DYNAMIC URL RESOLUTION / RESOLUCIÓN DINÁMICA DE URL
    # Prioritizes the local ngrok tunnel for field testing (Milestone 1).
    shared_url_file = os.path.join(project_root, "DOCS/SESSION/NGROK_URL.txt")
    
    if os.path.exists(shared_url_file):
        with open(shared_url_file, 'r') as f:
            public_url = f.read().strip()
        # The path corresponds to the voice stream entry point
        webhook_url = f"{public_url}/api/vox/inbound/"
        print(f"# [INFO] Usando túnel NGROK detectado: {webhook_url}")
    else:
        # Fallback to production if no tunnel is active
        webhook_url = "https://enterprisebot-miguelaetxio.pythonanywhere.com/api/vox/inbound/"
        print(f"# [WARNING] No se detectó túnel local. Usando Webhook de PRODUCCIÓN: {webhook_url}")

    try:
        client = Client(api_key_sid, api_key_secret, account_sid)
        print(f"# [AUDIT] Disparando llamada a {to_number}...")
        call = client.calls.create(
            url=webhook_url,
            to=to_number,
            from_=from_number,
            method='POST'
        )
        print(f"# [SUCCESS] Llamada iniciada con éxito.")
        print(f"# [SUCCESS] CallSid: {call.sid}")
    except Exception as e:
        print(f"# [ERROR FATAL] Fallo en la API de Twilio: {str(e)}")

if __name__ == "__main__":
    trigger_validation_call()
