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
        Closes all active ngrok tunnel sessions via the ngrok cloud API
        (api.ngrok.com) before killing local processes. This permanently
        resolves ERR_NGROK_334 ('endpoint already online') caused by orphaned
        remote tunnel sessions that survive after the local ngrok process is
        killed.

        Sequence:
            1. Load NGROK_API_KEY from the environment (set by load_dotenv in
               __init__).
            2. Query GET https://api.ngrok.com/endpoints to list all active
               remote endpoints and extract their tunnel_session IDs.
            3. Issue POST .../tunnel_sessions/{id}/stop per session — this
               instructs the ngrok cloud to terminate the remote ephemeral
               endpoint cleanly, freeing the URL for reuse.
            4. Wait 3 seconds for ngrok cloud propagation before the caller
               attempts to open a new tunnel.
            5. Kill any remaining local processes bound to target ports using
               the 2026 net_connections standard.
        ---
        Cierra todas las tunnel sessions activas de ngrok vía la API cloud de
        ngrok (api.ngrok.com) antes de matar los procesos locales. Esto resuelve
        permanentemente ERR_NGROK_334 ('endpoint already online') causado por
        tunnel sessions remotas huérfanas que sobreviven tras matar el proceso
        ngrok local.

        Secuencia:
            1. Cargar NGROK_API_KEY del entorno (establecida por load_dotenv en
               __init__).
            2. Consultar GET https://api.ngrok.com/endpoints para listar todos
               los endpoints remotos activos y extraer sus IDs de tunnel_session.
            3. Emitir POST .../tunnel_sessions/{id}/stop por sesión — esto
               instruye a la nube de ngrok a terminar el endpoint efímero remoto
               de forma limpia, liberando la URL para su reutilización.
            4. Esperar 3 segundos para la propagación en la nube de ngrok antes
               de que el llamante intente abrir un nuevo túnel.
            5. Matar los procesos locales restantes vinculados a los puertos
               objetivo usando el estándar net_connections de 2026.
        """
        self.flush_print("# [ORCHESTRATOR] Iniciando limpieza de infraestructura ngrok...")

        # STEP 1: Load the ngrok cloud API key from the environment.
        # PASO 1: Cargar la clave de API cloud de ngrok desde el entorno.
        ngrok_api_key = os.getenv("NGROK_API_KEY")
        cloud_api_base = "https://api.ngrok.com"
        cloud_headers = {
            "Authorization": f"Bearer {ngrok_api_key}",
            "Ngrok-Version": "2",
            "Content-Type": "application/json",
        }

        if not ngrok_api_key:
            self.flush_print(
                "# [CLEANUP] NGROK_API_KEY no encontrada en el entorno. "
                "Omitiendo cierre de tunnel sessions remotas."
            )
        else:
            # STEP 2: Query active endpoints from the ngrok cloud API.
            # PASO 2: Consultar los endpoints activos desde la API cloud de ngrok.
            try:
                resp = requests.get(
                    f"{cloud_api_base}/endpoints",
                    headers=cloud_headers,
                    timeout=10
                )
                if resp.status_code == 200:
                    endpoints = resp.json().get("endpoints", [])
                    if not endpoints:
                        self.flush_print(
                            "# [CLEANUP] No se encontraron endpoints activos en ngrok cloud."
                        )
                    else:
                        # STEP 3: Stop each tunnel session associated with an active endpoint.
                        # PASO 3: Detener cada tunnel session asociada a un endpoint activo.
                        session_ids_stopped = set()
                        for endpoint in endpoints:
                            public_url = endpoint.get("public_url", "N/A")
                            tunnel_session = endpoint.get("tunnel_session", {})
                            session_id = tunnel_session.get("id", "")

                            if not session_id:
                                self.flush_print(
                                    f"# [CLEANUP] Endpoint {public_url} sin tunnel_session.id. "
                                    "Omitiendo."
                                )
                                continue

                            if session_id in session_ids_stopped:
                                # Avoid duplicate stop calls for shared sessions.
                                # Evitar llamadas stop duplicadas para sesiones compartidas.
                                continue

                            stop_resp = requests.post(
                                f"{cloud_api_base}/tunnel_sessions/{session_id}/stop",
                                headers=cloud_headers,
                                json={},
                                timeout=10
                            )
                            session_ids_stopped.add(session_id)
                            self.flush_print(
                                f"# [CLEANUP] Tunnel session {session_id} "
                                f"({public_url}) detenida "
                                f"(HTTP {stop_resp.status_code})."
                            )

                        # STEP 4: Wait for ngrok cloud propagation.
                        # PASO 4: Esperar la propagación en la nube de ngrok.
                        if session_ids_stopped:
                            self.flush_print(
                                "# [CLEANUP] Esperando 3s para propagación en ngrok cloud..."
                            )
                            time.sleep(3)
                else:
                    self.flush_print(
                        f"# [CLEANUP] API cloud ngrok respondió HTTP {resp.status_code}. "
                        f"Respuesta: {resp.text[:200]}"
                    )

            except requests.exceptions.ConnectionError as exc:
                self.flush_print(
                    f"# [CLEANUP] Error de conexión con API cloud ngrok: {exc}. "
                    "Continuando con limpieza de puertos locales."
                )
            except Exception as exc:
                self.flush_print(
                    f"# [CLEANUP] Error inesperado al limpiar ngrok cloud: {exc}"
                )

        # STEP 5: Kill local processes bound to target ports.
        # PASO 5: Matar procesos locales vinculados a los puertos objetivo.
        self.flush_print("# [ORCHESTRATOR] Auditando puertos locales (net_connections)...")
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
        except requests.exceptions.ConnectionError:
            self.flush_print(
                "# [ORCHESTRATOR] Error de conexión con API local ngrok "
                f"({self.api_url}). El proceso ngrok puede no estar listo todavía. "
                "Reintentando en el siguiente ciclo..."
            )
        except requests.exceptions.Timeout:
            self.flush_print(
                "# [ORCHESTRATOR] Timeout consultando API local ngrok "
                f"({self.api_url}). El agente ngrok no respondió en el plazo fijado. "
                "Reintentando en el siguiente ciclo..."
            )
        except (KeyError, IndexError) as exc:
            self.flush_print(
                f"# [ORCHESTRATOR] Respuesta de API local ngrok inesperada o "
                f"estructura JSON no reconocida: {exc}. "
                "Verifique que el agente ngrok está activo y la clave 'tunnels' existe."
            )
        except ValueError as exc:
            self.flush_print(
                f"# [ORCHESTRATOR] Error al decodificar JSON de la API local ngrok: {exc}. "
                "La respuesta recibida no es JSON válido."
            )
        except Exception as exc:
            self.flush_print(
                f"# [ORCHESTRATOR] Error inesperado en get_public_url(): "
                f"{type(exc).__name__}: {exc}"
            )
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
