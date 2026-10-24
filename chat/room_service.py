# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/room_service.py
"""
H37 (S138). Logic of the platform chat rooms: who is looking at a room,
posting messages, the WhatsApp notice of each batch and the services
the bot posts in the Asistencia room.

---

H37 (S138). Lógica de las salas de chat de la plataforma (decisiones
de S136, anexo H37 sección 10, y de Miguel Ángel en S138):

- La sala funciona como un canal de IRC; de momento solo hay una,
  Asistencia. Los miembros los añade a mano quien gestiona la sala
  (administradores y supervisores de asistencia) con el botón
  "Añadir".
- Quien no tiene cuenta del panel entra con su enlace personal, que
  deja la sesión abierta en ese dispositivo (cookie firmada).
- WhatsApp solo avisa: un aviso por tanda, que no se repite hasta que
  la persona entra en la sala. Dentro de la ventana de 24 h, texto
  normal; fuera, la plantilla `chat_room_notice`, con botón de
  respuesta rápida "Ver mensajes".
- Los servicios los publica el bot en la sala, en texto plano o con
  el documento de TIREA del que salieron, y avisan igual que los
  mensajes de las personas.
"""
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from chat.models import ChatMessage, ChatRoom, ChatRoomMember

logger = logging.getLogger(__name__)

ASSISTANCE_SLUG = "asistencia"
ASSISTANCE_NAME = "Asistencia"
BOT_NAME = "Alia"
COOKIE_NAME = "eb_chat_member"
COOKIE_MAX_AGE = 365 * 24 * 3600
COOKIE_SALT = "chat.room.member"
# Inside the room = polled less than this ago (the page polls every 4 s).
# Dentro de la sala = consultó hace menos que esto (la página consulta
# cada 4 s).
PRESENCE_WINDOW = timedelta(seconds=60)
NOTICE_TEMPLATE_NAME = "chat_room_notice"
NOTICE_BUTTON_ID = "ver_mensajes_sala"
ATTACHMENT_BUCKET = "cgs_grupo_alvarez"
SOURCE_PREFIX = "asistencia/tirea"
MANAGER_ROLES = ("ADMIN", "ASSIST_SUPERVISOR")


def assistance_room(company):
    """
    The Asistencia room of the company (created the first time).

    ---

    La sala Asistencia de la empresa (se crea la primera vez).
    """
    room, _created = ChatRoom.objects.get_or_create(
        company=company, slug=ASSISTANCE_SLUG,
        defaults={"name": ASSISTANCE_NAME},
    )
    return room


def person_name(person):
    """
    Short name shown in the room (given name and first surname).

    ---

    Nombre corto con el que sale en la sala (nombre y primer apellido).
    """
    parts = [person.given_name.strip().title(),
             person.first_surname.strip().title()]
    return " ".join(part for part in parts if part) or str(person.pk)


def person_full_name(person):
    """
    Full name for the member picker.

    ---

    Nombre completo, para el buscador de "Añadir".
    """
    parts = [person.given_name, person.first_surname,
             person.second_surname]
    return " ".join(
        part.strip().title() for part in parts if part and part.strip()
    )


# ---------------------------------------------------------------------------
# Access: who is looking at the room.
# Acceso: quién mira la sala.
# ---------------------------------------------------------------------------

class Viewer:
    """
    Who is looking at a room and what he can do.

    ---

    Quién mira la sala y qué puede hacer: `person` (autor de sus
    mensajes), `member` (su fila de miembro, si lo es), `can_manage`
    (botón "Añadir") y `name` (nombre con el que escribe).
    """

    def __init__(self, person=None, member=None, company_user=None):
        self.person = person
        self.member = member
        self.company_user = company_user
        self.can_manage = bool(
            company_user is not None and company_user.role in MANAGER_ROLES
        )
        if person is not None:
            self.name = person_name(person)
        elif company_user is not None:
            user = company_user.user
            self.name = (
                user.get_full_name().strip() or user.get_username()
            )
        else:
            self.name = ""


