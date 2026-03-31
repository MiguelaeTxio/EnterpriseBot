# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/views.py
import os
import logging
from django.http import HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

# Internal developer context logger
# Logger de contexto para el desarrollador
logger = logging.getLogger("VoxViews")

@method_decorator(csrf_exempt, name='dispatch')
class InboundCallView(View):
    """
    Handles inbound TwiML requests from Twilio to establish a WebSocket Media Stream.
    Retrieves the active ngrok URL from a shared session file and performs protocol upgrade to WSS.
    ---
    Gestiona las peticiones TwiML entrantes de Twilio para establecer un flujo de medios por WebSocket.
    Recupera la URL activa de ngrok desde un archivo de sesión compartido y realiza la actualización de protocolo a WSS.
    """
    
    def get_active_wss_url(self):
        """
        Reads the NGROK_URL.txt file and converts the HTTPS schema to WSS.
        ---
        Lee el archivo NGROK_URL.txt y convierte el esquema HTTPS a WSS.
        """
        shared_file = "/home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/SESSION/NGROK_URL.txt"
        default_url = "wss://enterprisebot.ngrok-free.app"
        
        if os.path.exists(shared_file):
            with open(shared_file, 'r') as f:
                raw_url = f.read().strip().rstrip('/')
                if raw_url:
                    return raw_url.replace("https://", "wss://")
        
        return default_url

    def post(self, request, *args, **kwargs):
        """
        Responds with the TwiML <Connect><Stream> instruction to redirect audio to the sidecar.
        ---
        Responde con la instrucción TwiML <Connect><Stream> para redireccionar el audio al sidecar.
        """
        wss_url = self.get_active_wss_url()
        
        # Twilio standard XML payload / Payload XML estándar de Twilio
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            '    <Connect>'
            f'        <Stream url="{wss_url}" />'
            '    </Connect>'
            '</Response>'
        )
        
        return HttpResponse(twiml, content_type='text/xml')
