# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/debug_webhook_locally.py
import os
import django
from django.test import RequestFactory
from django.conf import settings

# Setup Django Environment / Configuración del Entorno Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'enterprise_core.settings')
django.setup()

from vox_bridge.views import InboundCallView

def run_diagnostic():
    print("# [DIAGNOSTIC] Iniciando simulación de Webhook local...")
    
    # 1. Mocking the Twilio Request / Simulando la Petición de Twilio
    factory = RequestFactory()
    request = factory.post('/api/vox/inbound/', {
        'CallSid': 'CA_DEBUG_123456',
        'From': '+34688360595',
        'To': '+12603466780',
        'AccountSid': 'ACd8fd956e126840342eaa2d201baed1fd'
    })
    
    # 2. Invoking the View / Invocando la Vista
    view = InboundCallView.as_view()
    response = view(request)
    
    # 3. Capture RAW Content / Capturar Contenido Crudo
    # Usamos modo binario 'wb' para no alterar saltos de línea ni espacios.
    output_path = '/home/MiguelAeTxio/SWAP/raw_twiml_debug.xml'
    with open(output_path, 'wb') as f:
        f.write(response.content)
    
    print(f"# [SUCCESS] TwiML capturado en: {output_path}")
    print(f"# [INFO] Status Code: {response.status_code}")
    print(f"# [INFO] Content-Type: {response.get('Content-Type')}")

if __name__ == "__main__":
    run_diagnostic()
