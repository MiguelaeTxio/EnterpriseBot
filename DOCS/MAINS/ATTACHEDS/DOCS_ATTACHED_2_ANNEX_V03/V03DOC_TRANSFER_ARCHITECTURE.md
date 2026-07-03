# ARQUITECTURA DE TRANSFERENCIA DE LLAMADA Y AUDIO EXPERIENCIAL
# CALL TRANSFER ARCHITECTURE AND EXPERIENTIAL AUDIO
---
# Última actualización / Last update: 2026-04-17

## 1. Visión General / Overview

La arquitectura opera en tres fases que sustituyen el modelo de
"notificación saliente" por una transferencia real de la llamada:

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
        Alia queda desconectada.

    FASE 3B — Transferencia fallida (no responde):
        El action webhook reactiva el bridge.
        Alia retoma la llamada (nuevo Media Stream).
        Informa al llamante. Ofrece dejar un mensaje de voz.
        Se registra PendingNotification en BD.

---

## 2. Flujo Técnico Detallado

### 2.1. FASE 1 — Audio de Bienvenida e Identificación de Sección

#### Audio de introducción (3-5 segundos antes del saludo de Alia)

TwiML de respuesta en handle_twiml_post():
    <?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Play>https://{host}/static/audio/intro.mp3</Play>
        <Connect>
            <Stream url="wss://{host}/media" />
        </Connect>
    </Response>

Requisitos del archivo intro.mp3:
    - Formato: MP3 o WAV.
    - Duración: 3-5 segundos.
    - Ruta sugerida: vox_bridge/static/vox_bridge/audio/intro.mp3

#### Identificación de sección (function calling route_to_section)

build_live_config() inyecta en el system_instruction:
    - DISPONIBILIDAD ACTUAL DE SECCIONES (horarios dinámicos).
    - ESTADO DE PRESENCIA ACTUAL DEL PERSONAL.
    - IDENTIFICADORES DE SECCIÓN (tabla section_pk → section_name).

Cuando Alia identifica la intención del llamante, invoca:
    route_to_section(section_id: int)

Handler en _receive_gemini_audio():
    1. Captura el tool_call.
    2. Llama a _reload_session_for_section(session, section_id).
    3. Responde con tool_response al modelo.
    4. Alia continúa con el CallFlow específico de la sección.

---

### 2.2. FASE 2 — Transferencia Real vía Dial Conference

#### Decisión arquitectónica: <Dial><Conference> vs <Dial><Number>

Se usa <Dial><Conference> por dos razones:
    1. MÚSICA EN ESPERA: waitUrl permite audio personalizado.
    2. CONTROL POST-TRANSFERENCIA: el bridge puede gestionar el fallo.

#### TwiML de transferencia (servido por /api/vox/transfer/{section_id}/):

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

NOTA CRÍTICA: Con <Connect><Stream>, Twilio NO ejecuta instrucciones
posteriores mientras el WebSocket esté activo. El cierre del WebSocket
desde el servidor es el único mecanismo de salida del Media Stream.

#### Música en espera — /api/vox/hold_music/

    <?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Play loop="0">https://{host}/static/audio/hold.mp3</Play>
    </Response>

Requisitos hold.mp3:
    - Formato: MP3.
    - Duración: mínimo 30 segundos (loop="0" lo repite).
    - Ruta sugerida: vox_bridge/static/vox_bridge/audio/hold.mp3

#### Llamada saliente al responsable

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

Números IE1 (españoles): usar credenciales TWILIO_API_KEY_SID_IE1 / TWILIO_API_KEY_SECRET_IE1.

---

### 2.3. FASE 3B — Transferencia Fallida

El timeout de <Dial> (30s) expira. Twilio hace POST a /api/vox/transfer_status/{call_sid}/

El bridge:
    1. Reconecta a Alia con un nuevo Media Stream bidireccional.
    2. Alia informa: "Lo sentimos, el responsable no está disponible."
    3. Alia ofrece dejar un mensaje de voz.
    4. Si acepta → Twilio <Record>.
    5. Se registra PendingNotification en BD.

#### Modelo PendingNotification (Paso 40)

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

---

## 3. Endpoints Necesarios

    /api/vox/transfer/{section_id}/        → TransferCallView
    /api/vox/hold_music/                   → HoldMusicView
    /api/vox/transfer_status/{call_sid}/   → TransferStatusView
    /api/vox/transfer_accept/{conf_name}/  → TransferAcceptView

---

## 4. Pasos de Hoja de Ruta (39-42)

    Paso 39 — Function calling: transfer_to_section_contact
    Paso 40 — Modelo PendingNotification + Fase 3B
    Paso 41 — Audio de bienvenida (intro.mp3)
    Paso 42 — Audio de espera (hold.mp3) + HoldMusicView

---

## 5. Restricciones Críticas

- <Connect><Stream> bidireccional NO admite instrucciones TwiML posteriores
  mientras el WebSocket esté activo.
- Solo puede haber un Media Stream bidireccional activo por llamada.
- La Conference tiene coste adicional por participante por minuto (timeout 30s recomendado).
- Los archivos de audio deben estar accesibles vía URL pública.
