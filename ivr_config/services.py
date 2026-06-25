# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/services.py
"""
Dynamic IVR configuration loader for the ivr_config multicompany engine.

This module implements build_live_config(), the central function that resolves
the active Gemini Live session configuration for an inbound call. Given the
Twilio E.164 number that received the call, it queries the database to load
the associated CallFlow, CorporateVoiceProfile and active PresenceStatus
records for all internal contacts, and assembles the complete system_instruction
and initial_greeting strings to be injected into the Gemini Live session.

A safety fallback mechanism is provided: if any database query fails (e.g. the
number is not yet configured, or the CallFlow is missing), the function raises
a well-typed exception that the caller must catch and handle by falling back
to hardcoded constants.
---
Cargador dinámico de configuración IVR para el motor multiempresa ivr_config.

Este módulo implementa build_live_config(), la función central que resuelve
la configuración de sesión de Gemini Live activa para una llamada entrante.
Dado el número Twilio en formato E.164 que recibió la llamada, consulta la
base de datos para cargar el CallFlow asociado, el CorporateVoiceProfile y
los registros PresenceStatus activos de todos los contactos internos, y
ensambla las cadenas system_instruction e initial_greeting completas que se
inyectarán en la sesión de Gemini Live.

Se proporciona un mecanismo de fallback de seguridad: si alguna consulta a
la base de datos falla (p. ej. el número aún no está configurado, o falta
el CallFlow), la función lanza una excepción tipada que el llamante debe
capturar y gestionar cayendo a las constantes hardcodeadas.
"""

import logging

from django.db import connection
from django.db.models import Q
from django.utils.timezone import now

from ivr_config.models import (
    BlockedCaller,
    CallFlow,
    Contact,
    PhoneNumber,
    PresenceStatus,
    Section,
    SectionSchedule,
)

# ---------------------------------------------------------------------------
# LOGGING CONFIGURATION / CONFIGURACIÓN DE LOGGING
# ---------------------------------------------------------------------------
# Module-level logger for structured, traceable output from the config loader.
# Logger de módulo para salida estructurada y trazable desde el cargador de config.
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PRESENCE STATUS LABELS / ETIQUETAS DE ESTADO DE PRESENCIA
# ---------------------------------------------------------------------------
# Human-readable Spanish labels for each PresenceStatus value, used when
# assembling the presence context block injected into the system_instruction.
# Etiquetas legibles en castellano para cada valor de PresenceStatus, usadas
# al ensamblar el bloque de contexto de presencia inyectado en system_instruction.

_PRESENCE_LABEL_MAP = {
    PresenceStatus.STATUS_AVAILABLE:        "está disponible",
    PresenceStatus.STATUS_IN_MEETING:       "está actualmente reunido/a",
    PresenceStatus.STATUS_BUSY_UNTIL:       "está ocupado/a hasta",
    PresenceStatus.STATUS_ABSENT_SCHEDULED: "está ausente de forma programada",
    PresenceStatus.STATUS_ABSENT_VACATION:  "está de vacaciones",
}


# ---------------------------------------------------------------------------
# INTERNAL HELPERS / FUNCIONES DE APOYO INTERNAS
# ---------------------------------------------------------------------------

def _get_active_presence(company_user) -> PresenceStatus | None:
    """
    Returns the single active PresenceStatus for the given CompanyUser,
    or None if no active record exists.

    A PresenceStatus is considered ACTIVE if:
        starts_at <= now() AND (ends_at IS NULL OR ends_at > now())

    This is the canonical query defined in V03DOC_PRESENCE_SYSTEM.md.

    Args:
        company_user: A CompanyUser instance.

    Returns:
        The active PresenceStatus instance, or None.
    ---
    Devuelve el único PresenceStatus activo para el CompanyUser dado,
    o None si no existe ningún registro activo.

    Un PresenceStatus se considera ACTIVO si:
        starts_at <= now() AND (ends_at IS NULL OR ends_at > now())

    Esta es la consulta canónica definida en V03DOC_PRESENCE_SYSTEM.md.

    Args:
        company_user: Una instancia de CompanyUser.

    Returns:
        La instancia de PresenceStatus activa, o None.
    """
    current_time = now()
    return (
        PresenceStatus.objects
        .filter(company_user=company_user)
        .filter(starts_at__lte=current_time)
        .filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=current_time)
        )
        .order_by("-starts_at")
        .first()
    )


