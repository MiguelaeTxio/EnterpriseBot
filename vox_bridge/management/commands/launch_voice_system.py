# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/management/commands/launch_voice_system.py
import os
import time
import subprocess
from django.core.management.base import BaseCommand
from django.conf import settings
from twilio.rest import Client

"""
EnterpriseBot Unified Voice Launcher: Orchestrates Ngrok, Sidecar and Twilio Outbound.
Resilience Patch: Separates Signaling (Django Web Node) from Media (Ngrok/Sidecar).
---
Lanzador Unificado de Voz de EnterpriseBot: Orquesta Ngrok, Sidecar y llamada de Twilio.
Parche de Resiliencia: Separa Señalización (Nodo Web Django) de Medios (Ngrok/Sidecar).
"""

class Command(BaseCommand):
    help = 'Lanza la infraestructura de voz y dispara la llamada de validación.'

    def handle(self, *args, **options):
        project_root = "/home/MiguelAeTxio/PROJECTS/EnterpriseBot"
        orchestrator_path = os.path.join(project_root, "voice_orchestrator.py")
        shared_url_file = os.path.join(project_root, "DOCS/SESSION/NGROK_URL.txt")
        log_file = "/home/MiguelAeTxio/SWAP/orchestrator_runtime.log"

        self.stdout.write(self.style.SUCCESS("# [INIT] Iniciando Sistema Unificado de Voz EnterpriseBot..."))

        # 1. LANZAMIENTO DE INFRAESTRUCTURA (NOHUP)
        self.stdout.write("# [1/3] Lanzando Orquestador Maestro en segundo plano...")
        try:
            with open(log_file, "w") as out:
                subprocess.Popen(
                    ["python3", "-u", orchestrator_path],
                    stdout=out,
                    stderr=out,
                    cwd=project_root,
                    start_new_session=True
                )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"# [CRITICAL] Fallo al lanzar el orquestador: {str(e)}"))
            return

        # 2. SLEEPER INTELIGENTE (POLLING)
        self.stdout.write("# [2/3] Esperando estabilización de túnel (Polling activo)...")
        public_url = None
        for i in range(25):
            if os.path.exists(shared_url_file):
                with open(shared_url_file, 'r') as f:
                    public_url = f.read().strip()
                    if public_url:
                        break
            time.sleep(1)
            if (i+1) % 5 == 0:
                self.stdout.write(f"# ... esperando conectividad ({i+1}s)")

        if not public_url:
            self.stdout.write(self.style.ERROR("# [ERROR] El túnel no levantó. Revisa: " + log_file))
            return

        self.stdout.write(self.style.SUCCESS(f"# [READY] Infraestructura lista en: {public_url}"))

        # 3. DISPARO DE LLAMADA TWILIO
        self.stdout.write("# [3/3] Disparando llamada de validación...")
        
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        api_key_sid = os.getenv('TWILIO_API_KEY_SID')
        api_key_secret = os.getenv('TWILIO_API_KEY_SECRET')
        from_number = os.getenv('TWILIO_PHONE_NUMBER')
        to_number = "+34688360595"
        
        # ✅ CRITICAL FIX: The webhook for the initial POST must be the Web Node (PythonAnywhere)
        # Twilio will receive the TwiML here, which then points to the Ngrok WSS URL.
        pa_domain = "MiguelAeTxio.pythonanywhere.com"
        webhook_url = f"https://{pa_domain}/vox/inbound/"

        try:
            client = Client(api_key_sid, api_key_secret, account_sid)
            call = client.calls.create(
                url=webhook_url,
                to=to_number,
                from_=from_number,
                method='POST'
            )
            self.stdout.write(self.style.SUCCESS(f"# [SUCCESS] Llamada en curso. CallSid: {call.sid}"))
            self.stdout.write(f"# Escucha el Bridge con: tail -f {log_file}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"# [ERROR TWILIO] {str(e)}"))