def _panel_user(request, room):
    """
    The active CompanyUser of the panel session, if of this company.

    ---

    El CompanyUser activo de la sesión del panel, si es de la empresa
    de la sala.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    company_user = getattr(user, "company_user", None)
    if (
        company_user is None
        or not company_user.is_active
        or company_user.company_id != room.company_id
    ):
        return None
    return company_user


def _cookie_member(request, room):
    """
    The member of this room in the personal-link cookie, or None.

    ---

    El miembro de esta sala guardado en la cookie del enlace personal,
    o None (sin cookie, firma mala, enlace renovado o de otra sala).
    """
    raw = request.COOKIES.get(COOKIE_NAME, "")
    if not raw:
        return None
    try:
        payload = signing.loads(
            raw, salt=COOKIE_SALT, max_age=COOKIE_MAX_AGE,
        )
        member_pk = int(payload.get("m"))
        token = str(payload.get("t"))
    except (signing.BadSignature, AttributeError, TypeError, ValueError):
        return None
    return ChatRoomMember.objects.select_related("person").filter(
        pk=member_pk, link_token=token, room=room,
    ).first()


def viewer_for(request, room):
    """
    The Viewer of the request in this room, or None if he cannot enter.

    ---

    Quién mira la sala, o None si no puede entrar. Entra un miembro
    (por su enlace personal o por su sesión del panel) y quien gestiona
    la sala (administradores y supervisores de asistencia), aunque aún
    no se haya añadido.
    """
    company_user = _panel_user(request, room)
    member = _cookie_member(request, room)
    person = member.person if member is not None else None
    if person is None and company_user is not None:
        person = getattr(company_user, "person_identity", None)
        if person is not None:
            member = ChatRoomMember.objects.filter(
                room=room, person=person,
            ).first()
    if member is None and not (
        company_user is not None and company_user.role in MANAGER_ROLES
    ):
        return None
    return Viewer(person=person, member=member, company_user=company_user)


def set_member_cookie(response, member):
    """
    Keep the session of this member open in this device.

    ---

    Deja abierta en este dispositivo la sesión de este miembro.
    """
    response.set_cookie(
        key=COOKIE_NAME,
        value=signing.dumps(
            {"m": member.pk, "t": member.link_token}, salt=COOKIE_SALT,
        ),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="Lax",
    )


def personal_link(member):
    """
    Absolute personal link of a member.

    ---

    Enlace personal del miembro, absoluto, para WhatsApp.
    """
    return settings.PLATFORM_BASE_URL + reverse(
        "chat_room:enter", args=[member.link_token],
    )


def mark_seen(member):
    """
    Note that the member is inside the room now.

    ---

    Anota que el miembro está dentro de la sala ahora. Entrar en la
    sala es lo que deja mandar el aviso de la tanda siguiente.
    """
    if member is None:
        return
    now = timezone.now()
    ChatRoomMember.objects.filter(pk=member.pk).update(last_seen_at=now)
    member.last_seen_at = now


# ---------------------------------------------------------------------------
# Members.
# Miembros.
# ---------------------------------------------------------------------------

def add_member(room, person, added_by=None):
    """
    Add a worker to the room (nothing if he already is).

    ---

    Añade un trabajador a la sala (nada si ya lo es). Devuelve
    (miembro, creado).
    """
    member = ChatRoomMember.objects.filter(room=room, person=person).first()
    if member is not None:
        return member, False
    member = ChatRoomMember.objects.create(
        room=room, person=person, added_by=added_by,
        link_token=secrets.token_urlsafe(32),
    )
    logger.info(
        "# [CHAT ROOM] %s añadido a %s por %s.",
        person.pk, room, getattr(added_by, "pk", None),
    )
    return member, True


def candidates(room, query=""):
    """
    Active workers of the company that are not in the room yet.

    ---

    Trabajadores en activo de la empresa que aún no están en la sala,
    filtrados por nombre si se escribe algo.
    """
    from django.db.models import Q

    from document_explorer.models import PersonIdentity

    people = PersonIdentity.objects.filter(
        company=room.company, is_active_employee=True,
    ).exclude(chat_memberships__room=room)
    for word in (query or "").split():
        people = people.filter(
            Q(given_name__icontains=word)
            | Q(first_surname__icontains=word)
            | Q(second_surname__icontains=word)
        )
    return people.order_by("first_surname", "second_surname", "given_name")


# ---------------------------------------------------------------------------
# Messages and notices.
# Mensajes y avisos.
# ---------------------------------------------------------------------------

def post_message(room, body, author=None, author_name="", kind=None,
                 attachment=None, work_order=None):
    """
    Save a message in the room and notify the other members.

    ---

    Guarda un mensaje en la sala y avisa por WhatsApp a los demás
    miembros (tras el commit). `attachment`: dict con `blob`, `name` y
    `type` de un archivo ya subido a GCS.
    """
    attachment = attachment or {}
    message = ChatMessage.objects.create(
        room=room,
        kind=kind or ChatMessage.KIND_USER,
        author=author,
        author_name=(author_name or BOT_NAME)[:120],
        body=body or "",
        attachment_blob=attachment.get("blob", ""),
        attachment_name=attachment.get("name", "")[:200],
        attachment_type=attachment.get("type", "")[:100],
        work_order=work_order,
    )
    author_pk = author.pk if author is not None else None
    transaction.on_commit(
        lambda: schedule_notices(room.pk, author_pk),
    )
    return message


def _claim_notice(member_pk, now):
    """
    Claim the notice of this batch for the member (True if claimed).

    ---

    Reserva el aviso de esta tanda para el miembro. Solo si no tiene
    aviso pendiente: nunca se le avisó, o entró en la sala después del
    último aviso. La actualización condicional evita dos avisos a la
    vez.
    """
    from django.db.models import F, Q

    return bool(
        ChatRoomMember.objects.filter(pk=member_pk).filter(
            Q(notice_sent_at__isnull=True)
            | Q(last_seen_at__gte=F("notice_sent_at"))
        ).update(notice_sent_at=now)
    )


def schedule_notices(room_pk, author_person_pk=None):
    """
    Send the WhatsApp notice to the members that need one.

    ---

    Manda el aviso por WhatsApp a los miembros que lo necesitan: todos
    menos el autor, quien está dentro de la sala ahora mismo y quien
    ya tiene un aviso sin abrir de esta tanda.
    """
    from chat.tasks import send_room_notice

    now = timezone.now()
    members = ChatRoomMember.objects.filter(room_id=room_pk)
    if author_person_pk is not None:
        members = members.exclude(person_id=author_person_pk)
    for member in members:
        if (
            member.last_seen_at is not None
            and now - member.last_seen_at < PRESENCE_WINDOW
        ):
            continue
        if _claim_notice(member.pk, now):
            send_room_notice.delay(member.pk)


def notice_text(member):
    """
    Plain text of the notice (inside the 24 h window).

    ---

    Texto normal del aviso, dentro de la ventana de 24 h.
    """
    return "Hay mensajes nuevos en la sala %s: %s" % (
        member.room.name, personal_link(member),
    )


def notice_variables(member):
    """
    Variables of the chat_room_notice template.

    ---

    Variables de la plantilla `chat_room_notice`: nombre, sala y
    enlace personal.
    """
    return {
        "1": member.person.given_name.strip().title() or "trabajador",
        "2": member.room.name,
        "3": personal_link(member),
    }


def deliver_notice(member_pk):
    """
    Send the notice of one member by WhatsApp (called from Celery).

    ---

    Manda el aviso de un miembro por WhatsApp (desde Celery). Si no se
    puede mandar (sin móvil, plantilla sin dar de alta, error de
    Twilio), se anota el motivo y se libera la tanda para que el
    siguiente mensaje lo vuelva a intentar.
    """
    from document_explorer.person_phone_service import mobile_of
    from whatsapp.models import WhatsAppTemplate
    from whatsapp.tasks import _build_twilio_client, _get_whatsapp_sender
    from whatsapp.window_service import send_notification, window_open

    member = ChatRoomMember.objects.select_related(
        "person", "room__company",
    ).filter(pk=member_pk).first()
    if member is None:
        return
    company = member.room.company
    phone = mobile_of(member.person)
    template = WhatsAppTemplate.objects.filter(
        company=company, name=NOTICE_TEMPLATE_NAME, is_active=True,
    ).first()
    error = ""
    if not phone:
        error = "La persona no tiene móvil en su ficha."
    elif template is None and not window_open(company, phone):
        error = (
            "Fuera de la ventana de 24 h y la plantilla %s no está dada "
            "de alta." % NOTICE_TEMPLATE_NAME
        )
    if error:
        _release_notice(member, error)
        return
    try:
        message = send_notification(
            _build_twilio_client(), _get_whatsapp_sender(), company, phone,
            template.content_sid if template is not None else "",
            variables=notice_variables(member),
            text=notice_text(member),
        )
    except Exception as exc:  # noqa: BLE001 -- se anota en el miembro
        logger.exception("# [CHAT ROOM] Aviso fallido a %s.", phone)
        _release_notice(member, "Twilio: %s" % exc)
        return
    ChatRoomMember.objects.filter(pk=member.pk).update(
        notice_message_sid=message.sid, notice_error="",
    )
    logger.info(
        "# [CHAT ROOM] Aviso de %s a %s (%s, %s).",
        member.room, phone, message.sid,
        "texto" if getattr(message, "sent_as_text", False)
        else "plantilla",
    )


def _release_notice(member, error):
    """
    Note why the notice was not sent and free the batch.

    ---

    Anota por qué no salió el aviso y libera la tanda.
    """
    logger.warning(
        "# [CHAT ROOM] Aviso no enviado al miembro %s: %s",
        member.pk, error,
    )
    ChatRoomMember.objects.filter(pk=member.pk).update(
        notice_sent_at=None, notice_error=error[:255],
    )


def handle_whatsapp_reply(company, from_number, button_payload,
                          replied_sid, whatsapp_sender):
    """
    Answer with the room link if the message answers a room notice.

    ---

    Si el mensaje contesta a un aviso de la sala (botón "Ver mensajes"
    o respuesta al propio aviso), el bot contesta con el enlace
    personal a la sala. Devuelve True si lo ha atendido. Una respuesta
    a otro mensaje nunca entra aquí, para no pisar a Alia.
    """
    from document_explorer.person_phone_service import (
        resolve_person_by_phone,
    )

    members = []
    if replied_sid:
        members = list(ChatRoomMember.objects.select_related(
            "room", "person",
        ).filter(room__company=company, notice_message_sid=replied_sid))
    if not members and button_payload == NOTICE_BUTTON_ID:
        person = resolve_person_by_phone(company, from_number)
        if person is not None:
            members = list(ChatRoomMember.objects.select_related(
                "room", "person",
            ).filter(room__company=company, person=person))
    if not members:
        return False
    from whatsapp.tasks import _build_twilio_client
    from whatsapp.window_service import to_e164

    body = "\n".join(
        "Sala %s: %s" % (member.room.name, personal_link(member))
        for member in members
    )
    sender = whatsapp_sender if whatsapp_sender.startswith(
        "whatsapp:",
    ) else "whatsapp:%s" % whatsapp_sender
    try:
        _build_twilio_client().messages.create(
            from_=sender, to="whatsapp:%s" % to_e164(from_number),
            body=body,
        )
    except Exception:  # noqa: BLE001 -- el webhook nunca se rompe
        logger.exception(
            "# [CHAT ROOM] No se pudo mandar el enlace a %s.", from_number,
        )
    return True


# ---------------------------------------------------------------------------
# Services posted by the bot.
# Servicios que publica el bot.
# ---------------------------------------------------------------------------

def service_text(work_order):
    """
    Plain text of a service, with the data it has.

    ---

    El servicio en texto plano, con los datos que tenga.
    """
    vehicle = " ".join(
        part for part in (
            work_order.vehicle_brand, work_order.vehicle_model,
            work_order.vehicle_plate,
        ) if part
    )
    insurer = work_order.insurer.name if work_order.insurer_id else ""
    lines = ["Nuevo servicio %s%s" % (
        work_order.work_order_number,
        " de %s" % insurer if insurer else "",
    )]
    rows = (
        ("Expediente", work_order.expediente),
        ("Cliente", work_order.client_name),
        ("Vehículo", vehicle),
        ("Recogida", work_order.pickup_location),
        ("Destino", work_order.destination),
        ("Avería", work_order.breakdown_description),
        ("Reparación en el sitio", "Sí" if work_order.repair_on_site
         else ""),
        ("Accidente", "Sí" if work_order.is_accident else ""),
        ("Comentarios de la aseguradora", work_order.insurer_comments),
        ("Observaciones", work_order.company_observations),
    )
    lines += ["%s: %s" % (label, value) for label, value in rows if value]
    return "\n".join(lines)


def post_service(work_order_pk):
    """
    The bot posts a new service in the Asistencia room.

    ---

    El bot publica un servicio nuevo en la sala Asistencia: con el
    documento de TIREA si salió de uno, y si no, en texto plano
    (Miguel Ángel, S138). Nunca rompe el alta del servicio.
    """
    from budgets.models import WorkOrderAssistance

    work_order = WorkOrderAssistance.objects.select_related(
        "company", "insurer",
    ).filter(pk=work_order_pk).first()
    if work_order is None:
        return None
    room = assistance_room(work_order.company)
    attachment = None
    body = service_text(work_order)
    if work_order.source_document_blob:
        name = "TIREA_%s%s" % (
            work_order.work_order_number,
            ".pdf" if work_order.source_document_type == "application/pdf"
            else "." + (
                work_order.source_document_type.split("/")[-1] or "jpg"
            ),
        )
        attachment = {
            "blob": work_order.source_document_blob,
            "name": name,
            "type": work_order.source_document_type,
        }
        body = "Nuevo servicio %s (documento de TIREA)" % (
            work_order.work_order_number,
        )
    try:
        with transaction.atomic():
            return post_message(
                room, body, author=None, author_name=BOT_NAME,
                kind=ChatMessage.KIND_BOT, attachment=attachment,
                work_order=work_order,
            )
    except Exception:  # noqa: BLE001 -- el alta del servicio sigue
        logger.exception(
            "# [CHAT ROOM] No se pudo publicar el servicio %s.",
            work_order.work_order_number,
        )
        return None


def store_source_document(company, data, content_type):
    """
    Keep a TIREA document in GCS and return its blob name.

    ---

    Guarda en GCS el documento de TIREA de un servicio (foto o PDF) y
    devuelve el nombre del blob, o "" si no se pudo.
    """
    import uuid

    from spare_parts.gcs_service import upload_bytes

    extension = {
        "application/pdf": "pdf", "image/png": "png",
        "image/webp": "webp",
    }.get(content_type, "jpg")
    blob_name = "%s/%s/%s.%s" % (
        SOURCE_PREFIX, timezone.localdate().strftime("%Y/%m"),
        uuid.uuid4().hex, extension,
    )
    try:
        upload_bytes(
            ATTACHMENT_BUCKET, blob_name, data, content_type=content_type,
        )
    except Exception:  # noqa: BLE001 -- el servicio se da igual
        logger.exception(
            "# [CHAT ROOM] No se pudo guardar el documento de TIREA de %s.",
            company,
        )
        return ""
    return blob_name


SOURCE_TOKEN_SALT = "chat.room.source"


def sign_source(blob_name, content_type):
    """
    Signed token of an uploaded TIREA document (for the order form).

    ---

    Token firmado del documento de TIREA subido, para que el formulario
    de alta lo lleve hasta el guardado sin poder cambiarlo.
    """
    if not blob_name:
        return ""
    return signing.dumps(
        {"b": blob_name, "t": content_type}, salt=SOURCE_TOKEN_SALT,
    )


def unsign_source(token):
    """
    (blob_name, content_type) of a signed token, or ("", "").

    ---

    (blob, tipo) de un token firmado, o ("", "") si no vale.
    """
    if not token:
        return "", ""
    try:
        payload = signing.loads(
            token, salt=SOURCE_TOKEN_SALT, max_age=7 * 24 * 3600,
        )
    except signing.BadSignature:
        return "", ""
    blob = str(payload.get("b", ""))
    if not blob.startswith(SOURCE_PREFIX + "/"):
        return "", ""
    return blob, str(payload.get("t", ""))