def _build_presence_context(company) -> str:
    """
    Queries all internal contacts of the given company and assembles a
    human-readable Spanish paragraph describing the current availability
    status of each one, suitable for injection into the Gemini system_instruction.

    Only contacts with is_internal=True and a linked company_user are included.
    Contacts without a linked company_user are skipped with a warning log.

    If no internal contacts exist for the company, an empty string is returned
    and no presence block is appended to the system_instruction.

    Args:
        company: A Company instance.

    Returns:
        A multiline string with one presence line per internal contact,
        or an empty string if no internal contacts are found.
    ---
    Consulta todos los contactos internos de la empresa dada y ensambla
    un párrafo legible en castellano que describe el estado de disponibilidad
    actual de cada uno, adecuado para su inyección en el system_instruction
    de Gemini.

    Solo se incluyen los contactos con is_internal=True y un company_user
    vinculado. Los contactos sin company_user vinculado se omiten con un
    log de advertencia.

    Si la empresa no tiene contactos internos, se devuelve una cadena vacía
    y no se añade ningún bloque de presencia al system_instruction.

    Args:
        company: Una instancia de Company.

    Returns:
        Una cadena multilínea con una línea de presencia por contacto interno,
        o una cadena vacía si no se encuentran contactos internos.
    """
    internal_contacts = (
        Contact.objects
        .filter(company=company, is_internal=True)
        .select_related("company_user")
        .order_by("name")
    )

    if not internal_contacts.exists():
        logger.info(
            f"[CONFIG] La empresa '{company.name}' no tiene contactos internos. "
            "No se generará bloque de presencia."
        )
        return ""

    presence_lines = []

    for contact in internal_contacts:
        if contact.company_user is None:
            # is_internal=True but no company_user linked — data integrity issue.
            # Log the warning and skip this contact gracefully.
            # is_internal=True pero sin company_user vinculado — problema de integridad.
            # Registrar la advertencia y omitir este contacto de forma elegante.
            logger.warning(
                f"[CONFIG] El contacto interno '{contact.name}' (id={contact.pk}) "
                f"de la empresa '{company.name}' no tiene company_user vinculado. "
                "Se omite de la generación del contexto de presencia."
            )
            continue

        presence = _get_active_presence(contact.company_user)

        if presence is None:
            # No active PresenceStatus — treat as AVAILABLE by convention.
            # Sin PresenceStatus activo — tratar como AVAILABLE por convención.
            line = f"{contact.name} está disponible."
        elif presence.status == PresenceStatus.STATUS_BUSY_UNTIL:
            # BUSY_UNTIL includes the end time for IVR context.
            # BUSY_UNTIL incluye la hora de fin para el contexto del IVR.
            if presence.ends_at:
                ends_at_str = presence.ends_at.strftime("%H:%M")
                line = f"{contact.name} está ocupado/a hasta las {ends_at_str}."
            else:
                line = f"{contact.name} está ocupado/a."
        elif presence.status in (
            PresenceStatus.STATUS_ABSENT_SCHEDULED,
            PresenceStatus.STATUS_ABSENT_VACATION,
        ):
            # Absences include the end date if defined.
            # Las ausencias incluyen la fecha de fin si está definida.
            label = _PRESENCE_LABEL_MAP.get(presence.status, "no está disponible")
            if presence.ends_at:
                ends_at_str = presence.ends_at.strftime("%-d de %B")
                line = f"{contact.name} {label} hasta el {ends_at_str}."
            else:
                line = f"{contact.name} {label}."
        else:
            # STATUS_AVAILABLE or STATUS_IN_MEETING — use the label map directly.
            # STATUS_AVAILABLE o STATUS_IN_MEETING — usar el mapa de etiquetas directamente.
            label = _PRESENCE_LABEL_MAP.get(presence.status, "está disponible")
            line = f"{contact.name} {label}."

        presence_lines.append(line)
        logger.debug(
            f"[CONFIG] Presencia resuelta para '{contact.name}': {line}"
        )

    return "\n".join(presence_lines)


def _is_caller_blocked(company, caller_number: str) -> bool:
    """
    Returns True if the caller's phone number has an active BlockedCaller
    record for the given company (i.e. blocked_until > now()).
    If caller_number is empty, returns False — the check is skipped entirely.
    ---
    Retorna True si el numero del llamante tiene un registro BlockedCaller activo
    para la empresa dada (es decir, blocked_until > now()).
    Si caller_number esta vacio, retorna False — la comprobacion se omite.
    """
    if not caller_number:
        return False
    return BlockedCaller.objects.filter(
        company=company,
        phone_number=caller_number,
        blocked_until__gt=now(),
    ).exists()


