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
La especificación original era incorrecta. InboundCallView NO instancia
VoiceOrchestrationService en ningún momento — únicamente genera el TwiML
<Connect><Stream> de respuesta.

El flujo de ejecución real de una llamada entrante es:

    1. Twilio realiza POST /api/vox/inbound/
       → UniversalVoiceBridge.handle_twiml_post() en voice_sidecar_bridge.py
       → Responde con TwiML <Connect><Stream url="wss://{host}/media" />
       → VoiceOrchestrationService NO se instancia aquí.

    2. Twilio abre WebSocket GET /media
       → UniversalVoiceBridge.handle_websocket_stream()
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

Las constantes originales han sido renombradas a *_FALLBACK.

#### run_voice_session()
Referencias a constantes globales sustituidas por atributos de instancia:
    SYSTEM_INSTRUCTION        →  self.system_instruction
    INITIAL_GREETING_TEXT     →  self.initial_greeting_text

### Cambios implementados en voice_sidecar_bridge.py

#### UniversalVoiceBridge.handle_websocket_stream()
- Instanciación de VoiceOrchestrationService diferida al evento 'start'.
- service y voice_task se inicializan a None al inicio del método.
- Todos los manejadores posteriores ('media', 'stop', CLOSED, ERROR)
  incluyen guardia defensiva (if service is not None).
- El bloque finally comprueba voice_task is not None antes de cancelarla.

### vox_bridge/views.py — Sin modificación
InboundCallView no forma parte del flujo de instanciación del servicio.

## 4. Fallback de Seguridad / Safety Fallback

    try:
        system_instruction, initial_greeting = build_live_config(twilio_number)
    except Exception:
        logger.error(f"[CONFIG] No se pudo cargar config para {twilio_number}. Usando fallback.")
        system_instruction = SYSTEM_INSTRUCTION_FALLBACK
        initial_greeting = INITIAL_GREETING_FALLBACK

Las constantes *_FALLBACK se definen en vox_bridge/services.py con la
configuración de Alia/Grupo Álvarez como red de seguridad.
