# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/views.py
import os
from django.http import HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .models import CallInteraction

@method_decorator(csrf_exempt, name='dispatch')
class InboundCallView(View):
    def get_active_wss_url(self):
        shared_file = "/home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/SESSION/NGROK_URL.txt"
        if os.path.exists(shared_file):
            with open(shared_file, 'r') as f:
                url = f.read().strip().rstrip('/')
                return url.replace("https://", "wss://")
        return "wss://enterprisebot.ngrok-free.app"

    def post(self, request, *args, **kwargs):
        call_sid = request.POST.get('CallSid', 'Unknown')
        wss_url = self.get_active_wss_url()
        twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Connect><Stream url="{wss_url}" /></Connect></Response>'
        return HttpResponse(twiml, content_type='text/xml')