def _build_section_schedule_context(company) -> tuple[str, dict]:
    """
    Queries all active sections of the given company that have an active
    CallFlow assigned (Estrategia B — Step 37.A) and assembles:

        1. A human-readable Spanish paragraph describing the current
           availability of each qualifying section based on SectionSchedule
           records and the is_24h flag, suitable for injection into the
           Gemini system_instruction.

        2. A section_callflow_map dict mapping each qualifying Section pk
           to its associated CallFlow instance, for consumption by
           VoiceOrchestrationService._reload_session_for_section().

    Availability logic:
        - Sections with is_24h=True are always available.
        - Sections with is_24h=False are evaluated against the current
          local weekday and time using SectionSchedule records.
        - If no SectionSchedule exists for the current weekday, the section
          is considered unavailable.

    Sections without a call_flow assigned (call_flow IS NULL or inactive)
    are EXCLUDED from both the context string and the map. They are
    invisible to the IVR motor at call time.

    Args:
        company: A Company instance.

    Returns:
        tuple[str, dict]: A 2-tuple of:
            - schedule_context (str): Multiline Spanish string with one
              availability line per qualifying section, or empty string
              if no qualifying sections exist.
            - section_callflow_map (dict[int, CallFlow]): Dict mapping
              section.pk → section.call_flow for all qualifying sections.
    ---
    Consulta todas las secciones activas de la empresa que tengan un CallFlow
    activo asignado (Estrategia B — Paso 37.A) y ensambla:

        1. Un párrafo legible en castellano describiendo la disponibilidad
           actual de cada sección cualificada según sus registros
           SectionSchedule y el flag is_24h, apto para inyección en el
           system_instruction de Gemini.

        2. Un dict section_callflow_map que mapea el pk de cada Section
           cualificada a su CallFlow asociado, para consumo en
           VoiceOrchestrationService._reload_session_for_section().

    Lógica de disponibilidad:
        - Las secciones con is_24h=True están siempre disponibles.
        - Las secciones con is_24h=False se evalúan contra el día de la
          semana y hora local actuales mediante registros SectionSchedule.
        - Si no existe SectionSchedule para el día actual, la sección
          se considera no disponible.

    Las secciones sin call_flow asignado (call_flow IS NULL o inactivo)
    quedan EXCLUIDAS tanto del texto de contexto como del mapa. Son
    invisibles para el motor IVR en tiempo de llamada.

    Args:
        company: Una instancia de Company.

    Returns:
        tuple[str, dict]: Una tupla de 2 elementos:
            - schedule_context (str): Cadena multilínea en castellano con
              una línea de disponibilidad por sección cualificada, o cadena
              vacía si no existen secciones cualificadas.
            - section_callflow_map (dict[int, CallFlow]): Dict que mapea
              section.pk → section.call_flow para todas las secciones
              cualificadas.
    """
    from django.utils.timezone import localtime

    # ESTRATEGIA B — FILTRO DE SECCIONES CUALIFICADAS:
    # Solo se incluyen secciones activas con call_flow asignado Y activo.
    # Esto garantiza que el motor IVR solo expone al llamante las secciones
    # que tienen un flujo de conversación propio configurado.
    # STRATEGY B — QUALIFYING SECTIONS FILTER:
    # Only active sections with an assigned AND active call_flow are included.
    # This ensures the IVR motor only exposes to the caller sections that
    # have their own conversation flow configured.
    qualifying_sections = (
        Section.objects
        .filter(
            company=company,
            is_active=True,
            ivr_transfer_enabled=True,
            call_flow__isnull=False,
            call_flow__is_active=True,
        )
        .select_related('call_flow')
        .prefetch_related('schedules')
        .order_by('name')
    )

    if not qualifying_sections.exists():
        logger.info(
            f"[CONFIG] La empresa '{company.name}' no tiene secciones activas "
            "con CallFlow asignado. No se generará bloque de horarios ni "
            "section_callflow_map."
        )
        return "", {}

    local_now  = localtime(now())
    weekday    = local_now.weekday()
    local_time = local_now.time()

    schedule_lines: list[str] = []
    # section_callflow_map: maps section.pk → CallFlow instance.
    # section_callflow_map: mapea section.pk → instancia de CallFlow.
    section_callflow_map: dict[int, CallFlow] = {}

    for section in qualifying_sections:
        # Register this section in the map regardless of current schedule.
        # The map is used by _reload_session_for_section() to load the
        # correct CallFlow when the caller's intent is detected. Availability
        # information (open/closed/24h) is conveyed to the caller verbally
        # but does NOT prevent the section from being in the map.
        # Registrar esta sección en el mapa independientemente del horario.
        # El mapa lo usa _reload_session_for_section() para cargar el
        # CallFlow correcto cuando se detecta la intención del llamante.
        # La información de disponibilidad (abierto/cerrado/24h) se comunica
        # al llamante verbalmente pero NO impide que la sección esté en el mapa.
        section_callflow_map[section.pk] = section.call_flow

        if section.is_24h:
            schedule_lines.append(
                f"La sección '{section.name}' está disponible las 24 horas."
            )
            logger.debug(
                f"[CONFIG] Sección '{section.name}': 24h — siempre disponible."
            )
            continue

        schedules_today = section.schedules.filter(weekday=weekday)
        is_open = any(
            s.time_open <= local_time <= s.time_close
            for s in schedules_today
        )

        if schedules_today.exists():
            slots = ', '.join(
                f"{s.time_open:%H:%M}–{s.time_close:%H:%M}"
                for s in schedules_today.order_by('time_open')
            )
            if is_open:
                schedule_lines.append(
                    f"La sección '{section.name}' está disponible ahora mismo "
                    f"(horario de hoy: {slots})."
                )
                logger.debug(
                    f"[CONFIG] Sección '{section.name}': ABIERTA ({slots})."
                )
            else:
                schedule_lines.append(
                    f"La sección '{section.name}' está fuera de su horario "
                    f"en este momento (horario de hoy: {slots})."
                )
                logger.debug(
                    f"[CONFIG] Sección '{section.name}': CERRADA ({slots})."
                )
        else:
            schedule_lines.append(
                f"La sección '{section.name}' no tiene horario definido "
                "para hoy y no está disponible en este momento."
            )
            logger.debug(
                f"[CONFIG] Sección '{section.name}': sin horario para hoy."
            )

    logger.info(
        f"[CONFIG] section_callflow_map construido para '{company.name}': "
        f"{len(section_callflow_map)} sección/es cualificada/s: "
        f"{[s.name for s in qualifying_sections]}."
    )

    return "\n".join(schedule_lines), section_callflow_map


