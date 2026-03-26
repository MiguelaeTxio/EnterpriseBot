# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/activate_bridge.py
import os
import requests
from dotenv import load_dotenv

# Carga de variables de entorno del proyecto
# Load project environment variables
load_dotenv()

def activate_mundosms_bridge():
    """
    Inyecta el Dialplan de enlace en MundoSMS para conectar el DID con Django.
    Injects the link Dialplan into MundoSMS to connect the DID with Django.
    """
    
    # Parámetros de identidad y destino
    username = os.getenv('MUNDOSMS_USER')
    password = os.getenv('MUNDOSMS_PASS')
    did_number = os.getenv('MUNDOSMS_PILOT_NUMBER')
    
    # URL de nuestro Webhook (El punto de llegada para el tráfico de voz)
    webhook_url = "https://enterprisebot-miguelaetxio.pythonanywhere.com/api/vox/inbound/"
    
    # Dialplan Maestro: Instruye a MundoSMS a delegar el control en nuestro servidor
    # Master Dialplan: Instructs MundoSMS to delegate control to our server
    dialplan_xml = f'<?xml version="1.0" encoding="UTF-8"?><dialplan><http-request url="{webhook_url}" method="post" mode="sync"/></dialplan>'
    
    print(f"# Iniciando activación del puente para el número: {did_number}")
    
    # Endpoint de la API de MundoSMS para modificar DIDs (vPBX v0.25, Pág. 23)
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
        
        # Parseo de respuesta según formato pipe-separated de MundoSMS
        # Response parsing according to MundoSMS pipe-separated format
        data = response.text.split('|')
        status_code = data[0]
        description = data[1]
        
        if status_code == "0":
            print(f"# ÉXITO: Puente activado correctamente. Mensaje: {description}")
            print(f"# La llamada al {did_number} ahora será atendida por EnterpriseBot.")
        else:
            print(f"# ERROR API: {status_code} - {description}")
            
    except Exception as e:
        print(f"# ERROR CRÍTICO DE RED: {str(e)}")

if __name__ == "__main__":
    activate_mundosms_bridge()
