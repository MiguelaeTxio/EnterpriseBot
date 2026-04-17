# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/DOCS_ATTACHED_2_ANNEX_V03/V03DOC_TRANSFER_ARCHITECTURE.md

# ARQUITECTURA DE TRANSFERENCIA DE LLAMADA Y AUDIO EXPERIENCIAL
# CALL TRANSFER ARCHITECTURE AND EXPERIENTIAL AUDIO
---
# Especificación técnica completa del mecanismo de transferencia real de llamada
# vía Twilio Dial, incluyendo audio de bienvenida, música en espera y gestión
# del flujo tras fallo de transferencia.
# Complete technical specification of the real call transfer mechanism via Twilio
# Dial, including welcome audio, hold music and post-transfer failure flow management.
#
# Última actualización / Last update: 2026-04-17

---

## 1. Visión General / Overview

La arquitectura de transferencia de llamada de EnterpriseBot opera en tres fases
diferenciadas que sustituyen el modelo original de "notificación saliente" por una
**transferencia real** de la llamada al responsable de sección:

    FASE 1 — Bienvenida (CallFlow general):
        Alia saluda al llamante con audio de introducción previo.
        Identifica la sección destino mediante function calling (route_to_section).
        Carga el CallFlow específico de la sección.

    FASE 2 — Transferencia (CallFlow de sección):
        Alia informa al llamante de que va a transferirle.
        El bridge termina el Media Stream de Gemini Live.
        Twilio ejecuta <Dial><Conference> con música en espera.
        El bridge llama al responsable mediante la API REST de Twilio.
        Si el responsable responde → se une a la Conference → conversación directa.
        Si el responsable no responde → Twilio dispara action webhook.

    FASE 3A — Transferencia exitosa:
        Llamante y responsable conectados en la Conference.
        Alia queda desconectada. La llamada continúa sin intervención del bridge.

    FASE 3B — Transferencia fallida (no responde):
        El action webhook reactiva el bridge.
        Alia retoma la llamada (nuevo Media Stream).
        Informa al llamante. Ofrece dejar un mensaje de voz.
        Se registra PendingNotification en BD (stub WhatsApp).

---

## 2. Flujo Técnico Detallado / Detailed Technical Flow

### 2.1. FASE 1 — Audio de Bienvenida e Identificación de Sección

#### 2.1.1. Audio de introducción (3-5 segundos antes del saludo de Alia)

El webhook `/api/vox/inbound/` responde con TwiML en dos pasos:

    1. <Play> — reproduce el archivo de música de introducción (3-5s).
    2. <Connect><Stream> — arranca el Media Stream bidireccional con Alia.

Implementación en handle_twiml_post() de voice_sidecar_bridge.py:

    TwiML de respuesta:
    <?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Play>https://{host}/static/audio/intro.mp3</Play>
        <Connect>
            <Stream url="wss://{host}/media" />
        </Connect>
    </Response>

Requisitos del archivo de audio:
    - Formato: MP3 o WAV (Twilio lo recodifica internamente).
    - Duración: 3-5 segundos.
    - Contenido: música corporativa o jingle de bienvenida.
    - Alojamiento: static files de Django (collectstatic) o URL pública estable.
    - Ruta sugerida: /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/static/vox_bridge/audio/intro.mp3

#### 2.1.2. Identificación de sección (function calling route_to_section)

Una vez activo el Media Stream, Alia opera con el CallFlow general.
build_live_config() inyecta en el system_instruction:
    - DISPONIBILIDAD ACTUAL DE SECCIONES (horarios dinámicos).
    - ESTADO DE PRESENCIA ACTUAL DEL PERSONAL.
    - IDENTIFICADORES DE SECCIÓN (tabla section_pk → section_name para function calling).

Cuando Alia identifica la intención del llamante, invoca:
    route_to_section(section_id: int)

El handler en _receive_gemini_audio() de vox_bridge/services.py:
    1. Captura el tool_call.
    2. Llama a _reload_session_for_section(session, section_id).
    3. Responde con tool_response al modelo.
    4. Alia continúa con el CallFlow específico de la sección.

---

### 2.2. FASE 2 — Transferencia Real vía Dial Conference

#### 2.2.1. Decisión arquitectónica: <Dial><Conference> vs <Dial><Number>

