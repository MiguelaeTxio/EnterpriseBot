# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/views.py
from django.http import HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .models import CallInteraction
import requests
import logging

# Logger configuration for real-time monitoring
# Configuración de logs para monitorización en tiempo real
logger = logging.getLogger(__name__)

@method_decorator(csrf_exempt, name='dispatch')
class InboundCallView(View):
    """
    Webhook receiver for Twilio Inbound Calls.
    Dynamically discovers the ngrok public URL and returns TwiML for Media Streaming.
    ---
    Receptor de Webhook para llamadas entrantes de Twilio.
    Descubre dinámicamente la URL pública de ngrok y devuelve TwiML para Media Streaming.
    """
    
    def get_active_wss_url(self):
        """
        Queries the local ngrok API to find the current public endpoint.
        Converts https:// to wss:// for Media Streams compatibility.
        ---
        Consulta la API local de ngrok para encontrar el endpoint público actual.
        Convierte https:// a wss:// para compatibilidad con Media Streams.
        """
        try:
            # Query the local agent API / Consultar la API del agente local
            response = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=1)
            response.raise_for_status()
            tunnels = response.json().get('tunnels', [])
            
            if tunnels:
                # Extract the first available public URL
                public_url = tunnels[0].get('public_url')
                # Transform protocol to WebSocket Secure
                return public_url.replace("https://", "wss://")
        except Exception as e:
            logger.error(f"# [ERROR] No se pudo recuperar la URL de ngrok: {str(e)}")
        
        # Fallback (This should be avoided in production)
        return "wss://enterprisebot-bridge.ngrok-free.app"

    def post(self, request, *args, **kwargs):
        # 1. Extraction of signaling data / Extracción de datos de señalización
        call_sid = request.POST.get('CallSid')
        from_number = request.POST.get('From', 'Unknown')
        to_number = request.POST.get('To', 'Unknown')
        account_sid = request.POST.get('AccountSid')
        
        # 2. Persistence / Persistencia
        try:
            CallInteraction.objects.create(
                call_sid=call_sid,
                from_number=from_number,
                to_number=to_number,
                account_sid=account_sid,
                status='ringing'
            )
            print(f"# [DJANGO] Llamada registrada: {call_sid} desde {from_number}", flush=True)
        except Exception as e:
            logger.error(f"# [ERROR DB] Fallo en persistencia inicial: {str(e)}")

        # 3. Dynamic WebSocket Discovery / Descubrimiento Dinámico de WebSocket
        wss_url = self.get_active_wss_url()
        
        # 4. TwiML Generation / Generación de TwiML
        # We use <Connect><Stream> to establish the bidirectional audio pipe.
        # Usamos <Connect><Stream> para establecer el conducto de audio bidireccional.
        twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Connect>
                <Stream url="{wss_url}" />
            </Connect>
        </Response>"""
        
        print(f"# [DJANGO] TwiML generado con URL: {wss_url}", flush=True)
        return HttpResponse(twiml_response, content_type='text/xml')
