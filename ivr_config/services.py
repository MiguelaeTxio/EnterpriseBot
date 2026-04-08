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

from django.db.models import Q
from django.utils.timezone import now

from ivr_config.models import (
    Contact,
    PhoneNumber,
    PresenceStatus,
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


# ---------------------------------------------------------------------------
# PUBLIC API / API PÚBLICA
# ---------------------------------------------------------------------------

def build_live_config(twilio_number: str) -> tuple[str, str]:
    """
    Builds the dynamic SYSTEM_INSTRUCTION and INITIAL_GREETING for an inbound call.

    Given the Twilio E.164 number that received the call, this function:
        1. Resolves the active PhoneNumber record for that number.
        2. Loads the associated active CallFlow.
        3. Loads the CorporateVoiceProfile of the Company (if active).
        4. Queries the active PresenceStatus of all internal Contacts.
        5. Assembles the full system_instruction by combining:
               - CallFlow.system_instruction (base IVR flow definition)
               - CorporateVoiceProfile.tone_guidelines (brand voice identity)
               - Presence context block (current availability of internal staff)
        6. Returns the tuple (system_instruction, initial_greeting).

    The caller is responsible for catching all exceptions and falling back
    to the hardcoded SYSTEM_INSTRUCTION_FALLBACK / INITIAL_GREETING_FALLBACK
    constants defined in vox_bridge/services.py.

    Args:
        twilio_number (str): The Twilio phone number that received the call,
                             in E.164 format (e.g. '+12603466780').

    Returns:
        tuple[str, str]: A tuple of (system_instruction, initial_greeting),
                         both as plain strings ready for injection into the
                         Gemini Live LiveConnectConfig.

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
    logger.info(
        f"[CONFIG] Iniciando carga dinámica de configuración IVR "
        f"para el número Twilio: {twilio_number}"
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
    # El perfil de voz es opcional: si la empresa no tiene ninguno o está
    # inactivo, el bloque de tono se omite del system_instruction.
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
    # STEP 4 — Build Presence Context / Construir Contexto de Presencia
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
    # STEP 5 — Assemble system_instruction / Ensamblar system_instruction
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

    if presence_context.strip():
        system_instruction_parts.append(
            "\n\nESTADO DE PRESENCIA ACTUAL DEL PERSONAL:\n"
            + presence_context.strip()
        )
        logger.debug("[CONFIG] Bloque de contexto de presencia añadido.")

    system_instruction = "".join(system_instruction_parts)

    # ------------------------------------------------------------------
    # STEP 6 — Extract initial_greeting / Extraer initial_greeting
    # ------------------------------------------------------------------
    initial_greeting = call_flow.initial_greeting.strip()

    logger.info(
        f"[CONFIG] Configuración dinámica ensamblada correctamente para "
        f"'{company.name}' — número {twilio_number}. "
        f"Longitud system_instruction: {len(system_instruction)} caracteres."
    )

    return system_instruction, initial_greeting
