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
import os
from datetime import date

from django.contrib.contenttypes.models import ContentType
from django.utils.timezone import now

from .models import DocumentAlert

logger = logging.getLogger(__name__)

# Decisión final de Miguel Ángel (S024): tres alertas por defecto para
# todo documento con fecha de caducidad -- un mes, 15 días y una
# semana antes. Orden de más lejana a más cercana.
DEFAULT_EXPIRY_ALERT_OFFSETS_DAYS = [30, 15, 7]

# Nombre de la plantilla WhatsApp usada tanto por la tarea periódica
# (document_management.tasks.send_document_expiry_alerts) como por el
# envío manual (send_alert_now(), S025) -- mismo Content SID en los
# dos sitios, un único punto de verdad.
TEMPLATE_NAME = "document_expiry_alert"


def _build_twilio_client():
    """
    Mismo patrón que whatsapp.tasks._build_twilio_client() -- import
    perezoso de twilio.rest.Client aquí dentro (no a nivel de módulo)
    para que este archivo siga siendo importable sin credenciales de
    Twilio configuradas en entornos donde no hagan falta (tests,
    shell, etc.).
    """
    from twilio.rest import Client as TwilioClient
    return TwilioClient(
        username=os.environ["TWILIO_API_KEY_SID"],
        password=os.environ["TWILIO_API_KEY_SECRET"],
        account_sid=os.environ["TWILIO_ACCOUNT_SID"],
    )


def _get_whatsapp_sender() -> str:
    """
    Devuelve el número sender de WhatsApp principal del entorno.
    Lee TWILIO_WHATSAPP_SENDER -- el número E.164 registrado como
    sender de WhatsApp en el Console de Twilio para Grupo Álvarez,
    con TWILIO_PHONE_NUMBER como fallback por compatibilidad. Mismo
    patrón EXACTO que whatsapp.tasks._get_whatsapp_sender() (S025,
    corregido tras un error real: la primera versión de esta función
    usaba el nombre inventado WHATSAPP_SENDER_NUMBER, que nunca
    existió en el entorno -- provocaba un 500 real en producción,
    confirmado por Miguel Ángel: "otras plantillas se están enviando
    desde ese sender y no está dando ningún tipo de error", señal de
    que el nombre real era otro).
    """
    return os.environ.get(
        "TWILIO_WHATSAPP_SENDER",
        os.environ.get("TWILIO_PHONE_NUMBER", ""),
    )


