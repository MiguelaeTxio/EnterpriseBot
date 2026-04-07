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

## 3. Impacto en vox_bridge/services.py

### Cambios en VoiceOrchestrationService.__init__()
Añadir parámetro twilio_number: str al constructor.
Llamar a build_live_config(twilio_number) y almacenar el resultado:
    self.system_instruction, self.initial_greeting_text = build_live_config(twilio_number)

### Cambios en run_voice_session()
Sustituir referencias a las constantes globales por los atributos de instancia:
    SYSTEM_INSTRUCTION        →  self.system_instruction
    INITIAL_GREETING_TEXT     →  self.initial_greeting_text

### Cambios en vox_bridge/views.py (InboundCallView)
Al instanciar VoiceOrchestrationService, extraer el número Twilio del
parámetro To del POST de Twilio y pasarlo al constructor:
    twilio_number = request.POST.get('To', '')
    service = VoiceOrchestrationService(twilio_number=twilio_number)

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
