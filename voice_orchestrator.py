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
2026 Standard: psutil.net_connections & ngrok v3 Config-Driven.
---
Orquestador de Voz de EnterpriseBot: Control maestro para Túnel y Sidecar.
Estándar 2026: psutil.net_connections y ngrok v3 basado en Configuración.
"""

os.environ["PYTHONUNBUFFERED"] = "1"

class VoiceOrchestrator:
    def __init__(self):
        self.project_root = "/home/MiguelAeTxio/PROJECTS/EnterpriseBot"
        self.ngrok_bin = os.path.join(self.project_root, "ngrok")
        self.config_path = os.path.join(self.project_root, "ngrok.yml")
        self.bridge_script = os.path.join(self.project_root, "voice_sidecar_bridge.py")
        self.python_bin = sys.executable
        self.shared_url_file = os.path.join(self.project_root, "DOCS/SESSION/NGROK_URL.txt")
        # El puerto 4041 se define ahora en el ngrok.yml
        self.api_url = "http://127.0.0.1:4041/api/tunnels"
        load_dotenv(os.path.join(self.project_root, ".env"))

    def flush_print(self, message):
        print(message, flush=True)

    def cleanup_ports(self):
        """
        Natively releases ports using the 2026 net_connections standard.
        ---
        Libera los puertos usando el estándar net_connections de 2026.
        """
        self.flush_print("# [ORCHESTRATOR] Auditando puertos (net_connections)...")
        target_ports = [8081, 4041, 4040]
        
        # ✅ APRIL 2026 FIX: Use net_connections() instead of deprecated connections()
        for conn in psutil.net_connections(kind='inet'):
            if conn.laddr.port in target_ports and conn.pid:
                try:
                    proc = psutil.Process(conn.pid)
                    self.flush_print(f"# [CLEANUP] Finalizando proceso {conn.pid} ({proc.name()})")
                    proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

    def start_ngrok(self):
        """
        Launches ngrok v3 using YAML-driven configuration.
        ---
        Lanza ngrok v3 utilizando configuración basada en YAML.
        """
        self.cleanup_ports()
        self.flush_print("# [ORCHESTRATOR] Iniciando túnel HTTP (Puerto 8081)...")
        
        # ✅ APRIL 2026 FIX: Removed --web-addr flag to avoid 'unknown flag' error.
        # The agent configuration is now handled entirely via --config ngrok.yml.
        cmd = [
            self.ngrok_bin, "http", "8081",
            "--config", self.config_path,
            "--log", "stdout"
        ]
        
        self.ngrok_process = subprocess.Popen(
            cmd, stdout=sys.stdout, stderr=sys.stderr, env=os.environ, text=True
        )
        time.sleep(5)
        return True

    def get_public_url(self):
        """
        Queries the 2026 API endpoint for the dynamic URL.
        """
        try:
            response = requests.get(self.api_url, timeout=2)
            tunnels = response.json().get('tunnels', [])
            if tunnels:
                url = tunnels[0].get('public_url')
                with open(self.shared_url_file, 'w') as f:
                    f.write(url)
                self.flush_print(f"\n# [SUCCESS] TÚNEL 2026 ACTIVO: {url}\n")
                return url
        except: pass
        return None

    def start_bridge(self):
        self.flush_print("# [ORCHESTRATOR] Lanzando Sidecar Bridge...")
        self.bridge_process = subprocess.Popen(
            [self.python_bin, "-u", self.bridge_script], 
            stdout=sys.stdout, stderr=sys.stderr, env=os.environ
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
                if self.ngrok_process.poll() is not None: break
                if self.bridge_process.poll() is not None: break
                time.sleep(10)
        except KeyboardInterrupt:
            self.stop()

    def stop(self, *args):
        self.flush_print("# [ORCHESTRATOR] Apagando infraestructura 2026...")
        if os.path.exists(self.shared_url_file): os.remove(self.shared_url_file)
        if hasattr(self, 'bridge_process'): self.bridge_process.terminate()
        if hasattr(self, 'ngrok_process'): self.ngrok_process.terminate()
        sys.exit(0)

if __name__ == "__main__":
    VoiceOrchestrator().run()
