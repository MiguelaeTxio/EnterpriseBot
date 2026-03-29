# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/views.py
from django.http import HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .models import CallInteraction
import logging

# Logger configuration for real-time monitoring
# Configuración de logs para monitorización en tiempo real
logger = logging.getLogger(__name__)

@method_decorator(csrf_exempt, name='dispatch')
class InboundCallView(View):
    """
    Webhook receiver for Twilio Inbound Calls.
    Orchestrates the initial signaling, persists the call metadata in MySQL, 
    and returns the TwiML to establish a Media Stream connection.
    ---
    Receptor de Webhook para llamadas entrantes de Twilio.
    Orquesta la señalización inicial, persiste los metadatos de la llamada en MySQL
    y devuelve el TwiML para establecer una conexión de Media Stream.
    """
    
    def post(self, request, *args, **kwargs):
        # 1. Extraction of signaling data / Extracción de datos de señalización
        call_sid = request.POST.get('CallSid')
        from_number = request.POST.get('From')
        to_number = request.POST.get('To')
        account_sid = request.POST.get('AccountSid')
        
        # 2. Initial persistence in database / Persistencia inicial en base de datos
        # We record the event immediately to ensure traceability
        # Registramos el evento inmediatamente para asegurar la trazabilidad
        try:
            CallInteraction.objects.create(
                call_sid=call_sid,
                from_number=from_number,
                to_number=to_number,
                account_sid=account_sid,
                status='ringing'
            )
            # Log for the developer context / Log para el contexto del desarrollador
            # print(f"# [INFO] Señalización recibida: {call_sid} desde {from_number}")
        except Exception as e:
            # En caso de error en base de datos, el flujo de la llamada no debe morir
            # logger.error(f"# [ERROR] Fallo en persistencia: {str(e)}")
            pass

        # 3. WebSocket Endpoint Configuration (Sidecar Bridge) / Configuración del Endpoint
        # NOTE: This URL must be updated with the active ngrok tunnel URL
        # NOTA: Esta URL debe ser actualizada con la URL activa del túnel de ngrok
        wss_url = "wss://tu-id-ngrok.ngrok-free.app"
        
        # 4. TwiML Response Generation / Generación de Respuesta TwiML
        # We use <Connect><Stream> to deliver the raw audio to our Sidecar process
        # Usamos <Connect><Stream> para entregar el audio RAW a nuestro proceso Sidecar
        twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Connect>
                <Stream url="{wss_url}" />
            </Connect>
        </Response>"""
        
        return HttpResponse(twiml_response, content_type='text/xml')
