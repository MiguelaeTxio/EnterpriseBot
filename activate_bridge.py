# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/activate_bridge.py
import os
import requests
from dotenv import load_dotenv

# Load project environment variables
# Carga de variables de entorno del proyecto
load_dotenv()

def activate_mundosms_bridge():
    """
    Injects the link Dialplan into MundoSMS using the official v0.25 documentation.
    Implements <http-request> with URL inside CDATA to avoid validation Error 3.
    ---
    Inyecta el Dialplan de enlace en MundoSMS usando la documentación oficial v0.25.
    Implementa <http-request> con la URL dentro de CDATA para evitar el Error 3.
    """
    
    # Identity and destination parameters
    # Parámetros de identidad y destino
    username = os.getenv('MUNDOSMS_USER')
    password = os.getenv('MUNDOSMS_PASS')
    did_number = os.getenv('MUNDOSMS_PILOT_NUMBER')
    
    # URL of our Webhook (The landing point for voice traffic)
    # URL de nuestro Webhook (El punto de llegada para el tráfico de voz)
    webhook_url = "https://enterprisebot-miguelaetxio.pythonanywhere.com/api/vox/inbound/"
    
    # Official Dialplan Structure (Source: API VoIP/vPBX v0.25 manual, Page 42)
    # 1. Root tag: <dialplan>
    # 2. Command: <http-request>
    # 3. Mandatory attributes for sync communication.
    # 4. URL as node value wrapped in CDATA (manufacturer recommendation).
    # Estructura de Dialplan Oficial (Fuente: Manual API VoIP/vPBX v0.25, Pág. 42)
    # 1. Tag raíz: <dialplan>
    # 2. Comando: <http-request>
    # 3. Atributos mandatorios para comunicación síncrona.
    # 4. URL como valor de nodo envuelta en CDATA (recomendación del fabricante).
    dialplan_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<dialplan>'
        '<http-request method="post" mode="sync">'
        f'<![CDATA[{webhook_url}]]>'
        '</http-request>'
        '</dialplan>'
    )
    
    print(f"# Iniciando activación del puente (Official Manual v0.25) para el número: {did_number}")
    
    # MundoSMS API endpoint for modifying DIDs
    # Endpoint de la API de MundoSMS para modificar DIDs
    api_url = "https://api.mundosms.es/APIv2/set_voipdids.php"
    
    params = {
        'username': username,
        'password': password,
        'did': did_number,
        'change_parameter': 'xml',
        'change_value': dialplan_xml
    }
    
    try:
        response = requests.get(api_url, params=params, timeout=15)
        response.raise_for_status()
        
        # Parse response using MundoSMS pipe-separated format
        # Parseo de respuesta según formato pipe-separated de MundoSMS
        data = response.text.split('|')
        status_code = data[0]
        description = data[1]
        
        if status_code == "0":
            print(f"# ÉXITO: Puente activado correctamente. Mensaje: {description}")
            print(f"# Configuración inyectada: {dialplan_xml}")
        else:
            print(f"# ERROR API: {status_code} - {description}")
            print(f"# XML rechazado por el servidor: {dialplan_xml}")
            
    except Exception as e:
        print(f"# ERROR CRÍTICO DE RED: {str(e)}")

if __name__ == "__main__":
    activate_mundosms_bridge()
