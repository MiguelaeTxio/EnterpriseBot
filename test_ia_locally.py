# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/test_ia_locally.py
import os
import django
import asyncio
import logging

# Configuración de logs en castellano (Directriz 2.1.3)
logging.basicConfig(level=logging.INFO, format='# [TEST] %(message)s')
logger = logging.getLogger("TestIA")

# Inicialización mínima del entorno Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "enterprise_core.settings")
django.setup()

from vox_bridge.services import GeminiStreamService

async def run_diagnostic():
    service = GeminiStreamService()
    logger.info("Iniciando diagnóstico local de esquema VoiceConfig...")
    
    try:
        # Intentamos instanciar la conexión (Punto de fallo de Pydantic)
        connection_coro = await service.connect()
        logger.info("ESQUEMA VÁLIDO: El SDK 1.69.0 ha aceptado la configuración de voz.")
        
        # Validamos la conectividad real con la API Key (Handshake)
        async with connection_coro as session:
            logger.info("CONECTIVIDAD OK: Handshake con Google GenAI exitoso.")
            print("\n# [RESULTADO] SUCCESS: La infraestructura de IA está lista.\n")
            
    except Exception as e:
        logger.error(f"FALLO DETECTADO: {str(e)}")
        print("\n# [RESULTADO] FAIL: El esquema sigue siendo rechazado.\n")

if __name__ == "__main__":
    asyncio.run(run_diagnostic())
