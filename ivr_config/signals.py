# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/signals.py

"""
Django signals for the ivr_config application.
Defines the post_save signal handler for Section that automatically creates
or regenerates the associated CallFlow when a Section is created or modified.

On creation: a new CallFlow is generated from a template incorporating the
section name, description, fleet machinery catalogue (filtered by
fleet_families), DataCaptureSet fields and SectionContact list. The generated
CallFlow is immediately assigned to section.call_flow.

On modification: the existing CallFlow's system_instruction is backed up into
backup_system_instruction and then fully regenerated from the current section
data. The admin can restore the previous version from the panel at any time.

---

Señales Django para la aplicación ivr_config.
Define el manejador de señal post_save para Section que crea o regenera
automáticamente el CallFlow asociado cuando se crea o modifica una Section.

En creación: se genera un nuevo CallFlow desde una plantilla que incorpora el
nombre de la sección, descripción, catálogo de maquinaria de flota (filtrado
por fleet_families), campos del DataCaptureSet y lista de SectionContact. El
CallFlow generado se asigna inmediatamente a section.call_flow.

En modificación: el system_instruction del CallFlow existente se respalda en
backup_system_instruction y luego se regenera completamente con los datos
actuales de la sección. El admin puede restaurar la versión anterior desde
el panel en cualquier momento.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Template builders / Constructores de plantilla
# ---------------------------------------------------------------------------

def _build_fleet_block(section) -> str:
    """
    Queries MachineAsset records filtered by section.fleet_families and builds
    a formatted text block listing available machinery for the section context.
    Returns an empty string if fleet_families is empty or no assets are found.

    ---

    Consulta los registros MachineAsset filtrados por section.fleet_families y
    construye un bloque de texto formateado con la maquinaria disponible para
    el contexto de la sección. Devuelve cadena vacía si fleet_families está
    vacío o no se encuentran activos.
    """
    from fleet.models import MachineAsset

    families = section.fleet_families
    if not families:
        return ""

    assets = (
        MachineAsset.objects
        .filter(familia__in=families, es_activo=True)
        .order_by("family", "type_name", "code")
        .values("code", "brand_model", "type_name", "family")
    )

    if not assets:
        return ""

    # Group by type_name for readability.
    # Agrupar por type_name para legibilidad.
    from collections import defaultdict
    by_type: dict = defaultdict(list)
    for asset in assets:
        by_type[asset["type_name"]].append(
            f"{asset['codigo']} ({asset['brand_model']})"
        )

    lines = ["MAQUINARIA DISPONIBLE EN ESTA SECCIÓN:"]
    for tipo, codigos in by_type.items():
        lines.append(f"  {tipo}:")
        for cod in codigos:
            lines.append(f"    - {cod}")

    return "\n".join(lines)


def _build_contacts_block(section) -> str:
    """
    Queries SectionContact records for the section ordered by priority and
    builds a formatted text block listing responsible contacts.
    Returns a placeholder string if no contacts are assigned.

    ---

    Consulta los registros SectionContact de la sección ordenados por prioridad
    y construye un bloque de texto formateado con los contactos responsables.
    Devuelve una cadena de marcador si no hay contactos asignados.
    """
    from ivr_config.models import SectionContact

    section_contacts = (
        SectionContact.objects
        .filter(section=section)
        .select_related("contact")
        .order_by("priority")
    )

    if not section_contacts:
        return "CONTACTOS RESPONSABLES:\n  [Sin contactos asignados — configurar en el panel]"

    lines = ["CONTACTOS RESPONSABLES (por orden de prioridad de transferencia):"]
    for sc in section_contacts:
        c = sc.contact
        tratamiento = ""
        if c.gender == "M":
            tratamiento = "Sr. "
        elif c.gender == "F":
            tratamiento = "Sra. "
        lines.append(
            f"  {sc.priority}. {tratamiento}{c.name} — {c.phone_number}"
        )

    return "\n".join(lines)


def _build_capture_block(section) -> str:
    """
    Reads the DataCaptureSet fields associated with the section and builds
    a formatted text block listing the data fields to collect from the caller.
    Returns a placeholder string if no DataCaptureSet is assigned.

    ---

    Lee los campos del DataCaptureSet asociado a la sección y construye un
    bloque de texto formateado con los campos de datos a recopilar del llamante.
    Devuelve una cadena de marcador si no hay DataCaptureSet asignado.
    """
    dcs = section.data_capture_set
    if not dcs:
        return (
            "DATOS A RECOPILAR DEL LLAMANTE:\n"
            "  [Sin conjunto de captura de datos configurado]"
        )

    fields = dcs.fields or []
    if not fields:
        return (
            f"DATOS A RECOPILAR DEL LLAMANTE ({dcs.name}):\n"
            "  [Sin campos definidos en el conjunto de captura]"
        )

    lines = [f"DATOS A RECOPILAR DEL LLAMANTE ({dcs.name}):"]
    for field in fields:
        label    = field.get("label", field.get("key", "Campo"))
        required = " (obligatorio)" if field.get("required") else " (opcional)"
        lines.append(f"  - {label}{required}")

    return "\n".join(lines)


def _build_section_system_instruction(section) -> str:
    """
    Builds the complete system_instruction for a Section's CallFlow by
    assembling all available context blocks: role definition, fleet machinery,
    data capture fields, responsible contacts and behavioural rules.

    This is the canonical template for auto-generated Section CallFlows.
    The admin may edit the generated text freely — the backup mechanism
    preserves the previous version before each regeneration.

    ---

    Construye el system_instruction completo para el CallFlow de una Section
    ensamblando todos los bloques de contexto disponibles: definición de rol,
    maquinaria de flota, campos de captura de datos, contactos responsables
    y reglas de comportamiento.

    Esta es la plantilla canónica para los CallFlow de Section generados
    automáticamente. El admin puede editar el texto generado libremente —
    el mecanismo de backup preserva la versión anterior antes de cada
    regeneración.
    """
    company_name = section.company.name
    section_name = section.name
    description  = section.description or "[Sin descripción de sección]"

    fleet_block    = _build_fleet_block(section)
    contacts_block = _build_contacts_block(section)
    capture_block  = _build_capture_block(section)

    # Availability context / Contexto de disponibilidad.
    if section.is_24h:
        availability = (
            "Esta sección está disponible las 24 horas del día, "
            "los 7 días de la semana."
        )
    else:
        availability = (
            "Esta sección tiene horario de atención limitado. "
            "Si el llamante contacta fuera de horario, infórmale amablemente "
            "y ofrécete a tomar sus datos de contacto."
        )

    parts = [
        f"Eres María, la asistente virtual de {company_name}, "
        f"atendiendo la sección {section_name}.",
        "",
        f"ROL EN ESTA SECCIÓN:",
        f"{description}",
        "",
        f"DISPONIBILIDAD:",
        f"{availability}",
    ]

    if fleet_block:
        parts += ["", fleet_block]

    parts += ["", capture_block]
    parts += ["", contacts_block]

    parts += [
        "",
        "INSTRUCCIÓN DE TRANSFERENCIA — OBLIGATORIO:",
        "Cuando vayas a ejecutar una transferencia al responsable, SIEMPRE",
        "pronuncia antes: \"Un momento por favor, no se retire.\"",
        "NUNCA ejecutes la transferencia sin despedirte verbalmente del llamante.",
        "",
        "IDIOMA — OBLIGATORIO:",
        "El llamante puede llegar a esta sección desde el IVR principal en",
        "cualquier idioma. CONTINÚA la conversación en el idioma que el llamante",
        "esté usando en ese momento, sin cambiarlo ni preguntar por él.",
        "Si durante la conversación el llamante cambia de idioma, adáptate",
        "inmediatamente. Esta regla es de OBLIGADO CUMPLIMIENTO.",
        "",
        "REGLAS GENERALES:",
        "- Tono profesional, cálido y conciso.",
        "- Nunca inventes información que no figure en este contexto.",
        "- Nunca menciones que eres una inteligencia artificial salvo pregunta directa.",
        "- Sé concisa: no des explicaciones innecesarias.",
        "- Siempre trata al llamante de usted.",
    ]

    return "\n".join(parts)


def _build_section_initial_greeting(section) -> str:
    """
    Builds the initial_greeting for a Section's CallFlow. The greeting
    instructs the agent to acknowledge the routing and offer assistance
    in the section context without re-introducing itself from scratch,
    since the caller has already spoken with the main IVR agent.

    ---

    Construye el initial_greeting para el CallFlow de una Section. El saludo
    instruye al agente a reconocer el enrutamiento y ofrecer asistencia en el
    contexto de la sección sin volver a presentarse desde cero, ya que el
    llamante ya ha hablado con el agente IVR principal.
    """
    return (
        f"El llamante acaba de ser enrutado a la sección {section.name}. "
        f"Continúa la conversación en el idioma que el llamante esté usando. "
        f"Salúdale con el siguiente mensaje adaptado a ese idioma: "
        f"'Le paso con {section.name}. ¿En qué puedo ayudarle?'"
    )


# ---------------------------------------------------------------------------
# Signal handler / Manejador de señal
# ---------------------------------------------------------------------------

@receiver(post_save, sender="ivr_config.Section")
def auto_manage_section_call_flow(sender, instance, created, **kwargs):
    """
    Handles the post_save signal for Section.

    Skips automatically when the save was triggered by this handler itself
    — detected by checking update_fields: if the only field being saved is
    'call_flow', the signal is a self-triggered FK assignment and must not
    re-enter the handler.

    On creation (created=True):
      - Generates a new CallFlow from the canonical section template.
      - Assigns the generated CallFlow to section.call_flow via a direct
        QuerySet update (no save() call) to avoid re-triggering post_save.

    On modification (created=False, update_fields != {'call_flow'}):
      - If section has no CallFlow: generates one via QuerySet update.
      - If section has a CallFlow: backs up system_instruction and
        regenerates from current section data.

    ---

    Maneja la señal post_save para Section.

    Se omite automáticamente cuando el guardado fue disparado por este mismo
    manejador — detectado comprobando update_fields: si el único campo que
    se está guardando es 'call_flow', la señal es una asignación FK
    auto-disparada y no debe re-entrar en el manejador.

    En creación (created=True):
      - Genera un nuevo CallFlow desde la plantilla canónica de sección.
      - Asigna el CallFlow generado a section.call_flow mediante un update()
        directo del QuerySet (sin llamada a save()) para evitar re-disparar
        post_save.

    En modificación (created=False, update_fields != {'call_flow'}):
      - Si la sección no tiene CallFlow: genera uno vía update() del QuerySet.
      - Si la sección tiene CallFlow: respalda system_instruction y regenera
        con los datos actuales de la sección.
    """
    # Skip self-triggered FK assignment saves.
    # Omitir los guardados de asignación FK auto-disparados.
    update_fields = kwargs.get("update_fields")
    if update_fields is not None and set(update_fields) == {"call_flow"}:
        return

    from ivr_config.models import CallFlow, Section as SectionModel

    system_instruction = _build_section_system_instruction(instance)
    initial_greeting   = _build_section_initial_greeting(instance)

    if created:
        # ------------------------------------------------------------------
        # Creation path: generate CallFlow and assign via QuerySet update.
        # Ruta de creación: generar CallFlow y asignar vía update() del QS.
        # ------------------------------------------------------------------
        call_flow = CallFlow.objects.create(
            company            = instance.company,
            name               = f"Flujo — {instance.name}",
            system_instruction = system_instruction,
            initial_greeting   = initial_greeting,
            is_active          = True,
        )
        # Use QuerySet.update() to assign the FK without triggering post_save.
        # Usar QuerySet.update() para asignar el FK sin disparar post_save.
        SectionModel.objects.filter(pk=instance.pk).update(call_flow=call_flow)
        instance.call_flow = call_flow  # Keep in-memory instance in sync.
        logger.info(
            "# [Signal] CallFlow '%s' creado y asignado a Section '%s' (ID=%d).",
            call_flow.name,
            instance.name,
            instance.pk,
        )

    else:
        # ------------------------------------------------------------------
        # Modification path: backup + regenerate existing CallFlow.
        # Ruta de modificación: backup + regenerar CallFlow existente.
        # ------------------------------------------------------------------
        # Reload call_flow from DB to avoid stale cached FK descriptor.
        # Recargar call_flow desde BD para evitar el descriptor FK cacheado.
        instance.refresh_from_db(fields=["call_flow"])
        call_flow = instance.call_flow

        if not call_flow:
            # Section has no CallFlow yet — generate and assign now.
            # La sección aún no tiene CallFlow — generar y asignar ahora.
            call_flow = CallFlow.objects.create(
                company            = instance.company,
                name               = f"Flujo — {instance.name}",
                system_instruction = system_instruction,
                initial_greeting   = initial_greeting,
                is_active          = True,
            )
            SectionModel.objects.filter(pk=instance.pk).update(call_flow=call_flow)
            instance.call_flow = call_flow
            logger.info(
                "# [Signal] CallFlow '%s' generado para Section existente '%s' (ID=%d).",
                call_flow.name,
                instance.name,
                instance.pk,
            )
            return

        # Backup current content before overwriting.
        # Respaldar el contenido actual antes de sobreescribir.
        call_flow.backup_system_instruction = call_flow.system_instruction
        call_flow.backup_initial_greeting   = call_flow.initial_greeting
        call_flow.system_instruction        = system_instruction
        call_flow.initial_greeting          = initial_greeting
        call_flow.save(update_fields=[
            "backup_system_instruction",
            "backup_initial_greeting",
            "system_instruction",
            "initial_greeting",
        ])
        logger.info(
            "# [Signal] CallFlow '%s' regenerado para Section '%s' (ID=%d). "
            "Backup preservado.",
            call_flow.name,
            instance.name,
            instance.pk,
        )
