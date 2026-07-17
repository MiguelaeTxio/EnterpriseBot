# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_management/alert_service.py
"""
Creación automática de las alertas de caducidad POR DEFECTO (Hito 26,
ampliación S024). Decisión final de Miguel Ángel, cerrando el hueco
dejado en un commit anterior de esta misma sesión: no una sola alerta,
sino TRES por documento con fecha de caducidad -- un mes, 15 días y
una semana antes de que se cumpla, para todos los documentos que
tengan fecha de caducidad, sin excepción. El envío en sí (WhatsApp,
tarea periódica) ya existía desde H26/S021 -- ver
document_management.tasks.send_document_expiry_alerts, sin tocar.
Esto solo CREA las filas DocumentAlert automáticamente al clasificar.

Domain-agnostic a propósito, mismo principio que el resto de H26 (ver
DocumentAlert, ContentType genérico): NUNCA importa MachineDocument ni
PersonalDocument -- quien llama (machine_documents.tasks/
personal_documents.tasks) ya resuelve document_label/subject_label/
expiry_date/company/default_contact antes de invocar esto.
"""
import logging

from django.contrib.contenttypes.models import ContentType

from .models import DocumentAlert

logger = logging.getLogger(__name__)

# Decisión final de Miguel Ángel (S024): tres alertas por defecto para
# todo documento con fecha de caducidad -- un mes, 15 días y una
# semana antes. Orden de más lejana a más cercana.
DEFAULT_EXPIRY_ALERT_OFFSETS_DAYS = [30, 15, 7]


def create_default_expiry_alerts(
    document,
    expiry_date,
    document_label: str,
    subject_label: str,
    company,
    default_contact=None,
    offsets_days: list[int] = DEFAULT_EXPIRY_ALERT_OFFSETS_DAYS,
) -> list:
    """
    Crea las alertas de caducidad por defecto de `document` -- una por
    cada valor de `offsets_days` (30/15/7 por defecto), si `document`
    todavía no tiene una alerta con ese mismo offset (idempotente por
    offset, no por documento: un reintento de la tarea de
    clasificación no duplica ninguna de las tres, pero tampoco impide
    crear la que faltara si dos de las tres ya existían). No hace nada
    si `expiry_date` es None.

    Args:
        document: instancia MachineDocument o PersonalDocument.
        expiry_date: fecha de caducidad efectiva ya resuelta por quien
            llama (MachineDocument.expiry_date directo;
            PersonalDocument.expiry_date o, si está vacío,
            computed_expiry_date).
        document_label: nombre legible del documento (display_name).
        subject_label: nombre legible del sujeto (código de máquina o
            nombre de trabajador; "Sin asignar" si corresponde).
        company: ivr_config.Company del documento.
        default_contact: ivr_config.CompanyUser a añadir como único
            contacto inicial de cada alerta (típicamente
            document.uploaded_by), o None.
        offsets_days: lista de días de antelación -- ver
            DEFAULT_EXPIRY_ALERT_OFFSETS_DAYS más arriba.

    Devuelve la lista de DocumentAlert creadas en esta llamada (puede
    ser más corta que `offsets_days` si alguna ya existía).

    ---

    Creates `document`'s default expiry alerts -- one per value in
    `offsets_days` (30/15/7 by default), idempotent per offset. Does
    nothing if `expiry_date` is None.
    """
    if expiry_date is None:
        return []

    content_type = ContentType.objects.get_for_model(document)
    existing_offsets = set(
        DocumentAlert.objects
        .filter(content_type=content_type, object_id=document.pk)
        .values_list("alert_offset_days", flat=True)
    )

    created = []
    for offset_days in offsets_days:
        if offset_days in existing_offsets:
            logger.info(
                "# [create_default_expiry_alerts] %s #%d ya tiene "
                "alerta a %d días -- no se duplica.",
                content_type.model, document.pk, offset_days,
            )
            continue

        alert = DocumentAlert.objects.create(
            content_type=content_type,
            object_id=document.pk,
            document_label=document_label,
            subject_label=subject_label,
            company=company,
            expiry_date=expiry_date,
            alert_offset_days=offset_days,
        )
        if default_contact is not None:
            alert.contacts.add(default_contact)
        created.append(alert)

        logger.info(
            "# [create_default_expiry_alerts] Alerta #%d creada para "
            "%s #%d (%s, vence %s, aviso %d días antes).",
            alert.pk, content_type.model, document.pk, document_label,
            expiry_date, offset_days,
        )

    return created