# ---------------------------------------------------------------------------
# BREAKDOWN SECTIONS CONTEXT / CONTEXTO DE SECCIONES DE AVERÍA INTERNA
# ---------------------------------------------------------------------------

def _build_breakdown_context(company) -> tuple[str, list[int]]:
    """
    Queries all active sections of the given company with
    ivr_breakdown_enabled=True and assembles a human-readable Spanish
    paragraph for injection into the system_instruction, together with
    a list of their PKs for the Gemini function call handler.

    Returns:
        tuple[str, list[int]]: A 2-tuple of:
            - breakdown_context (str): Multiline Spanish string describing
              the breakdown-enabled sections, or empty string if none.
            - breakdown_section_pks (list[int]): List of Section PKs with
              ivr_breakdown_enabled=True.
    ---
    Consulta todas las secciones activas de la empresa con
    ivr_breakdown_enabled=True y ensambla un párrafo legible en castellano
    para inyección en el system_instruction, junto con la lista de sus PKs
    para el handler de function call de Gemini.

    Returns:
        tuple[str, list[int]]: Una tupla de 2 elementos:
            - breakdown_context (str): Cadena multilínea en castellano
              describiendo las secciones habilitadas para avería, o cadena
              vacía si no hay ninguna.
            - breakdown_section_pks (list[int]): Lista de PKs de Section con
              ivr_breakdown_enabled=True.
    """
    breakdown_sections = (
        Section.objects
        .filter(
            company=company,
            is_active=True,
            ivr_breakdown_enabled=True,
        )
        .order_by('name')
    )

    if not breakdown_sections.exists():
        return "", []

    pks = list(breakdown_sections.values_list('pk', flat=True))
    names = [s.name for s in breakdown_sections]

    context = (
        "AVERÍA INTERNA DE FLOTA:\n"
        "Si el llamante reporta una avería en una máquina propia de la empresa "
        "(grúa, camión, plataforma u otro vehículo de flota), NO realices ninguna "
        "transferencia de llamada. En su lugar, sigue el flujo de captura de datos "
        "de avería descrito en este system_instruction.\n"
        f"Secciones de taller habilitadas para recepcionar averías internas: "
        f"{', '.join(names)}."
    )

    logger.debug(
        f"[CONFIG] Secciones con ivr_breakdown_enabled: {names}."
    )

    return context, pks


# ---------------------------------------------------------------------------
# PUBLIC API / API PUBLICA
# ---------------------------------------------------------------------------

