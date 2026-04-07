# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/DOCS_ATTACHED_2_ANNEX_V01/API_HANDSHAKE_PROTOCOL.md

# PROTOCOLO DE DOBLE HANDSHAKE (HTTP/WSS)
# DOUBLE HANDSHAKE PROTOCOL (HTTP/WSS)
---
# Gestión de la separación de métodos HTTP y actualización de protocolos.
# Management of HTTP method separation and protocol upgrades.

## 1. El Problema del Handshake Único / The Single Handshake Problem
En infraestructuras como PythonAnywhere, los servidores WSGI tradicionales no soportan el "Upgrade" a WebSocket de forma nativa en el mismo puerto que las peticiones HTTP estándar. Intentar manejar ambos en una sola ruta provoca el error `Unsupported HTTP Method: GET`.
In infrastructures like PythonAnywhere, traditional WSGI servers do not natively support WebSocket "Upgrade" on the same port as standard HTTP requests. Attempting to handle both on a single route causes the `Unsupported HTTP Method: GET` error.

## 2. La Solución: Separación de Responsabilidades / The Solution: Separation of Concerns
Implementamos un protocolo de doble fase:
We implement a two-phase protocol:

### Fase A: Handshake de Control (Django)
- **Endpoint:** `/api/vox/inbound/` (POST)
- **Actor:** `vox_bridge.views.InboundCallView`
- **Función:** Recibir la notificación de llamada de Twilio y responder con instrucciones TwiML. El campo `<Stream url="wss://...">` redirige el flujo de audio al Sidecar Bridge.

### Fase B: Handshake de Datos (Sidecar)
- **Endpoint:** `/media` (GET/Upgrade)
- **Actor:** `UniversalVoiceBridge` (aiohttp)
- **Función:** Realizar el upgrade de HTTP a WebSocket. Una vez establecido, se inicia el streaming binario de audio.

## 3. Ciclo de Vida del SDK 1.69.0 / SDK 1.69.0 Lifecycle
La conexión con Gemini NO se realiza al iniciar el bridge, sino al establecer el WebSocket con Twilio.
The connection with Gemini is NOT established when starting the bridge, but when establishing the WebSocket with Twilio.

```python
async with client.aio.live.connect(model=MODEL, config=CONFIG) as session:
    # La entrada exitosa garantiza el handshake con Google.
    # Successful entry guarantees the handshake with Google.
    ...
```
