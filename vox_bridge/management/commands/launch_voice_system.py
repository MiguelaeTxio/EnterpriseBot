# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/management/commands/launch_voice_system.py
import os
import time
import subprocess
from django.core.management.base import BaseCommand
from django.conf import settings
from twilio.rest import Client

"""
EnterpriseBot Unified Voice Launcher: Orchestrates Ngrok, Sidecar and Tunneling.
Webhook Fix: Corrected URL path to include /api/ prefix (April 2026).
---
Lanzador Unificado de Voz de EnterpriseBot: Orquesta Ngrok, Sidecar y Tunelización.
Corrección de Webhook: Ruta ajustada para incluir el prefijo /api/ (Abril 2026).
"""

class Command(BaseCommand):
    """
    Management command to launch the voice infrastructure and trigger the validation call.
    ---
    Comando de gestión para lanzar la infraestructura de voz y disparar la llamada.
    """
    help = 'Lanza la infraestructura de voz y dispara la llamada de validación con el hostname correcto.'

    def handle(self, *args, **options):
        project_root = "/home/MiguelAeTxio/PROJECTS/EnterpriseBot"
        orchestrator_path = os.path.join(project_root, "voice_orchestrator.py")
        shared_url_file = os.path.join(project_root, "DOCS/SESSION/NGROK_URL.txt")
        log_file = "/home/MiguelAeTxio/SWAP/orchestrator_runtime.log"

        self.stdout.write(self.style.SUCCESS("# [INIT] Iniciando Sistema EnterpriseBot (Sincronización de Hostname)..."))

        # 1. LANZAMIENTO DE INFRAESTRUCTURA
        self.stdout.write("# [1/3] Lanzando Orquestador Maestro...")
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
        self.stdout.write("# [2/3] Esperando estabilización de túnel...")
        public_url = None
        for i in range(25):
            if os.path.exists(shared_url_file):
                with open(shared_url_file, 'r') as f:
                    public_url = f.read().strip()
                    if public_url:
                        break
            time.sleep(1)

        if not public_url:
            self.stdout.write(self.style.ERROR("# [ERROR] El túnel no levantó. Revisa logs en SWAP."))
            return

        self.stdout.write(self.style.SUCCESS(f"# [READY] Túnel activo en: {public_url}"))

        # 3. DISPARO DE LLAMADA TWILIO (WEBHOOK DE PRODUCCIÓN)
        self.stdout.write("# [3/3] Disparando llamada de validación a +34688360595...")
        
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        api_key_sid = os.getenv('TWILIO_API_KEY_SID')
        api_key_secret = os.getenv('TWILIO_API_KEY_SECRET')
        from_number = os.getenv('TWILIO_PHONE_NUMBER')
        to_number = "+34688360595"
        
        # ✅ APRIL 2026 FIX: Corrected path with /api/ prefix
        pa_domain = "enterprisebot-MiguelAeTxio.pythonanywhere.com"
        webhook_url = f"https://{pa_domain}/api/vox/inbound/"

        try:
            client = Client(api_key_sid, api_key_secret, account_sid)
            call = client.calls.create(
                url=webhook_url,
                to=to_number,
                from_=from_number,
                method='POST'
            )
            self.stdout.write(self.style.SUCCESS(f"# [SUCCESS] Llamada disparada. Webhook: {webhook_url}"))
            self.stdout.write(f"# Auditoría: tail -f {log_file}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"# [ERROR TWILIO] {str(e)}"))
