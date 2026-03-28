# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/views.py
from django.http import HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

@method_decorator(csrf_exempt, name='dispatch')
class InboundCallView(View):
    """
    Webhook receiver for Twilio Inbound Calls.
    Returns TwiML to connect the call to the Sidecar WebSocket.
    ---
    Receptor de Webhook para llamadas entrantes de Twilio.
    Devuelve TwiML para conectar la llamada al WebSocket del Sidecar.
    """
    def post(self, request, *args, **kwargs):
        host = request.get_host()
        # Nota: En producción, 'wss_url' apuntará al puerto de la Always-on Task
        wss_url = f"wss://{host}/media-stream"
        
        twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say language="es-ES">Conectando con la inteligencia artificial de Enterprise Bot.</Say>
            <Connect>
                <Stream url="{wss_url}" />
            </Connect>
        </Response>"""
        
        return HttpResponse(twiml_response, content_type='text/xml')
