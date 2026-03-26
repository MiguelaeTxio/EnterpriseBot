# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/views.py
import os
import logging
from django.http import HttpResponse
from django.views.generic import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from .models import CallInteraction
from .services import AudioHandlingService, GeminiAudioService

logger = logging.getLogger(__name__)

@method_decorator(csrf_exempt, name='dispatch')
class InboundCallView(View):
    """
    Webhook View that handles the full call lifecycle with MundoSMS and Gemini.
    ---
    Vista Webhook que gestiona el ciclo de vida completo de la llamada con MundoSMS y Gemini.
    """

    def post(self, request, *args, **kwargs):
        # Extract metadata from MundoSMS request
        # Extraer metadatos de la petición de MundoSMS
        call_id = request.POST.get('call_id')
        phone_number = request.POST.get('FROM', request.POST.get('CALLERID', 'Unknown'))
        recording_url = request.POST.get('[LAST_RECORD]')

        # Phase 1: Initial Greeting and Recording Command
        # Fase 1: Saludo Inicial y Comando de Grabación
        if not recording_url:
            CallInteraction.objects.update_or_create(
                call_id=call_id,
                defaults={'phone_number': phone_number}
            )
            
            xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<dialplan>
    <read voice="es-es-f1">Bienvenido a Enterprise Bot. Por favor, tras la señal, indique brevemente el motivo de su llamada o el departamento con el que desea hablar.</read>
    <record duration="5" b_beep="1" timeout_silence="2"/>
</dialplan>"""
            return HttpResponse(xml_content, content_type='text/xml')

        # Phase 2: Audio Processing and AI Classification
        # Fase 2: Procesamiento de Audio y Clasificación por IA
        temp_audio_path = None
        detected_dept = "ERROR_AMBIGUO"
        
        try:
            # 1. Download audio to SWAP
            temp_audio_path = AudioHandlingService.download_remote_audio(recording_url, call_id)
            
            if temp_audio_path:
                # 2. AI Inference
                gemini_service = GeminiAudioService()
                result = gemini_service.classify_call_intent(temp_audio_path)
                
                detected_dept = result.department
                
                # 3. Update Interaction Model
                CallInteraction.objects.filter(call_id=call_id).update(
                    recording_url=recording_url,
                    transcription=result.transcription,
                    department_detected=detected_dept
                )
        except Exception as e:
            logger.error(f"Critical error in InboundCallView for call {call_id}: {str(e)}")
        finally:
            # 4. SWAP Hygiene: Remove temp file
            if temp_audio_path and os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)

        # Phase 3: Dynamic XML Redirection
        # Fase 3: Redirección XML Dinámica
        extension_map = {
            "VENTAS": "101",
            "SOPORTE": "102",
            "ADMINISTRACION": "103",
            "ERROR_AMBIGUO": "100" # General Reception / Recepción General
        }
        
        target_ext = extension_map.get(detected_dept, "100")
        
        xml_redirection = f"""<?xml version="1.0" encoding="UTF-8"?>
<dialplan>
    <read voice="es-es-f1">Transfiriendo su llamada al departamento de {detected_dept.lower()}. Espere un momento.</read>
    <call destination="{target_ext}"/>
</dialplan>"""
        
        return HttpResponse(xml_redirection, content_type='text/xml')

    def get(self, request, *args, **kwargs):
        return HttpResponse("EnterpriseBot Webhook Active", content_type='text/plain')