def send_alert_now(alert: DocumentAlert) -> tuple[bool, str]:
    """
    Envía INMEDIATAMENTE el WhatsApp de vencimiento de `alert` a todos
    sus contactos con teléfono válido -- sin esperar a la tarea
    periódica (S025, petición explícita de Miguel Ángel: "tenemos que
    tener la disponibilidad de lanzar el aviso, la notificación por
    WhatsApp, de forma manual"). Misma plantilla y mismas variables de
    contenido que la tarea periódica
    (document_management.tasks.send_document_expiry_alerts), que a su
    vez reutiliza esta misma función para no duplicar la lógica de
    envío en dos sitios.

    Marca `alert` como SENT si al menos un contacto recibió el
    mensaje. Devuelve (éxito, mensaje legible) para mostrar feedback
    directo al usuario en el panel -- a diferencia de la tarea
    periódica, que solo registra en logs (nadie está mirando en ese
    momento).
    """
    from ivr_config.models import Contact
    from whatsapp.models import WhatsAppTemplate

    try:
        template = WhatsAppTemplate.objects.get(
            company=alert.company, name=TEMPLATE_NAME, is_active=True,
        )
    except WhatsAppTemplate.DoesNotExist:
        return False, "La plantilla de WhatsApp no está activa/aprobada todavía."

    contacts = list(alert.contacts.all())
    if not contacts:
        return False, "Esta alerta no tiene ningún contacto asignado."

    try:
        twilio_client = _build_twilio_client()
        sender_number = _get_whatsapp_sender()
    except KeyError as exc:
        # S025, hallazgo real: una variable de entorno de Twilio
        # ausente (TWILIO_API_KEY_SID/TWILIO_API_KEY_SECRET/
        # TWILIO_ACCOUNT_SID) reventaba con un 500 sin capturar --
        # HTMX no sustituye nada en pantalla ante una respuesta 500,
        # así que el botón "no hacía nada" en apariencia mientras el
        # error real vivía solo en el log web. Nunca debe romper la
        # petición -- se convierte en el mismo tipo de fallo
        # controlado que "sin contactos" o "plantilla no aprobada".
        logger.error(
            "# [send_alert_now] Variable de entorno de Twilio ausente "
            "en el proceso web: %s.", exc,
        )
        return False, (
            f"Falta configurar la variable de entorno {exc} en el "
            "servidor -- contacta con el administrador."
        )

    if not sender_number:
        logger.error(
            "# [send_alert_now] Ni TWILIO_WHATSAPP_SENDER ni "
            "TWILIO_PHONE_NUMBER están configurados en el proceso web.",
        )
        return False, (
            "No hay ningún número remitente de WhatsApp configurado "
            "en el servidor -- contacta con el administrador."
        )

    notified = []
    skipped = []
    for company_user in contacts:
        try:
            contact = Contact.objects.get(
                company_user=company_user, is_internal=True,
            )
        except Contact.DoesNotExist:
            skipped.append(f"{company_user} (sin ficha de contacto)")
            continue
        if not contact.phone_number:
            skipped.append(f"{company_user} (sin teléfono)")
            continue
        try:
            twilio_client.messages.create(
                from_=f"whatsapp:{sender_number}",
                to=f"whatsapp:{contact.phone_number}",
                content_sid=template.content_sid,
                content_variables={
                    "1": company_user.user.get_full_name() or company_user.user.username,
                    "2": alert.document_label,
                    "3": alert.subject_label,
                    "4": alert.expiry_date.strftime("%d/%m/%Y"),
                },
            )
            notified.append(company_user)
        except Exception as exc:
            logger.error(
                "# [send_alert_now] Error enviando alerta #%d a %s: %s",
                alert.pk, contact.phone_number, exc,
            )
            skipped.append(f"{company_user} (error de envío)")

    if notified:
        alert.status = DocumentAlert.Status.SENT
        alert.sent_at = now()
        alert.save(update_fields=["status", "sent_at"])
        message = f"Enviada a {len(notified)} contacto(s)."
        if skipped:
            message += f" Omitido(s): {', '.join(skipped)}."
        logger.info(
            "# [send_alert_now] Alerta #%d enviada manualmente -- %s",
            alert.pk, message,
        )
        return True, message

    message = (
        "No se pudo enviar a ningún contacto -- " + "; ".join(skipped)
        if skipped else
        "No se pudo enviar a ningún contacto."
    )
    return False, message


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

    QUEDA TERMINANTEMENTE PROHIBIDO crear ninguna alerta si
    `expiry_date` ya pasó (S025, decisión explícita de Miguel Ángel:
    "cuando un documento ya está archivado... no tiene sentido crear
    ningún tipo de alerta"). Un documento con fecha de caducidad
    anterior a hoy está archivado por definición
    (vigencia_service.is_current -- expiry_date >= hoy), así que
    avisar de una caducidad que ya pasó no tiene sentido de negocio --
    origen real: documentación histórica subida hoy pero con fechas de
    hace meses/años generaba alertas "vencidas sin enviar" desde el
    primer instante.

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
    ser más corta que `offsets_days` si alguna ya existía, o vacía si
    `expiry_date` es None o ya pasó).

    ---

    Creates `document`'s default expiry alerts -- one per value in
    `offsets_days` (30/15/7 by default), idempotent per offset. Does
    nothing if `expiry_date` is None or already in the past.
    """
    if expiry_date is None:
        return []

    if expiry_date < date.today():
        logger.info(
            "# [create_default_expiry_alerts] #%d (%s): expiry_date "
            "%s ya pasó -- documento archivado por definición, no se "
            "crea ninguna alerta.",
            document.pk, document_label, expiry_date,
        )
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
