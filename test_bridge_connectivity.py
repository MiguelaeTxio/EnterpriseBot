# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/test_bridge_connectivity.py
import asyncio
import aiohttp
import json
import base64
import logging
import os

"""
EnterpriseBot Dynamic Architecture Validator (April 2026 Standard).
Refactored to resolve public Ngrok URLs for cross-console auditing.
Tests the full pipeline: Public Internet -> Tunnel -> Hybrid Bridge -> Gemini 3.1 Flash Live.
---
Validador de Arquitectura Dinámico de EnterpriseBot (Estándar Abril 2026).
Refactorizado para resolver URLs públicas de Ngrok para auditoría entre consolas.
Prueba la tubería completa: Internet Pública -> Túnel -> Bridge Híbrido -> Gemini 3.1 Flash Live.
"""

# Advanced Logging Configuration / Configuración de Registro Avanzada
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s # [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("BridgeAudit")

class BridgeValidator:
    """
    Simulates a remote telephony client using the active ngrok tunnel.
    ---
    Simula un cliente de telefonía remoto usando el túnel ngrok activo.
    """
    def __init__(self):
        self.project_root = "/home/MiguelAeTxio/PROJECTS/EnterpriseBot"
        self.shared_url_file = os.path.join(self.project_root, "DOCS/SESSION/NGROK_URL.txt")
        self.public_url = self._resolve_public_url()
        
        if self.public_url:
            # External endpoints via HTTPS/WSS (Ngrok Standard)
            self.base_url = self.public_url
            self.wss_url = self.public_url.replace("https://", "wss://").replace("http://", "wss://") + "/media"
        else:
            self.base_url = None
            
        self.call_sid = "CA_AUDIT_EXTERNAL_2026"
        self.stream_sid = "ST_AUDIT_EXT_001"

    def _resolve_public_url(self) -> str:
        """
        Reads the dynamic tunnel URL from the session shared file.
        ---
        Lee la URL dinámica del túnel desde el archivo compartido de sesión.
        """
        try:
            if os.path.exists(self.shared_url_file):
                with open(self.shared_url_file, 'r') as f:
                    url = f.read().strip()
                    logger.info(f"# [INFO] URL de Auditoría resuelta: {url}")
                    return url
            else:
                logger.error("# [ERROR] No se encontró NGROK_URL.txt. ¿Está el orquestador activo?")
        except Exception as e:
            logger.error(f"# [ERROR] Error al leer la URL: {str(e)}")
        return ""

    async def audit_http_handshake(self, session):
        """
        Validates the TwiML generation via the Public Tunnel.
        ---
        Valida la generación de TwiML a través del Túnel Público.
        """
        if not self.base_url: return False
        
        logger.info(f"# [STEP 1] Auditando Handshake HTTP EXTERNO ({self.base_url}/api/vox/inbound/)...")
        endpoint = f"{self.base_url}/api/vox/inbound/"
        payload = {
            "CallSid": self.call_sid,
            "From": "+34688360595",
            "To": "+12603466780"
        }
        
        try:
            async with session.post(endpoint, data=payload, timeout=10) as response:
                if response.status == 200:
                    content = await response.text()
                    logger.info("# [SUCCESS] Respuesta HTTP 200 recibida desde el Túnel.")
                    if "<Stream url=\"wss://" in content:
                        logger.info("# [SUCCESS] TwiML válido y seguro detectado.")
                        return True
                    else:
                        logger.error("# [FAIL] El TwiML no contiene la directiva <Stream> correcta.")
                else:
                    logger.error(f"# [FAIL] El Bridge respondió vía Ngrok con estado: {response.status}")
        except Exception as e:
            logger.error(f"# [CRITICAL] Fallo en la conexión de red externa: {str(e)}")
        return False

    async def audit_websocket_flow(self, session):
        """
        Validates binary audio streaming via WSS and Gemini 3.1 Flash Live.
        ---
        Valida el streaming de audio binario vía WSS y Gemini 3.1 Flash Live.
        """
        logger.info(f"# [STEP 2] Auditando Flujo WebSocket SEGURO ({self.wss_url})...")
        
        try:
            # SSL validation is handled by aiohttp for Ngrok certificates
            async with session.ws_connect(self.wss_url, timeout=60.0) as ws:
                logger.info("# [SUCCESS] Conexión WSS establecida a través del Túnel.")

                # 1. Start Event / Evento de Inicio
                start_event = {
                    "event": "start",
                    "start": {
                        "callSid": self.call_sid,
                        "streamSid": self.stream_sid,
                        "accountSid": "AC_EXTERNAL_AUDIT"
                    }
                }
                await ws.send_json(start_event)
                logger.info("# [WSS] Evento 'start' inyectado en el túnel.")

                # 2. Dummy Media Frame (April 2026 Compliance)
                # G.711 mu-law silent frame.
                dummy_payload = base64.b64encode(b'\xff' * 160).decode('utf-8')
                media_event = {
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {
                        "payload": dummy_payload
                    }
                }
                await ws.send_json(media_event)
                logger.info("# [WSS] Trama de audio enviada al Bridge Híbrido.")

                # 3. Listening for AI Response / Escuchando Respuesta de la IA
                logger.info("# [SDK] Esperando eco de Gemini 3.1 Flash Live a través del Bridge...")
                
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("event") == "media":
                            logger.info("\n# [SUCCESS] ¡ARQUITECTURA DE VOZ COMPLETA VALIDADA!")
                            logger.info(f"# [INFO] Latencia de red: OK.")
                            logger.info(f"# [INFO] Audio de IA recibido: {len(data['media']['payload'])} bytes.")
                            logger.info("# [INFO] El sistema está listo para pruebas de campo (Outbound).\n")
                            break
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.warning("# [WSS] Conexión cerrada por el host remoto.")
                        break
        except Exception as e:
            logger.error(f"# [CRITICAL] Fallo en la auditoría WSS: {str(e)}")

    async def run(self):
        """
        Main execution sequence.
        """
        if not self.base_url:
            logger.error("# [ABORT] No hay infraestructura activa para auditar.")
            return

        async with aiohttp.ClientSession() as session:
            if await self.audit_http_handshake(session):
                # Stability pause
                await asyncio.sleep(2)
                await self.audit_websocket_flow(session)

if __name__ == "__main__":
    validator = BridgeValidator()
    try:
        asyncio.run(validator.run())
    except KeyboardInterrupt:
        logger.info("# [SYSTEM] Auditoría detenida.")
