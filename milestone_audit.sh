# 1. DISPARO DE SEÑALIZACIÓN (OUTBOUND TRIGGER)
# Se invoca el script de validación con inyección de variables de entorno corregidas.
python3 -m dotenv run python3 /home/MiguelAeTxio/PROJECTS/EnterpriseBot/trigger_outbound_call.py

# 2. PERIODO DE GRACIA PARA SEÑALIZACIÓN
# Esperamos 12 segundos para permitir el Handshake de Twilio y la respuesta WSGI de Django.
sleep 12

# 3. RECOLECCIÓN DE EVIDENCIAS EN EL DIRECTORIO SWAP
# Auditoría de logs de acceso normalizados (minúsculas) del nodo web.
cat /var/log/miguelaetxio.pythonanywhere.com.access.log | tail -n 30 > /home/MiguelAeTxio/SWAP/access_final_audit.txt

# Auditoría de persistencia en la base de datos (Django ORM).
python3 -m dotenv run python3 - << 'DBEOF' > /home/MiguelAeTxio/SWAP/db_final_audit.txt
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'enterprise_core.settings')
django.setup()
from vox_bridge.models import CallInteraction
interaction = CallInteraction.objects.order_by('-created_at').first()
if interaction:
    print(f"CALL_SID: {interaction.call_sid}")
    print(f"FROM: {interaction.from_number}")
    print(f"STATUS: {interaction.status}")
    print(f"TIMESTAMP: {interaction.created_at}")
else:
    print("RESULT: NO_INTERACTION_FOUND")
DBEOF

# Auditoría de publicación de URL de ngrok (Estado compartido).
if [ -f /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/SESSION/NGROK_URL.txt ]; then
    cat /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/SESSION/NGROK_URL.txt > /home/MiguelAeTxio/SWAP/url_final_audit.txt
else
    echo "RESULT: NGROK_URL_FILE_MISSING" > /home/MiguelAeTxio/SWAP/url_final_audit.txt
fi

# Auditoría de logs del Sidecar (ASGI Bridge)
# Extraemos las últimas líneas para confirmar si el audio llegó al puerto 8080.
# (Este paso asume que el orquestador redirige la salida al Dashboard, 
# se intenta capturar rastro de red si ngrok reporta actividad).
curl -s http://127.0.0.1:4040/api/tunnels | python3 -m json.tool > /home/MiguelAeTxio/SWAP/ngrok_api_audit.txt
