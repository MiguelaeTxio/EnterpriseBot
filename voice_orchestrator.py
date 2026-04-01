# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/voice_orchestrator.py
import os
import subprocess
import time
import requests
import sys
import signal
import psutil
from dotenv import load_dotenv

"""
EnterpriseBot Voice Orchestrator: Master control for Tunneling and Sidecar.
Refactored for Native Port Management using psutil (March 2026).
---
Orquestador de Voz de EnterpriseBot: Control maestro para Túnel y Sidecar.
Refactorizado para Gestión Nativa de Puertos usando psutil (Marzo 2026).
"""

# Forzar salida inmediata para visibilidad total en Dashboard
os.environ["PYTHONUNBUFFERED"] = "1"

class VoiceOrchestrator:
    def __init__(self):
        self.project_root = "/home/MiguelAeTxio/PROJECTS/EnterpriseBot"
        self.ngrok_bin = os.path.join(self.project_root, "ngrok")
        self.config_path = os.path.join(self.project_root, "ngrok.yml")
        self.bridge_script = os.path.join(self.project_root, "voice_sidecar_bridge.py")
        self.python_bin = sys.executable
        # Shared file for inter-node communication
        self.shared_url_file = os.path.join(self.project_root, "DOCS/SESSION/NGROK_URL.txt")
        
        # Explicitly load .env from project root
        load_dotenv(os.path.join(self.project_root, ".env"))

    def flush_print(self, message):
        print(message, flush=True)

    def cleanup_ports(self):
        """
        Natively releases port 8081 using psutil to avoid restricted system commands.
        ---
        Libera el puerto 8081 de forma nativa usando psutil para evitar comandos de sistema restringidos.
        """
        self.flush_print("# [ORCHESTRATOR] Auditando puerto 8081 (Método Nativo Python)...")
        target_port = 8081
        found = False
        
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # Iterate over connections of the current process
                connections = proc.connections(kind='inet')
                for conn in connections:
                    if conn.laddr.port == target_port:
                        found = True
                        self.flush_print(f"# [CLEANUP] Detectado proceso '{proc.info['name']}' (PID: {proc.pid}) bloqueando el puerto {target_port}")
                        
                        # Attempt clean termination
                        proc.terminate()
                        # Wait up to 3 seconds for it to release the resource
                        try:
                            proc.wait(timeout=3)
                            self.flush_print(f"# [CLEANUP] Proceso {proc.pid} finalizado correctamente.")
                        except psutil.TimeoutExpired:
                            self.flush_print(f"# [WARN] El proceso no respondió. Forzando cierre (kill)...")
                            proc.kill()
                            
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                # Ignore processes that disappear or don't belong to the user
                continue
        
        if not found:
            self.flush_print(f"# [ORCHESTRATOR] Puerto {target_port} libre. No se requiere limpieza.")
        else:
            # Small grace period for the OS to mark the port as available
            time.sleep(1)

    def start_ngrok(self):
        self.cleanup_ports()
        self.flush_print("# [ORCHESTRATOR] Iniciando túnel ngrok v3...")
        
        token = os.getenv('NGROK_AUTHTOKEN')
        if not token:
            self.flush_print("# [ERROR] Variable NGROK_AUTHTOKEN no encontrada.")
            return False

        # Build command following ngrok v3 syntax
        cmd = [
            self.ngrok_bin, "start", 
            "--authtoken", token,
            "--config", self.config_path, 
            "enterprise_voice_bridge"
        ]
        
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
        """Queries local ngrok API and persists the URL for the Django Web Node"""
        try:
            response = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=2)
            tunnels = response.json().get('tunnels', [])
            if tunnels:
                url = tunnels[0].get('public_url')
                # Persist URL to shared file
                try:
                    with open(self.shared_url_file, 'w') as f:
                        f.write(url)
                    self.flush_print(f"# [ORCHESTRATOR] URL persistida en: {self.shared_url_file}")
                except Exception as e:
                    self.flush_print(f"# [ERROR FS] Error al escribir NGROK_URL.txt: {str(e)}")

                self.flush_print(f"\n# ########################################################")
                self.flush_print(f"# [SUCCESS] CONECTIVIDAD ESTABLECIDA")
                self.flush_print(f"# URL PÚBLICA: {url}")
                self.flush_print(f"# ########################################################\n")
                return url
        except: pass
        return None

    def start_bridge(self):
        self.flush_print("# [ORCHESTRATOR] Lanzando Voice Sidecar Bridge (Gemini Live A2A)...")
        # Ensure the bridge is launched with unbuffered output
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

        # Wait for ngrok to establish tunnel and publish URL
        for _ in range(5):
            if self.get_public_url(): break
            time.sleep(2)

        self.start_bridge()

        try:
            while True:
                if self.ngrok_process.poll() is not None:
                    self.flush_print("# [CRITICAL] ngrok ha fallado.")
                    break
                if self.bridge_process.poll() is not None:
                    self.flush_print("# [CRITICAL] El Bridge de Voz ha fallado.")
                    break
                time.sleep(10)
        except KeyboardInterrupt:
            self.stop()

    def stop(self, *args):
        self.flush_print("# [ORCHESTRATOR] Finalizando procesos de infraestructura...")
        if os.path.exists(self.shared_url_file):
            try: os.remove(self.shared_url_file)
            except: pass

        if hasattr(self, 'bridge_process') and self.bridge_process: self.bridge_process.terminate()
        if hasattr(self, 'ngrok_process') and self.ngrok_process: self.ngrok_process.terminate()
        sys.exit(0)

if __name__ == "__main__":
    VoiceOrchestrator().run()
