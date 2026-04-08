# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/DOCS_ATTACHED_2_ANNEX_V03/V03DOC_DYNAMIC_IVR_INJECTION.md

# INYECCIÓN DINÁMICA DE CONFIGURACIÓN IVR
# DYNAMIC IVR CONFIGURATION INJECTION
---
# Especificación del mecanismo de carga dinámica de configuración desde BD.
# Specification of the dynamic configuration loading mechanism from the database.

## 1. Problema Actual / Current Problem

En la implementación actual del Hito 1, la configuración del IVR está
completamente hardcodeada en vox_bridge/services.py:

    SYSTEM_INSTRUCTION = "Eres Alia, la asistente virtual del Grupo Álvarez..."
    INITIAL_GREETING_TEXT = "El llamante acaba de contestar..."

Este enfoque impide la operación multiempresa y la configuración desde producción.

## 2. Solución: Cargador Dinámico / Solution: Dynamic Loader

Se implementa ivr_config/services.py con la función build_live_config():

    def build_live_config(twilio_number: str) -> tuple[str, str]:
        """
        Builds the dynamic SYSTEM_INSTRUCTION and INITIAL_GREETING for a call.
        ---
        Construye el SYSTEM_INSTRUCTION e INITIAL_GREETING dinámicos para una llamada.

        Args:
            twilio_number: The Twilio number that received the call (E.164 format).
        Returns:
            Tuple of (system_instruction, initial_greeting).
        Raises:
            PhoneNumber.DoesNotExist: if no active PhoneNumber matches.
            CallFlow.DoesNotExist: if the PhoneNumber has no active CallFlow.
        """

Lógica interna:
1. Obtener PhoneNumber activo por twilio_number.
2. Obtener CallFlow asociado.
3. Obtener CorporateVoiceProfile de la Company.
4. Consultar PresenceStatus activo de todos los Contact internos de la Company.
5. Construir presence_context:
       presence_lines = []
       for contact in internal_contacts:
           status = get_active_presence(contact.company_user)
           if status.status == 'IN_MEETING':
               presence_lines.append(f"{contact.name} está actualmente reunido/a.")
           elif status.status == 'ABSENT_VACATION':
               presence_lines.append(f"{contact.name} está de vacaciones hasta {status.ends_at}.")
           ...
6. Ensamblar system_instruction:
       system_instruction = (
           call_flow.system_instruction
           + "\n\nPERFIL CORPORATIVO:\n" + voice_profile.tone_guidelines
           + "\n\nESTADO DE PRESENCIA ACTUAL:\n" + "\n".join(presence_lines)
       )
7. Retornar (system_instruction, call_flow.initial_greeting).

## 3. Impacto real en el código — Flujo de ejecución corregido

### CORRECCIÓN ARQUITECTÓNICA (sesión 2026-04-08)
La especificación original de esta sección era incorrecta. Identificaba
vox_bridge/views.py (InboundCallView) como el punto de instanciación de
VoiceOrchestrationService. El análisis del código real durante la sesión
de implementación reveló que InboundCallView no instancia el servicio en
ningún momento — únicamente genera el TwiML <Connect><Stream> de respuesta.

El flujo de ejecución real de una llamada entrante es el siguiente:

    1. Twilio realiza POST /api/vox/inbound/
       → UniversalVoiceBridge.handle_twiml_post() en voice_sidecar_bridge.py
       → Responde con TwiML <Connect><Stream url="wss://{host}/media" />
       → El número 'To' está disponible aquí en el body del POST de aiohttp,
         pero VoiceOrchestrationService aún no se instancia en este punto.

    2. Twilio abre WebSocket GET /media
       → UniversalVoiceBridge.handle_websocket_stream() en voice_sidecar_bridge.py
       → Se inicia el bucle lector de eventos de Twilio.
       → VoiceOrchestrationService NO se instancia todavía.

    3. Twilio envía evento 'start' por el WebSocket
       → handle_websocket_stream() extrae twilio_number de:
             data["start"]["to"] o data["start"]["To"]
       → En este momento se instancia VoiceOrchestrationService:
             service = VoiceOrchestrationService(twilio_number=twilio_number)
       → Se lanza run_voice_session() como asyncio.Task concurrente.
       → Se almacena el streamSid via service.set_stream_sid(stream_sid).

    4. Twilio envía eventos 'media' sucesivos
       → Se reenvían a service.receive_twilio_audio() para transcodificación
         y encolado hacia Gemini Live.

    5. Twilio envía evento 'stop'
       → service.terminate_session() señaliza el fin de sesión.

### Cambios implementados en vox_bridge/services.py

#### VoiceOrchestrationService.__init__()
Añadido parámetro twilio_number: str (default "") al constructor.
Llamada a build_live_config(twilio_number) con fallback de seguridad:
    try:
        from ivr_config.services import build_live_config
        self.system_instruction, self.initial_greeting_text = (
            build_live_config(twilio_number)
        )
    except Exception:
        self.system_instruction = SYSTEM_INSTRUCTION_FALLBACK
        self.initial_greeting_text = INITIAL_GREETING_FALLBACK

Las constantes originales SYSTEM_INSTRUCTION e INITIAL_GREETING_TEXT han
sido renombradas a SYSTEM_INSTRUCTION_FALLBACK e INITIAL_GREETING_FALLBACK.

#### run_voice_session()
Referencias a las constantes globales sustituidas por atributos de instancia:
    SYSTEM_INSTRUCTION        →  self.system_instruction
    INITIAL_GREETING_TEXT     →  self.initial_greeting_text

### Cambios implementados en voice_sidecar_bridge.py

#### UniversalVoiceBridge.handle_websocket_stream()
- La instanciación de VoiceOrchestrationService se ha diferido desde el
  inicio del método hasta el interior del manejador del evento 'start',
  donde el número Twilio 'to' está disponible en el payload WebSocket.
- service y voice_task se inicializan a None al inicio del método y se
  asignan dentro del manejador de 'start'.
- Todos los manejadores de eventos posteriores ('media', 'stop', CLOSED,
  ERROR) incluyen guardia defensiva (if service is not None) para el caso
  extremo en que el WebSocket se cierre antes de recibir el evento 'start'.
- La guardia del bloque finally comprueba voice_task is not None antes de
  intentar cancelarla.

### vox_bridge/views.py — Sin modificación
InboundCallView no forma parte del flujo de instanciación del servicio
y no ha sido modificada en este hito. Su única responsabilidad es generar
el TwiML <Connect><Stream> de respuesta al POST inicial de Twilio cuando
el sistema opera en modo Django WSGI (no aplica al bridge aiohttp activo).

## 4. Fallback de Seguridad / Safety Fallback

Si build_live_config() lanza una excepción (número no configurado, sin CallFlow),
el sistema cae al comportamiento de demo hardcodeado para no dejar
al llamante sin respuesta:

    try:
        system_instruction, initial_greeting = build_live_config(twilio_number)
    except Exception:
        logger.error(f"[CONFIG] No se pudo cargar config para {twilio_number}. Usando fallback.")
        system_instruction = SYSTEM_INSTRUCTION_FALLBACK
        initial_greeting = INITIAL_GREETING_FALLBACK

Las constantes SYSTEM_INSTRUCTION_FALLBACK e INITIAL_GREETING_FALLBACK se
definen en vox_bridge/services.py y contienen la configuración actual de
Alia/Grupo Álvarez como red de seguridad.
