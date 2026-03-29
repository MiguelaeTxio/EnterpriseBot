# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/voice_orchestrator.py
import os
import subprocess
import time
import requests
import sys
import signal
from dotenv import load_dotenv

# Forzar salida inmediata para visibilidad total en Dashboard
os.environ["PYTHONUNBUFFERED"] = "1"

class VoiceOrchestrator:
    def __init__(self):
        self.project_root = "/home/MiguelAeTxio/PROJECTS/EnterpriseBot"
        self.ngrok_bin = os.path.join(self.project_root, "ngrok")
        self.config_path = os.path.join(self.project_root, "ngrok.yml")
        self.bridge_script = os.path.join(self.project_root, "voice_sidecar_bridge.py")
        self.python_bin = sys.executable
        
        # Carga explícita del entorno .env
        load_dotenv(os.path.join(self.project_root, ".env"))

    def flush_print(self, message):
        print(message, flush=True)

    def start_ngrok(self):
        self.flush_print("# [ORCHESTRATOR] Iniciando túnel ngrok v3 con inyección de Token por CLI...")
        
        # Extraer token del entorno para inyectarlo directamente
        token = os.getenv('NGROK_AUTHTOKEN')
        if not token:
            self.flush_print("# [ERROR] Variable NGROK_AUTHTOKEN no encontrada en el entorno.")
            return False

        if not os.path.exists(self.ngrok_bin):
            self.flush_print("# [ERROR] Binario ngrok no encontrado.")
            return False

        # Inyectamos el token vía --authtoken para evitar fallos de expansión en YAML
        cmd = [
            self.ngrok_bin, "start", 
            "--authtoken", token,
            "--config", self.config_path, 
            "enterprise_voice_bridge"
        ]
        
        # Redirección directa a la consola (Dashboard)
        self.ngrok_process = subprocess.Popen(
            cmd, 
            stdout=sys.stdout, 
            stderr=sys.stderr, 
            env=os.environ,
            text=True
        )
        
        time.sleep(5)
        return True

    def get_public_url(self):
        try:
            response = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=2)
            tunnels = response.json().get('tunnels', [])
            if tunnels:
                url = tunnels[0].get('public_url')
                self.flush_print(f"\n# ########################################################")
                self.flush_print(f"# [SUCCESS] CONECTIVIDAD ESTABLECIDA")
                self.flush_print(f"# URL PÚBLICA: {url}")
                self.flush_print(f"# ########################################################\n")
                return url
        except Exception:
            pass
        return None

    def start_bridge(self):
        self.flush_print("# [ORCHESTRATOR] Lanzando Voice Sidecar Bridge...")
        self.bridge_process = subprocess.Popen(
            [self.python_bin, "-u", self.bridge_script], 
            stdout=sys.stdout,
            stderr=sys.stderr,
            env=os.environ
        )

    def run(self):
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)

        if not self.start_ngrok(): return

        for _ in range(5):
            if self.get_public_url(): break
            time.sleep(2)

        self.start_bridge()

        try:
            while True:
                if self.ngrok_process.poll() is not None:
                    self.flush_print("# [CRITICAL] ngrok ha muerto. Ver traza arriba.")
                    break
                if self.bridge_process.poll() is not None:
                    self.flush_print("# [CRITICAL] El Bridge de Voz ha muerto.")
                    break
                time.sleep(10)
        except KeyboardInterrupt:
            self.stop()

    def stop(self, *args):
        self.flush_print("# [ORCHESTRATOR] Finalizando procesos...")
        if self.bridge_process: self.bridge_process.kill()
        if self.ngrok_process: self.ngrok_process.kill()
        sys.exit(0)

if __name__ == "__main__":
    VoiceOrchestrator().run()
