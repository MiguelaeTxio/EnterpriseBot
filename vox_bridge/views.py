# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/views.py
from django.http import HttpResponse
from django.views.generic import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

@method_decorator(csrf_exempt, name='dispatch')
class InboundCallView(View):
    """
    Vista Webhook encargada de recibir la llamada inicial de MundoSMS.
    Genera el XML de bienvenida y solicita la grabación de voz del usuario.
    """
    def post(self, request, *args, **kwargs):
        # XML basado en la especificación VoicePush v0.30 BETA
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<dialplan>
    <read voice="es-es-f1">Bienvenido a Enterprise Bot. Por favor, diga su nombre y el departamento con el que desea hablar tras la señal.</read>
    <record duration="5" b_beep="1" timeout_silence="2"/>
</dialplan>"""
        
        return HttpResponse(xml_content, content_type='text/xml')

    def get(self, request, *args, **kwargs):
        # Permitimos GET para pruebas rápidas de navegador
        return self.post(request, *args, **kwargs)
