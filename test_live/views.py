from .services import GeminiLiveProbe
from asgiref.sync import async_to_sync
from django.shortcuts import render

# Create your views here.

from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views import View

class WalkieTalkieView(TemplateView):
    """
    View that renders the diagnostic interface for Gemini Live.
    ---
    Vista que renderiza la interfaz de diagnóstico para Gemini Live.
    """
    template_name = "test_live/walkie_talkie.html"

class ProcessAudioView(View):
    """
    Endpoint that receives audio chunks and interacts with the GeminiLiveProbe.
    ---
    Endpoint que recibe fragmentos de audio e interactúa con la sonda GeminiLiveProbe.
    """
    def post(self, request, *args, **kwargs):
        audio_file = request.FILES.get('audio')
        session_id = request.POST.get('session_id', 'TEST_DEFAULT')
        probe = GeminiLiveProbe(session_id)
        # Executing the diagnostic probe / Ejecutando la sonda de diagnóstico
        result = async_to_sync(probe.run_diagnostic)(audio_file)
        return JsonResponse(result)
