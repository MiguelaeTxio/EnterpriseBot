# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_management/alert_service.py
"""
Creación automática de la alerta de caducidad POR DEFECTO (Hito 26,
ampliación S024 -- Miguel Ángel: "tenemos que tener una alerta por
defecto, la fecha de caducidad de los documentos que entran... que ya
lleguen con [antelación] de antemano"). El envío en sí (WhatsApp,
tarea periódica) ya existía desde H26/S021 -- ver
document_management.tasks.send_document_expiry_alerts, sin tocar. Esto
solo CREA la fila DocumentAlert automáticamente en el momento de
clasificar, para que no dependa de que alguien la dé de alta a mano.

Domain-agnostic a propósito, mismo principio que el resto de H26 (ver
DocumentAlert, ContentType genérico): NUNCA importa MachineDocument ni
PersonalDocument -- quien llama (machine_documents.tasks/
personal_documents.tasks) ya resuelve document_label/subject_label/
expiry_date/company/default_contact antes de invocar esto.

⚠ DEFAULT_EXPIRY_ALERT_OFFSET_DAYS pendiente de confirmación final de
Miguel Ángel (S024): barajó 15 días, una semana y un mes (este último
para casos como ITV, por el tiempo de pedir cita) sin cerrar un número
único. Se usa aquí el default ya existente del propio modelo
DocumentAlert.alert_offset_days (30) como punto de partida razonable
-- UNA sola constante, cambiarla aquí basta, no hay que tocar
machine_documents.tasks ni personal_documents.tasks.
"""
import logging

from django.contrib.contenttypes.models import ContentType

from .models import DocumentAlert

logger = logging.getLogger(__name__)

# Ver aviso del docstring del módulo -- pendiente de confirmación
# final de Miguel Ángel, cambiar aquí cuando la dé.
DEFAULT_EXPIRY_ALERT_OFFSET_DAYS = 30


def create_default_expiry_alert(
    document,
    expiry_date,
    document_label: str,
    subject_label: str,
    company,
    default_contact=None,
    offset_days: int = DEFAULT_EXPIRY_ALERT_OFFSET_DAYS,
):
    """
    Crea la alerta de caducidad por defecto de `document` si todavía
    no tiene ninguna (idempotente -- un reintento de la tarea de
    clasificación no duplica alertas). No hace nada si `expiry_date`
    es None (documento sin fecha de caducidad conocida -- nada que
    alertar por defecto).

    Args:
        document: instancia MachineDocument o PersonalDocument (el
            objeto real, para resolver content_type/object_id -- este
            módulo no conoce su forma interna más allá de eso).
        expiry_date: fecha de caducidad efectiva ya resuelta por quien
            llama (MachineDocument.expiry_date directo;
            PersonalDocument.expiry_date o, si está vacío,
            computed_expiry_date -- ver PersonalDocument, S022/S024).
        document_label: nombre legible del documento (display_name).
        subject_label: nombre legible del sujeto (código de máquina o
            nombre de trabajador; "Sin asignar" si document está en
            estado UNASSIGNED -- decisión de quien llama).
        company: ivr_config.Company del documento.
        default_contact: ivr_config.CompanyUser a añadir como único
            contacto inicial de la alerta (típicamente
            document.uploaded_by), o None si no hay ninguno
            disponible -- la alerta se crea igualmente sin contactos,
            editable después desde el CRUD (previsto, todavía sin
            construir -- ver hoja de ruta).
        offset_days: días de antelación -- ver
            DEFAULT_EXPIRY_ALERT_OFFSET_DAYS más arriba.

    Devuelve la instancia DocumentAlert creada, o None si no se creó
    (expiry_date vacío, o ya existía una alerta para este documento).

    ---

    Creates `document`'s default expiry alert if it doesn't have one
    yet (idempotent). Does nothing if `expiry_date` is None.
    """
    if expiry_date is None:
        return None

    content_type = ContentType.objects.get_for_model(document)
    already_exists = DocumentAlert.objects.filter(
        content_type=content_type, object_id=document.pk,
    ).exists()
    if already_exists:
        logger.info(
            "# [create_default_expiry_alert] %s #%d ya tiene alerta -- "
            "no se duplica.",
            content_type.model, document.pk,
        )
        return None

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

    logger.info(
        "# [create_default_expiry_alert] Alerta #%d creada para %s "
        "#%d (%s, vence %s, aviso %d días antes).",
        alert.pk, content_type.model, document.pk, document_label,
        expiry_date, offset_days,
    )
    return alert
