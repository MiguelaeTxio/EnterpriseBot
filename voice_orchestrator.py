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

    def update_twilio_webhook(self, ngrok_url: str) -> bool:
        """
        Updates the Twilio voice webhook for all active PhoneNumber records
        in the database to point to the currently active ngrok tunnel URL.

        Regional routing logic (2026-04-11):
            Each PhoneNumber is interrogated against the Twilio Routes API
            (routes.twilio.com/v2/PhoneNumbers/{number}) to determine its
            active voice_region (IE1, US1, AU1, etc.). The webhook update
            request is then routed to the correct regional API endpoint using
            the matching regional credentials from the environment:
                US1 → api.twilio.com           + TWILIO_API_KEY_SID/SECRET
                IE1 → api.dublin.ie1.twilio.com + TWILIO_API_KEY_SID_IE1/SECRET_IE1

            This resolves the IE1 routing problem identified on 2026-04-10,
            where the standard api.twilio.com endpoint silently updated the
            US1 webhook configuration while leaving the IE1 configuration
            (the one actually serving inbound calls for Spanish numbers)
            unchanged and pointing to a stale URL.

        Returns True if all updates succeeded, False if any failed.
        ---
        Actualiza el webhook de voz de Twilio para todos los registros
        PhoneNumber activos en la base de datos para que apunten a la URL
        activa del túnel ngrok.

        Lógica de routing regional (2026-04-11):
            Cada PhoneNumber se interroga contra la Routes API de Twilio
            (routes.twilio.com/v2/PhoneNumbers/{number}) para determinar su
            voice_region activo (IE1, US1, AU1, etc.). La solicitud de
            actualización del webhook se enruta al endpoint regional correcto
            usando las credenciales regionales correspondientes del entorno:
                US1 → api.twilio.com            + TWILIO_API_KEY_SID/SECRET
                IE1 → api.dublin.ie1.twilio.com + TWILIO_API_KEY_SID_IE1/SECRET_IE1

            Esto resuelve el problema de routing IE1 identificado el 2026-04-10,
            donde el endpoint estándar api.twilio.com actualizaba silenciosamente
            la configuración del webhook en US1 mientras dejaba la configuración
            IE1 (la que realmente sirve las llamadas entrantes de los números
            españoles) sin cambios y apuntando a una URL obsoleta.

        Devuelve True si todas las actualizaciones tuvieron éxito,
        False si alguna falló.
        """
        import django
        import sys as _sys

        # Bootstrap Django ORM — required to query PhoneNumber records.
        # Arranque del ORM de Django — necesario para consultar registros PhoneNumber.
        _sys.path.insert(0, self.project_root)
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "enterprise_core.settings")
        try:
            django.setup()
        except RuntimeError:
            # django.setup() raises RuntimeError if called more than once.
            # django.setup() lanza RuntimeError si se llama más de una vez.
            pass

        from ivr_config.models import PhoneNumber

        # ------------------------------------------------------------------
        # Validate required US1 credentials (mandatory baseline).
        # Validar credenciales US1 requeridas (línea base obligatoria).
        # ------------------------------------------------------------------
        required_us1_vars = [
            "TWILIO_ACCOUNT_SID",
            "TWILIO_API_KEY_SID",
            "TWILIO_API_KEY_SECRET",
        ]
        missing_us1 = [v for v in required_us1_vars if not os.getenv(v)]
        if missing_us1:
            self.flush_print(
                f"# [WEBHOOK] ERROR: Variables de entorno US1 no encontradas: "
                f"{', '.join(missing_us1)}. Abortando actualización de webhook."
            )
            return False

        twilio_account_sid    = os.environ["TWILIO_ACCOUNT_SID"]
        us1_api_key_sid       = os.environ["TWILIO_API_KEY_SID"]
        us1_api_key_secret    = os.environ["TWILIO_API_KEY_SECRET"]

        # IE1 credentials — optional but required for Spanish numbers.
        # If absent, IE1 numbers are logged as skipped.
        # Credenciales IE1 — opcionales pero necesarias para números españoles.
        # Si están ausentes, los números IE1 se registran como omitidos.
        ie1_api_key_sid    = os.getenv("TWILIO_API_KEY_SID_IE1", "")
        ie1_api_key_secret = os.getenv("TWILIO_API_KEY_SECRET_IE1", "")

        if not ie1_api_key_sid or not ie1_api_key_secret:
            self.flush_print(
                "# [WEBHOOK] AVISO: Credenciales IE1 no configuradas "
                "(TWILIO_API_KEY_SID_IE1 / TWILIO_API_KEY_SECRET_IE1). "
                "Los números con voice_region IE1 serán omitidos."
            )

        voice_webhook_url = f"{ngrok_url.rstrip('/')}/api/vox/inbound/"

        self.flush_print("# [WEBHOOK] Iniciando actualización de webhooks Twilio...")
        self.flush_print(f"# [WEBHOOK] URL destino: {voice_webhook_url}")

        # ------------------------------------------------------------------
        # Regional endpoint map — valid as of 2026-04-11.
        # api.ie1.twilio.com is deprecated (stops working 2026-04-28).
        # Must use api.dublin.ie1.twilio.com for IE1.
        # Mapa de endpoints regionales — válido a 2026-04-11.
        # api.ie1.twilio.com está deprecado (deja de funcionar 2026-04-28).
        # Debe usarse api.dublin.ie1.twilio.com para IE1.
        # ------------------------------------------------------------------
        REGIONAL_API_ENDPOINTS = {
            "US1": "https://api.twilio.com",
            "IE1": "https://api.dublin.ie1.twilio.com",
            "AU1": "https://api.sydney.au1.twilio.com",
        }
        ROUTES_API_BASE = "https://routes.twilio.com/v2/PhoneNumbers"

        # ------------------------------------------------------------------
        # Query all active PhoneNumber records with voice capability.
        # Consultar todos los registros PhoneNumber activos con capacidad de voz.
        # ------------------------------------------------------------------
        voice_numbers = PhoneNumber.objects.filter(
            is_active=True,
            capabilities__in=["VOICE", "BOTH"],
        )

        if not voice_numbers.exists():
            self.flush_print(
                "# [WEBHOOK] AVISO: No se encontraron PhoneNumbers activos con "
                "capacidad de voz en la BD. No hay webhooks que actualizar."
            )
            return True

        all_succeeded = True

        for phone_record in voice_numbers:
            number_e164 = phone_record.number
            self.flush_print(f"# [WEBHOOK] ── Procesando: {number_e164} ──")

            # --------------------------------------------------------------
            # STEP 1: Detect active voice_region via Twilio Routes API.
            # The Routes API is a global resource — authenticates with US1
            # API Key credentials regardless of the number's region.
            # PASO 1: Detectar voice_region activo vía Routes API de Twilio.
            # La Routes API es un recurso global — se autentica con credenciales
            # API Key US1 independientemente de la región del número.
            # --------------------------------------------------------------
            routes_url = (
                f"{ROUTES_API_BASE}/"
                f"{requests.utils.quote(number_e164, safe='')}"
            )
            voice_region = "US1"  # safe default / valor por defecto seguro

            try:
                routes_resp = requests.get(
                    routes_url,
                    auth=(us1_api_key_sid, us1_api_key_secret),
                    timeout=15,
                )
                if routes_resp.status_code == 200:
                    voice_region = (
                        routes_resp.json().get("voice_region", "us1").upper()
                    )
                    self.flush_print(
                        f"# [WEBHOOK] Routes API → voice_region: '{voice_region}'"
                    )
                elif routes_resp.status_code == 404:
                    # No explicit routing config — defaults to US1 per Twilio docs.
                    # Sin config de routing explícita — US1 por defecto según docs Twilio.
                    self.flush_print(
                        f"# [WEBHOOK] Routes API → 404 (sin routing explícito). "
                        "Usando US1 por defecto."
                    )
                else:
                    self.flush_print(
                        f"# [WEBHOOK] AVISO: Routes API respondió HTTP "
                        f"{routes_resp.status_code} para {number_e164}. "
                        "Usando US1 como fallback seguro."
                    )
            except Exception as routes_exc:
                self.flush_print(
                    f"# [WEBHOOK] AVISO: Error consultando Routes API para "
                    f"{number_e164}: {routes_exc}. Usando US1 como fallback."
                )

            # --------------------------------------------------------------
            # STEP 2: Select regional credentials and API endpoint.
            # PASO 2: Seleccionar credenciales y endpoint regional.
            # --------------------------------------------------------------
            api_base = REGIONAL_API_ENDPOINTS.get(
                voice_region, REGIONAL_API_ENDPOINTS["US1"]
            )

            if voice_region == "IE1":
                if not ie1_api_key_sid or not ie1_api_key_secret:
                    self.flush_print(
                        f"# [WEBHOOK] OMITIDO: {number_e164} requiere credenciales "
                        "IE1 que no están configuradas en el .env."
                    )
                    all_succeeded = False
                    continue
                regional_auth = (ie1_api_key_sid, ie1_api_key_secret)
            elif voice_region == "US1":
                regional_auth = (us1_api_key_sid, us1_api_key_secret)
            else:
                self.flush_print(
                    f"# [WEBHOOK] OMITIDO: {number_e164} tiene voice_region "
                    f"'{voice_region}' sin credenciales configuradas."
                )
                all_succeeded = False
                continue

            # --------------------------------------------------------------
            # STEP 3: Locate the IncomingPhoneNumber SID on the regional
            # endpoint using the correct regional credentials.
            # PASO 3: Localizar el SID de IncomingPhoneNumber en el endpoint
            # regional usando las credenciales regionales correctas.
            # --------------------------------------------------------------
            try:
                list_url = (
                    f"{api_base}/2010-04-01/Accounts/{twilio_account_sid}"
                    f"/IncomingPhoneNumbers.json"
                    f"?PhoneNumber={requests.utils.quote(number_e164, safe='')}"
                )
                list_resp = requests.get(
                    list_url, auth=regional_auth, timeout=15
                )

                if list_resp.status_code != 200:
                    self.flush_print(
                        f"# [WEBHOOK] ERROR: HTTP {list_resp.status_code} al "
                        f"buscar SID de {number_e164} en {voice_region}. "
                        f"Respuesta: {list_resp.text[:300]}"
                    )
                    all_succeeded = False
                    continue

                incoming_numbers = list_resp.json().get(
                    "incoming_phone_numbers", []
                )
                if not incoming_numbers:
                    self.flush_print(
                        f"# [WEBHOOK] AVISO: {number_e164} no encontrado en "
                        f"la cuenta Twilio bajo la región {voice_region}. "
                        "Omitiendo."
                    )
                    all_succeeded = False
                    continue

                phone_sid = incoming_numbers[0]["sid"]
                self.flush_print(
                    f"# [WEBHOOK] SID localizado: {phone_sid} "
                    f"(región {voice_region})"
                )

            except Exception as sid_exc:
                self.flush_print(
                    f"# [WEBHOOK] ERROR al localizar SID de {number_e164}: "
                    f"{type(sid_exc).__name__}: {sid_exc}"
                )
                all_succeeded = False
                continue

            # --------------------------------------------------------------
            # STEP 4: Update the voice webhook on the correct regional
            # endpoint using requests.post() with HTTP Basic Auth.
            # Using requests directly (not TwilioClient SDK) avoids the need
            # for region-specific SDK client instantiation and is fully
            # supported per Twilio REST API documentation (2026-04-11).
            # PASO 4: Actualizar el webhook de voz en el endpoint regional
            # correcto usando requests.post() con autenticación HTTP Basic.
            # Usar requests directamente (no el SDK TwilioClient) evita la
            # necesidad de instanciar el cliente SDK con parámetros regionales
            # y está completamente soportado según la documentación de la
            # API REST de Twilio (2026-04-11).
            # --------------------------------------------------------------
            try:
                update_url = (
                    f"{api_base}/2010-04-01/Accounts/{twilio_account_sid}"
                    f"/IncomingPhoneNumbers/{phone_sid}.json"
                )
                update_resp = requests.post(
                    update_url,
                    auth=regional_auth,
                    data={"VoiceUrl": voice_webhook_url, "VoiceMethod": "POST"},
                    timeout=15,
                )

                if update_resp.status_code not in (200, 201):
                    self.flush_print(
                        f"# [WEBHOOK] ERROR: HTTP {update_resp.status_code} al "
                        f"actualizar {number_e164} en {voice_region}. "
                        f"Respuesta: {update_resp.text[:400]}"
                    )
                    all_succeeded = False
                    continue

                returned_url = update_resp.json().get("voice_url", "")
                if returned_url == voice_webhook_url:
                    self.flush_print(
                        f"# [WEBHOOK] ✓ {number_e164} actualizado correctamente "
                        f"| Región: {voice_region} | SID: {phone_sid} "
                        f"| URL: {returned_url}"
                    )
                else:
                    self.flush_print(
                        f"# [WEBHOOK] AVISO: URL devuelta no coincide para "
                        f"{number_e164} en {voice_region}. "
                        f"Solicitada: {voice_webhook_url} | "
                        f"Devuelta: {returned_url}"
                    )
                    all_succeeded = False

            except Exception as upd_exc:
                self.flush_print(
                    f"# [WEBHOOK] ERROR al actualizar {number_e164}: "
                    f"{type(upd_exc).__name__}: {upd_exc}"
                )
                all_succeeded = False

        if all_succeeded:
            self.flush_print(
                "# [WEBHOOK] Todos los webhooks actualizados correctamente."
            )
        else:
            self.flush_print(
                "# [WEBHOOK] AVISO: Algunos webhooks no pudieron actualizarse. "
                "Revise los mensajes anteriores."
            )

        return all_succeeded

    def start_bridge(self):
        self.flush_print("# [ORCHESTRATOR] Lanzando Sidecar Bridge...")
        # PIPE FIX: Launching the bridge with stdout=sys.stdout / stderr=sys.stderr
        # causes a deadlock when the parent process (orchestrator) shares those
        # descriptors with the ngrok subprocess output. The bridge blocks on its
        # first write attempt because the shared pipe is not being drained.
        # Solution: open a dedicated log file for the bridge and redirect both
        # stdout and stderr to it. This decouples the bridge output from the
        # orchestrator's stdout and eliminates the deadlock entirely.
        # CORRECCIÓN DE PIPE: Lanzar el bridge con stdout=sys.stdout / stderr=sys.stderr
        # provoca un deadlock cuando el proceso padre (orquestador) comparte esos
        # descriptores con la salida del subproceso ngrok. El bridge se bloquea en su
        # primer intento de escritura porque el pipe compartido no está siendo drenado.
        # Solución: abrir un archivo de log dedicado para el bridge y redirigir tanto
        # stdout como stderr a él. Esto desacopla la salida del bridge del stdout del
        # orquestador y elimina el deadlock completamente.
        bridge_log_path = "/home/MiguelAeTxio/PROJECTS/EnterpriseBot/logs/bridge.log"
        bridge_log_fh = open(bridge_log_path, "a", buffering=1, encoding="utf-8")
        self.flush_print(
            f"# [ORCHESTRATOR] Salida del bridge redirigida a: {bridge_log_path}"
        )
        self.bridge_process = subprocess.Popen(
            [self.python_bin, "-u", self.bridge_script],
            stdout=bridge_log_fh,
            stderr=bridge_log_fh,
            env=os.environ
        )

    def run(self):
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        if not self.start_ngrok(): return
        ngrok_url = None
        for _ in range(5):
            ngrok_url = self.get_public_url()
            if ngrok_url:
                break
            time.sleep(2)

        if ngrok_url:
            self.update_twilio_webhook(ngrok_url)
        else:
            self.flush_print(
                "# [ORCHESTRATOR] AVISO: No se pudo obtener la URL de ngrok. "
                "Los webhooks de Twilio no han sido actualizados."
            )

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