def build_live_config(
    twilio_number: str,
    caller_number: str = "",
) -> tuple[str, str, str, dict]:
    """
    Builds the dynamic SYSTEM_INSTRUCTION and INITIAL_GREETING for an inbound call,
    and constructs the section_callflow_map for Estrategia B in-session routing.

    Given the Twilio E.164 number that received the call, this function:
        1. Resolves the active PhoneNumber record for that number.
        2. Loads the associated active CallFlow (general / welcome flow).
        3. Loads the CorporateVoiceProfile of the Company (if active).
        4. Queries the active PresenceStatus of all internal Contacts.
        5. Assembles the full system_instruction by combining:
               - CallFlow.system_instruction (base IVR flow definition)
               - CorporateVoiceProfile.tone_guidelines (brand voice identity)
               - Section schedule context block (availability per section —
                 ONLY for sections with an active call_flow assigned)
               - Presence context block (current availability of internal staff)
        6. Builds section_callflow_map: dict[section_pk, CallFlow] for all
           qualifying sections (active + call_flow assigned + call_flow active).
        7. Returns the 4-tuple (system_instruction, initial_greeting,
           voice_name, section_callflow_map).

    The caller is responsible for catching all exceptions and falling back
    to the hardcoded SYSTEM_INSTRUCTION_FALLBACK / INITIAL_GREETING_FALLBACK
    constants defined in vox_bridge/services.py.

    Args:
        twilio_number (str): The Twilio phone number that received the call,
                             in E.164 format (e.g. '+34951796832').
        caller_number (str): The caller's E.164 number (From field). Used to
                             verify the caller against the BlockedCaller registry.
                             Defaults to empty string, which skips the check.

    Returns:
        tuple[str, str, str, dict, CallFlow | None]: A 5-tuple of:
            - system_instruction (str): Full assembled system instruction ready
              for injection into the Gemini Live LiveConnectConfig. Includes
              the IDENTIFICADORES DE SECCIÓN block with section_pk → name
              mapping for function calling (Paso 38).
            - initial_greeting (str): Initial greeting text to be sent via
              session.send_client_content() upon session entry.
            - voice_name (str): Gemini Live voice name for this company
              (e.g. 'Aoede', 'Puck', 'Charon', etc.).
            - section_callflow_map (dict[int, CallFlow]): Maps section.pk →
              CallFlow for all qualifying sections. Used by
              VoiceOrchestrationService._reload_session_for_section() to
              dynamically reinject the correct system_instruction when the
              caller's intended section is identified.
            - general_call_flow (CallFlow | None): The general CallFlow instance
              linked to the PhoneNumber. Required by
              VoiceOrchestrationService._activate_fallback_section() to resolve
              the fallback_section FK. None if no active CallFlow is assigned.

    Raises:
        PhoneNumber.DoesNotExist: If no active PhoneNumber matches twilio_number.
        ValueError: If the matched PhoneNumber has no active CallFlow assigned.
    ---
    Construye el SYSTEM_INSTRUCTION e INITIAL_GREETING dinámicos para una
    llamada entrante.

    Dado el número Twilio en formato E.164 que recibió la llamada, esta función:
        1. Resuelve el registro PhoneNumber activo para ese número.
        2. Carga el CallFlow activo asociado.
        3. Carga el CorporateVoiceProfile de la Company (si está activo).
        4. Consulta el PresenceStatus activo de todos los Contact internos.
        5. Ensambla el system_instruction completo combinando:
               - CallFlow.system_instruction (definición base del flujo IVR)
               - CorporateVoiceProfile.tone_guidelines (identidad de voz de marca)
               - Bloque de contexto de presencia (disponibilidad actual del personal)
        6. Devuelve la tupla (system_instruction, initial_greeting).

    El llamante es responsable de capturar todas las excepciones y caer al
    fallback de las constantes hardcodeadas SYSTEM_INSTRUCTION_FALLBACK /
    INITIAL_GREETING_FALLBACK definidas en vox_bridge/services.py.

    Args:
        twilio_number (str): El número de teléfono Twilio que recibió la llamada,
                             en formato E.164 (p. ej. '+12603466780').

    Returns:
        tuple[str, str]: Una tupla de (system_instruction, initial_greeting),
                         ambas como cadenas planas listas para su inyección en
                         el LiveConnectConfig de Gemini Live.

    Raises:
        PhoneNumber.DoesNotExist: Si ningún PhoneNumber activo coincide con
                                  twilio_number.
        ValueError: Si el PhoneNumber encontrado no tiene ningún CallFlow
                    activo asignado.
    """
    # Close any stale database connection before querying.
    # Cierra cualquier conexión de base de datos obsoleta antes de consultar.
    # Long-running processes (always-on task) keep the connection open between
    # calls. MySQL closes idle connections after wait_timeout seconds, causing
    # OperationalError / InterfaceError on the next query. Calling close()
    # forces Django to open a fresh connection on the next ORM operation.
    # Los procesos de larga duración (always-on task) mantienen la conexión
    # abierta entre llamadas. MySQL cierra las conexiones inactivas tras
    # wait_timeout segundos, provocando OperationalError / InterfaceError en
    # la siguiente consulta. Llamar a close() fuerza a Django a abrir una
    # conexión fresca en la siguiente operación ORM.
    connection.close()

    logger.info(
        f"[CONFIG] Iniciando carga dinámica de configuración IVR "
        f"para el número Twilio: {twilio_number} "
        f"(llamante: '{{caller_number or 'desconocido'}}')"
    )

    # ------------------------------------------------------------------
    # STEP 0 — Verify BlockedCaller / Verificar BlockedCaller
    # ------------------------------------------------------------------
    if caller_number:
        try:
            _pn = PhoneNumber.objects.select_related('company').get(
                number=twilio_number, is_active=True
            )
            if _is_caller_blocked(_pn.company, caller_number):
                logger.warning(
                    f"[CONFIG] Llamante bloqueado: {caller_number} "
                    f"para '{_pn.company.name}'. Retornando config de rechazo."
                )
                _rej_instr = (
                    "El llamante esta en la lista de bloqueados de esta empresa. "
                    "Salúdale brevemente y comunícale que en este momento no "
                    "puedes atenderle. Despídete de forma educada y da por "
                    "finalizada la llamada sin proporcionar ninguna otra informacion."
                )
                _rej_greeting = (
                    "El llamante acaba de conectar. Dile exactamente: "
                    "'Lo sentimos, en este momento no podemos atender su llamada. "
                    "Gracias por contactarnos. Hasta luego.' y da por finalizada la sesion."
                )
                return _rej_instr, _rej_greeting, "Aoede"
        except PhoneNumber.DoesNotExist:
            pass
        except Exception as block_exc:
            logger.warning(
                f"[CONFIG] Error al verificar BlockedCaller para '{caller_number}': "
                f"{type(block_exc).__name__}: {block_exc}. "
                "Continuando sin verificacion de bloqueo."
            )

    # ------------------------------------------------------------------
    # STEP 1 — Resolve PhoneNumber / Resolver PhoneNumber
    # ------------------------------------------------------------------
    # Raises PhoneNumber.DoesNotExist if the number is not configured.
    # Lanza PhoneNumber.DoesNotExist si el número no está configurado.
    phone_number_record = PhoneNumber.objects.select_related(
        "company",
        "call_flow",
        "call_flow__company",
    ).get(number=twilio_number, is_active=True)

    company = phone_number_record.company
    logger.info(
        f"[CONFIG] PhoneNumber resuelto: {twilio_number} → "
        f"Empresa: '{company.name}' (id={company.pk})"
    )

    # ------------------------------------------------------------------
    # STEP 2 — Resolve CallFlow / Resolver CallFlow
    # ------------------------------------------------------------------
    call_flow = phone_number_record.call_flow
    if call_flow is None or not call_flow.is_active:
        raise ValueError(
            f"El número {twilio_number} de la empresa '{company.name}' "
            f"no tiene ningún CallFlow activo asignado. "
            "No es posible construir la configuración dinámica."
        )
    logger.info(
        f"[CONFIG] CallFlow resuelto: '{call_flow.name}' (id={call_flow.pk})"
    )

    # ------------------------------------------------------------------
    # STEP 3 — Load CorporateVoiceProfile / Cargar CorporateVoiceProfile
    # ------------------------------------------------------------------
    # The voice profile is optional: if the company has none or it is
    # inactive, the tone block is simply omitted from the system_instruction.
    # voice_name is always extracted — falls back to 'Aoede' if no profile.
    # El perfil de voz es opcional: si la empresa no tiene ninguno o está
    # inactivo, el bloque de tono se omite del system_instruction.
    # voice_name siempre se extrae — cae a 'Aoede' si no hay perfil.
    voice_name   = "Aoede"
    voice_profile = None
    try:
        candidate_profile = company.voice_profile
        if candidate_profile.is_active:
            voice_profile = candidate_profile
            logger.info(
                f"[CONFIG] CorporateVoiceProfile cargado para '{company.name}'."
            )
        else:
            logger.info(
                f"[CONFIG] CorporateVoiceProfile de '{company.name}' existe "
                "pero está inactivo. Se omitirá el bloque de tono."
            )
    except Exception:
        # company.voice_profile raises RelatedObjectDoesNotExist (subclass of
        # AttributeError / ObjectDoesNotExist) if no profile exists.
        # company.voice_profile lanza RelatedObjectDoesNotExist (subclase de
        # AttributeError / ObjectDoesNotExist) si no existe ningún perfil.
        logger.info(
            f"[CONFIG] La empresa '{company.name}' no tiene CorporateVoiceProfile. "
            "Se omitirá el bloque de tono."
        )

    # ------------------------------------------------------------------
    # STEP 4 — Build Section Schedule Context + section_callflow_map
    #           Construir Contexto de Horarios + section_callflow_map
    # ------------------------------------------------------------------
    # _build_section_schedule_context() now returns a 2-tuple (Estrategia B,
    # Step 37.A). The second element is the section_callflow_map dict that
    # maps each qualifying Section pk to its CallFlow instance for dynamic
    # in-session reinjection by VoiceOrchestrationService.
    # _build_section_schedule_context() devuelve ahora una tupla de 2 elementos
    # (Estrategia B, Paso 37.A). El segundo elemento es el section_callflow_map
    # que mapea el pk de cada Section cualificada a su CallFlow para la
    # reinyección dinámica en sesión por VoiceOrchestrationService.
    schedule_context, section_callflow_map = _build_section_schedule_context(company)
    if schedule_context:
        logger.info(
            f"[CONFIG] Contexto de horarios generado para '{company.name}' "
            f"({len(schedule_context.splitlines())} sección/es cualificada/s)."
        )
    else:
        logger.info(
            f"[CONFIG] Sin contexto de horarios para '{company.name}'."
        )

    # ------------------------------------------------------------------
    # STEP 4B — Build Breakdown Context / Construir Contexto de Averías
    # ------------------------------------------------------------------
    # Queries sections with ivr_breakdown_enabled=True. The resulting
    # context block is injected into the system_instruction so Gemini
    # knows when to trigger the breakdown capture flow instead of
    # attempting a transfer.
    # Consulta secciones con ivr_breakdown_enabled=True. El bloque de
    # contexto resultante se inyecta en el system_instruction para que
    # Gemini sepa cuándo activar el flujo de captura de avería en lugar
    # de intentar una transferencia.
    breakdown_context, breakdown_section_pks = _build_breakdown_context(company)
    if breakdown_context:
        logger.info(
            f"[CONFIG] Contexto de avería interna generado para '{company.name}' "
            f"({len(breakdown_section_pks)} sección/es habilitada/s)."
        )

    # ------------------------------------------------------------------
    # STEP 4C — Build Alia Mechanic Expert Context
    #           Construir Contexto de Alia Mecanica Experta
    # H17 Paso 4: If the caller is a registered Contact of the company,
    # inject Alia mechanic expert profile into the system_instruction.
    # H17 Paso 4: Si el llamante es un Contact registrado en la empresa,
    # inyectar el perfil de mecanica experta de Alia en el system_instruction.
    # ------------------------------------------------------------------
    alia_mechanic_context = ""
    if caller_number and breakdown_context:
        try:
            _is_internal_caller = Contact.objects.filter(
                company=company,
                phone_number=caller_number,
            ).exists()
            if _is_internal_caller:
                alia_mechanic_context = (
                    "PERFIL DE ALIA - TECNICA DE FLOTA:\n"
                    "Eres Alia, tecnica de flota con mas de 20 anos de "
                    "experiencia en vehiculos industriales pesados: gruas, "
                    "camiones de gran tonelaje, plataformas elevadoras y "
                    "maquinaria de obra. Dominas sistemas electricos, "
                    "electronica, hidraulica, motores diesel, transmisiones, "
                    "frenos, direccion y estructuras de elevacion.\n\n"
                    "COMO ACTUAS ANTE UN FALLO:\n"
                    "1. DIAGNOSTICAS: en cuanto el conductor describe el "
                    "fallo, lo identificas tecnicamente de inmediato. No "
                    "preguntas lo que ya sabes.\n"
                    "2. EVALUAS EL RIESGO: determines si el vehiculo puede "
                    "seguir en marcha o debe parar. Un fallo de senalizacion "
                    "(intermitentes, luces) implica que el vehiculo NO debe "
                    "circular en via publica: riesgo de accidente y sancion. "
                    "Lo dices directamente, sin preguntar si puede circular.\n"
                    "3. ORIENTAS: si el vehiculo no debe circular, preguntas "
                    "donde esta el conductor para indicarle si puede llegar a "
                    "la base mas cercana o si necesita asistencia in situ.\n"
                    "4. PREGUNTAS SOLO LO QUE FALTA: maquina, ubicacion fisica "
                    "(base o ruta). Nunca preguntas la urgencia: la calculas "
                    "tu misma segun el fallo.\n\n"
                    "SOBRE LA UBICACION EN RUTA:\n"
                    "Cuando el conductor diga que esta en ruta o fuera de una "
                    "base, NUNCA le digas que te mande la ubicacion a este "
                    "numero ni a ninguno de los numeros de voz. "
                    "Este es un canal de voz unicamente. "
                    "Lo que debes decir es exactamente esto: "
                    "'Le vamos a enviar un mensaje de WhatsApp al numero "
                    "desde el que esta llamando. Respondalo con su ubicacion "
                    "y nuestros tecnicos se pondran en contacto con usted.' "
                    "Despues confirma el resto de datos del ticket y "
                    "cierralo normalmente.\n\n"
                    "EJEMPLO CORRECTO:\n"
                    "Conductor: 'No me lucen los intermitentes del lado izquierdo.'\n"
                    "Alia: 'Fallo en el circuito de senalizacion lateral "
                    "izquierdo. El vehiculo no debe circular en via publica: "
                    "riesgo de accidente y sancion. Que maquina es y donde "
                    "se encuentra?'\n"
                    "Conductor: 'Estoy en ruta, en la autovia.'\n"
                    "Alia: 'Le vamos a enviar un mensaje de WhatsApp al "
                    "numero desde el que esta llamando. Respondalo con su "
                    "ubicacion y nuestros tecnicos se pondran en contacto "
                    "con usted. Cual es el codigo o matricula de la maquina?'\n\n"
                    "EJEMPLO INCORRECTO (nunca hagas esto):\n"
                    "'Envieme su ubicacion a este mismo numero' -- INCORRECTO: "
                    "este es un numero de voz, no de mensajeria.\n"
                    "'Puede circular con precaucion?' -- INCORRECTO: con un "
                    "fallo de senalizacion la respuesta es no, no se pregunta.\n\n"
                    "Cuando tengas maquina y ubicacion confirmadas, resume la "
                    "averia en dos frases, confirma con el conductor y cierra "
                    "el ticket."
                )
                logger.info(
                    "[CONFIG] Llamante '%s' es Contact interno - "
                    "perfil de mecanica experta activado.",
                    caller_number,
                )
        except Exception as _alia_exc:
            logger.warning(
                "[CONFIG] Error al verificar Contact interno para Alia: "
                "%s: %s. Perfil de mecanica experta omitido.",
                type(_alia_exc).__name__, _alia_exc,
            )

    # ------------------------------------------------------------------
    # STEP 5 — Build Presence Context / Construir Contexto de Presencia
    # ------------------------------------------------------------------
    presence_context = _build_presence_context(company)
    if presence_context:
        logger.info(
            f"[CONFIG] Contexto de presencia generado para '{company.name}' "
            f"({len(presence_context.splitlines())} contacto/s interno/s)."
        )
    else:
        logger.info(
            f"[CONFIG] Sin contexto de presencia para '{company.name}'."
        )

    # ------------------------------------------------------------------
    # STEP 6 — Assemble system_instruction / Ensamblar system_instruction
    # ------------------------------------------------------------------
    # The assembly order mirrors the specification in V03DOC_DYNAMIC_IVR_INJECTION.md:
    #   1. Base IVR flow (CallFlow.system_instruction) — always present.
    #   2. Corporate voice profile block — only if a voice_profile is available.
    #   3. Presence context block — only if internal contacts with active
    #      statuses exist.
    #
    # El orden de ensamblado sigue la especificación de V03DOC_DYNAMIC_IVR_INJECTION.md:
    #   1. Flujo IVR base (CallFlow.system_instruction) — siempre presente.
    #   2. Bloque de perfil de voz corporativo — solo si hay voice_profile disponible.
    #   3. Bloque de contexto de presencia — solo si existen contactos internos
    #      con estados activos.
    system_instruction_parts = [call_flow.system_instruction.strip()]

    if voice_profile and voice_profile.tone_guidelines.strip():
        system_instruction_parts.append(
            "\n\nPERFIL CORPORATIVO DE VOZ:\n"
            + voice_profile.tone_guidelines.strip()
        )
        logger.debug("[CONFIG] Bloque de perfil de voz corporativo añadido.")

    if schedule_context.strip():
        system_instruction_parts.append(
            "\n\nDISPONIBILIDAD ACTUAL DE SECCIONES:\n"
            + schedule_context.strip()
        )
        logger.debug("[CONFIG] Bloque de contexto de horarios de secciones añadido.")

    if breakdown_context.strip():
        system_instruction_parts.append(
            "\n\n" + breakdown_context.strip()
        )
        logger.debug("[CONFIG] Bloque de contexto de avería interna añadido.")

    if alia_mechanic_context.strip():
        system_instruction_parts.append(
            "\n\n" + alia_mechanic_context.strip()
        )
        logger.debug("[CONFIG] Bloque perfil mecánica experta Alia añadido.")

    if presence_context.strip():
        system_instruction_parts.append(
            "\n\nESTADO DE PRESENCIA ACTUAL DEL PERSONAL:\n"
            + presence_context.strip()
        )
        logger.debug("[CONFIG] Bloque de contexto de presencia añadido.")

    # IDENTIFICADORES DE SECCIÓN — FUNCTION CALLING (PASO 38):
    # Se inyecta una tabla pk → nombre de sección para que Gemini pueda
    # invocar route_to_section(section_id) con el ID numérico correcto.
    # Solo se añade cuando hay secciones cualificadas en el mapa.
    #
    # SECTION IDENTIFIERS — FUNCTION CALLING (STEP 38):
    # A pk → section name table is injected so Gemini can invoke
    # route_to_section(section_id) with the correct numeric ID.
    # Only added when qualifying sections exist in the map.
    if section_callflow_map:
        section_id_lines = [
            f"  {pk}: {section_callflow_map[pk].__class__.__name__}"
            for pk in section_callflow_map
        ]
        # Resolve section names from the qualifying_sections queryset.
        # We iterate the map and resolve names via the CallFlow's related
        # sections to avoid an extra DB query.
        # Resolver los nombres de sección desde el queryset de secciones
        # cualificadas. Iteramos el mapa y resolvemos los nombres desde
        # los CallFlow relacionados para evitar una query extra a BD.
        from ivr_config.models import Section as _Section
        section_name_map = {
            s.pk: s.name
            for s in _Section.objects.filter(
                pk__in=list(section_callflow_map.keys())
            ).only("pk", "name")
        }
        section_id_lines = [
            f"  ID {pk}: {section_name_map.get(pk, f'Sección {pk}')}"
            for pk in section_callflow_map
        ]
        system_instruction_parts.append(
            "\n\nIDENTIFICADORES DE SECCIÓN:\n"
            "Cuando identifiques la sección destino, invoca la función "
            "route_to_section con el section_id correspondiente según "
            "esta tabla (solo una vez por llamada):\n"
            + "\n".join(section_id_lines)
        )
        logger.debug(
            f"[CONFIG] Bloque IDENTIFICADORES DE SECCIÓN añadido "
            f"({len(section_callflow_map)} sección/es)."
        )

    system_instruction = "".join(system_instruction_parts)

    # ------------------------------------------------------------------
    # STEP 7 — Extract initial_greeting / Extraer initial_greeting
    # ------------------------------------------------------------------
    initial_greeting = call_flow.initial_greeting.strip()

    # ------------------------------------------------------------------
    # STEP 8 — Extract voice_name / Extraer voice_name
    # ------------------------------------------------------------------
    # If a voice_profile was loaded, use its configured voice_name.
    # Otherwise the default 'Aoede' set in step 3 is preserved.
    # Si se cargó un voice_profile, usar su voice_name configurado.
    # En caso contrario se preserva el 'Aoede' por defecto del paso 3.
    if voice_profile:
        voice_name = voice_profile.voice_name
        logger.debug(
            f"[CONFIG] Voz del agente: '{voice_name}' "
            f"(CorporateVoiceProfile de '{company.name}')."
        )
    else:
        logger.debug(
            "[CONFIG] Sin CorporateVoiceProfile activo — voz por defecto 'Aoede'."
        )

    logger.info(
        f"[CONFIG] Configuración dinámica ensamblada correctamente para "
        f"'{company.name}' — número {twilio_number}. "
        f"Longitud system_instruction: {len(system_instruction)} caracteres. "
        f"Voz: '{voice_name}'."
    )

    return system_instruction, initial_greeting, voice_name, section_callflow_map, call_flow