Se usa <Dial><Conference> en lugar de <Dial><Number> directo por dos razones:

    1. MÚSICA EN ESPERA: <Dial><Conference> con waitUrl permite reproducir
       música personalizada al llamante mientras espera que el responsable
       se una. <Dial><Number> directo solo reproduce el tono de llamada estándar.

    2. CONTROL POST-TRANSFERENCIA: Con Conference, el bridge puede unirse
       programáticamente a la sala y gestionar el flujo tras el fallo.
       Con <Dial><Number> el control es más limitado.

#### 2.2.2. Cierre del Media Stream y emisión del TwiML de transferencia

Cuando el CallFlow de sección instruye a Alia para transferir:

    1. Alia informa al llamante verbalmente ("Le voy a transferir con el
       responsable de [sección], por favor espere un momento").
    2. El bridge detecta la señal de transferencia (function calling
       transfer_to_section_contact — Paso 39).
    3. El bridge cierra el WebSocket del Media Stream desde el servidor.
       Twilio ejecuta las instrucciones TwiML siguientes al <Connect><Stream>.
       NOTA: Con <Connect><Stream>, Twilio NO ejecuta instrucciones posteriores
       a menos que el WebSocket se cierre desde el servidor. El cierre del
       WebSocket es el mecanismo de salida del Media Stream.
    4. El bridge actualiza la llamada vía REST API de Twilio con nuevo TwiML:
       POST /2010-04-01/Accounts/{AccountSid}/Calls/{CallSid}.json
       con Twiml= o Url= apuntando a /api/vox/transfer/{section_id}/

    TwiML de transferencia (servido por /api/vox/transfer/{section_id}/):
    <?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Dial action="/api/vox/transfer_status/{call_sid}/" method="POST"
              timeout="30">
            <Conference waitUrl="/api/vox/hold_music/"
                        waitMethod="GET"
                        startConferenceOnEnter="false"
                        endConferenceOnExit="true"
                        beep="false">
                EnterpriseBot-{call_sid}
            </Conference>
        </Dial>
    </Response>

    El llamante entra en la Conference y escucha la música de espera.
    El bridge llama al responsable via REST API (llamada saliente independiente).
    El responsable recibe: TwiML que lo une a la misma Conference.

#### 2.2.3. Música en espera — /api/vox/hold_music/

Endpoint Django que devuelve TwiML con <Play> en bucle:

    <?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Play loop="0">https://{host}/static/audio/hold.mp3</Play>
    </Response>

Requisitos del archivo de audio:
    - Formato: MP3 (preferido por Twilio para caching).
    - Duración: mínimo 30 segundos (loop="0" lo repite indefinidamente).
    - Contenido: música instrumental de espera, sin voz.
    - Ruta sugerida: /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/static/vox_bridge/audio/hold.mp3
    - Alojamiento: static files de Django o URL pública con headers de caché apropiados.

#### 2.2.4. Llamada saliente al responsable

El bridge realiza una llamada saliente via REST API de Twilio al Contact responsable
de la sección. La llamada incluye TwiML que une al responsable a la Conference:

    Cliente Twilio (IE1 para números españoles):
        client.calls.create(
            to=contact.phone_number,
            from_=twilio_number,
            twiml="""
            <Response>
                <Say>Llamada entrante de EnterpriseBot. Pulse 1 para aceptar.</Say>
                <Gather numDigits="1" action="/api/vox/transfer_accept/{conference_name}/">
                </Gather>
            </Response>
            """
        )

    Si el responsable pulsa 1 → se une a la Conference → conversación directa.
    Si no responde / rechaza → el timeout del <Dial> dispara el action webhook.

---

### 2.3. FASE 3A — Transferencia Exitosa

El responsable acepta y se une a la Conference (startConferenceOnEnter=true en
su TwiML de unión). La música de espera cesa. Llamante y responsable conversan
directamente. Twilio gestiona la llamada sin intervención del bridge.

Cuando cualquiera de los dos cuelga, la Conference termina
(endConferenceOnExit=true en el TwiML del llamante).

---

### 2.4. FASE 3B — Transferencia Fallida

El timeout de <Dial> (30 segundos) expira sin que el responsable conteste.
Twilio realiza POST al action URL: /api/vox/transfer_status/{call_sid}/

El bridge:
    1. Reconecta a Alia con un nuevo Media Stream bidireccional.
    2. Alia informa al llamante: "Lo sentimos, el responsable no está disponible
       en este momento."
    3. Alia ofrece dejar un mensaje de voz: "¿Desea dejar un mensaje de voz
       para que le devuelvan la llamada?"
    4. Si el llamante acepta → Alia graba el mensaje (Twilio <Record>).
    5. Se registra un PendingNotification en BD con todos los datos.

#### 2.4.1. Modelo PendingNotification (nuevo — Paso 40)

    class PendingNotification(models.Model):
        company         ForeignKey(Company, on_delete=CASCADE)
        section         ForeignKey(Section, null=True, on_delete=SET_NULL)
        contact         ForeignKey(Contact, null=True, on_delete=SET_NULL)
        caller_number   CharField(max_length=20)
        call_sid        CharField(max_length=40)
        created_at      DateTimeField(auto_now_add=True)
        notified_at     DateTimeField(null=True, blank=True)
        channel         CharField(choices=[('WHATSAPP','WhatsApp'),
                                           ('SMS','SMS'),
                                           ('EMAIL','Email'),
                                           ('PENDING','Pendiente')],
                                  default='PENDING')
        voice_recording_url  URLField(blank=True)
        notes           TextField(blank=True)

    Cuando WhatsApp esté operativo (Hito 4), un worker de Celery procesará
    los registros con channel='PENDING' y los convertirá en notificaciones reales.

---

## 3. Nuevos Endpoints Necesarios / New Required Endpoints

Todos bajo la app vox_bridge, registrados en enterprise_core/urls.py:

    /api/vox/transfer/{section_id}/
        GET/POST — Devuelve TwiML de Conference para el llamante.
        Handler: TransferCallView.

    /api/vox/hold_music/
        GET — Devuelve TwiML con <Play loop="0"> del archivo de música de espera.
        Handler: HoldMusicView.

    /api/vox/transfer_status/{call_sid}/
        POST — Webhook de Twilio cuando el <Dial> termina (action URL).
        Handler: TransferStatusView. Reactiva el Media Stream con Alia.

    /api/vox/transfer_accept/{conference_name}/
        POST — El responsable pulsa 1. Le une a la Conference.
        Handler: TransferAcceptView.

---

## 4. Nuevos Pasos en la Hoja de Ruta / New Roadmap Steps

    Paso 39 — Function calling: transfer_to_section_contact
        Definir tool transfer_to_section_contact(section_id: int) en LiveConnectConfig.
        Handler en _receive_gemini_audio(): cierra WebSocket, actualiza Call con TwiML
        de transferencia, realiza llamada saliente al contacto responsable.
        Criterio de éxito: llamada real en la que Alia inicia la transferencia y el
        llamante escucha la música de espera mientras suena el teléfono del responsable.

    Paso 40 — Modelo PendingNotification + Fase 3B
        Crear modelo PendingNotification en ivr_config/models.py.
        Implementar TransferStatusView: reactiva Alia, ofrece mensaje de voz, registra
        PendingNotification. Criterio de éxito: llamada con responsable no disponible
        queda registrada en BD con los datos del llamante.

    Paso 41 — Audio de bienvenida (intro.mp3)
        Seleccionar o producir archivo de audio intro.mp3 (3-5s).
        Añadir <Play> al TwiML de handle_twiml_post() antes de <Connect><Stream>.
        Criterio de éxito: el llamante escucha la música antes de que Alia salude.

    Paso 42 — Audio de espera (hold.mp3) + HoldMusicView
        Seleccionar o producir archivo de audio hold.mp3 (>30s, instrumental).
        Implementar HoldMusicView y registrar /api/vox/hold_music/.
        Criterio de éxito: el llamante escucha música personalizada durante la espera.

---

## 5. Restricciones y Consideraciones / Constraints and Considerations

- <Connect><Stream> bidireccional NO admite instrucciones TwiML posteriores mientras
  el WebSocket esté activo. El cierre del WebSocket desde el servidor es el único
  mecanismo de salida del Media Stream.
- Solo puede haber un Media Stream bidireccional activo por llamada. La reconexión
  de Alia en Fase 3B requiere cerrar el Stream anterior completamente.
- El archivo intro.mp3 se reproduce ANTES de que arranque el Media Stream — no
  requiere ningún cambio en el bridge de audio, solo en el TwiML de respuesta inicial.
- La Conference de Twilio tiene coste adicional por participante por minuto. Para
  minimizarlo, el timeout del <Dial> debe ser ajustado (30s recomendado).
- Los archivos de audio estáticos deben estar accesibles vía URL pública. En
  PythonAnywhere, los static files se sirven directamente desde el WSGI app.
- Para números IE1 (españoles), las llamadas salientes al responsable deben usar
  las credenciales IE1 (TWILIO_API_KEY_SID_IE1 / TWILIO_API_KEY_SECRET_IE1).
