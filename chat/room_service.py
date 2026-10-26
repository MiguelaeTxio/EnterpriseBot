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
import re
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
# Inside the room = polled less than this ago (the page polls every 4 s
# while it is on screen and says when it leaves it). S138: was 60 s; a
# message sent in that minute after closing the app got no notice.
# Dentro de la sala = consultó hace menos que esto (la página consulta
# cada 4 s mientras está a la vista y avisa al dejar de estarlo). S138:
# eran 60 s; un mensaje en ese minuto tras cerrar la app se quedaba sin
# aviso.
PRESENCE_WINDOW = timedelta(seconds=15)
NOTICE_TEMPLATE_NAME = "chat_room_notice"
NOTICE_BUTTON_ID = "ver_mensajes_sala"
ATTACHMENT_BUCKET = "cgs_grupo_alvarez"
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
    return ChatRoomMember.objects.select_related(
        "person__company_user__user",
    ).filter(pk=member_pk, link_token=token, room=room).first()


def viewer_for(request, room):
    """
    The Viewer of the request in this room, or None if he cannot enter.

    ---

    Quién mira la sala, o None si no puede entrar. Entra un miembro
    (por su enlace personal o por su sesión del panel) y quien gestiona
    la sala (administradores y supervisores de asistencia), aunque aún
    no se haya añadido. Con el enlace personal, la cuenta del panel de
    la persona cuenta igual que una sesión abierta (S138).
    """
    company_user = _panel_user(request, room)
    member = _cookie_member(request, room)
    person = member.person if member is not None else None
    if company_user is None and person is not None:
        # S138: the personal link counts as the person's panel account
        # (giving services, managing the room) when he has one, even
        # without a panel session on that device.
        # El enlace personal cuenta como la cuenta del panel de la
        # persona (dar servicios, gestionar la sala) si la tiene, aunque
        # no haya sesión del panel en ese dispositivo.
        linked = person.company_user
        if (
            linked is not None
            and linked.is_active
            and linked.user.is_active
            and linked.company_id == room.company_id
        ):
            company_user = linked
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


def mark_away(member):
    """
    Note that the member has just left the room (app closed or hidden).

    ---

    Anota que el miembro acaba de dejar la sala (app cerrada o en
    segundo plano): desde ya le llegan los avisos.
    """
    if member is None:
        return
    away = timezone.now() - PRESENCE_WINDOW - timedelta(seconds=1)
    ChatRoomMember.objects.filter(
        pk=member.pk, last_seen_at__gt=away,
    ).update(last_seen_at=away)


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
    Workers who can give services and are not in the room yet.

    ---

    Trabajadores que pueden dar servicios y aún no están en la sala
    (Miguel Ángel, S138: la sala es solo de quien da servicios): ficha
    en activo enlazada a una cuenta del panel activa de administrador o
    supervisor de asistencia. Filtrados por nombre si se escribe algo.
    """
    from django.db.models import Q

    from budgets.service_intake import SERVICE_GIVER_ROLES
    from document_explorer.models import PersonIdentity

    people = PersonIdentity.objects.filter(
        company=room.company, is_active_employee=True,
        company_user__is_active=True,
        company_user__user__is_active=True,
        company_user__role__in=SERVICE_GIVER_ROLES,
    ).exclude(chat_memberships__room=room).select_related("company_user")
    for word in (query or "").split():
        people = people.filter(
            Q(given_name__icontains=word)
            | Q(first_surname__icontains=word)
            | Q(second_surname__icontains=word)
        )
    return people.order_by("first_surname", "second_surname", "given_name")


def can_join(person):
    """
    Whether a worker can be added to the room (gives services).

    ---

    Si un trabajador se puede añadir a la sala: su cuenta enlazada da
    servicios.
    """
    from budgets.service_intake import service_giver

    return bool(
        person.is_active_employee
        and service_giver(person.company_user)
        and person.company_user.user.is_active
    )


def missing_data(person):
    """
    What a room member lacks to use every path (for the Añadir list).

    ---

    Lo que le falta a un miembro para usar todos los caminos: móvil en
    la ficha (sala por WhatsApp, aviso de respaldo) y contacto de
    WhatsApp enlazado a su cuenta (dar servicios a Alia por WhatsApp).
    """
    from document_explorer.person_phone_service import mobile_of
    from ivr_config.models import Contact

    missing = []
    if not mobile_of(person):
        missing.append("sin móvil en su ficha")
    if not Contact.objects.filter(
        company_user=person.company_user,
    ).exclude(phone_number="").exists():
        missing.append("sin contacto de WhatsApp en su cuenta")
    return missing


# ---------------------------------------------------------------------------
# Messages and notices.
# Mensajes y avisos.
# ---------------------------------------------------------------------------

def post_message(room, body, author=None, author_name="", kind=None,
                 attachment=None, work_order=None, transcript="", tone=""):
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
        transcript=transcript or "",
        tone=tone or "",
    )
    message_pk = message.pk
    transaction.on_commit(lambda: schedule_delivery(message_pk))
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


def schedule_delivery(message_pk):
    """
    Deliver a new message to the other members.

    ---

    Reparte un mensaje nuevo a los demás miembros (todos menos el
    autor), con el pipeline híbrido de Miguel Ángel (S138):

    1. Dentro de la sala por WhatsApp (#asistencia): el mensaje por
       WhatsApp.
    2. Con la sala abierta ahora mismo: nada.
    3. Con avisos push activados en algún dispositivo: push, uno por
       mensaje.
    4. El resto (quien no quiere push): el aviso por WhatsApp de la
       tanda, salvo que ya tenga uno sin abrir.
    """
    from chat.push_service import enabled as push_enabled
    from chat.tasks import (
        relay_room_message,
        send_room_notice,
        send_room_push,
    )

    message = ChatMessage.objects.filter(pk=message_pk).first()
    if message is None:
        return
    now = timezone.now()
    members = ChatRoomMember.objects.filter(room_id=message.room_id)
    if message.author_id is not None:
        members = members.exclude(person_id=message.author_id)
    with_push = set()
    if push_enabled():
        with_push = set(members.filter(
            push_subscriptions__isnull=False,
        ).values_list("pk", flat=True))
    inside = []
    pushed = []
    present = []
    noticed = []
    for member in members:
        if member.whatsapp_inside:
            inside.append(member.pk)
            continue
        if (
            member.last_seen_at is not None
            and now - member.last_seen_at < PRESENCE_WINDOW
        ):
            present.append(member.pk)
            continue
        if member.pk in with_push:
            pushed.append(member.pk)
            continue
        if _claim_notice(member.pk, now):
            noticed.append(member.pk)
            send_room_notice.delay(member.pk)
    logger.info(
        "# [CHAT ROOM] Mensaje %s: WhatsApp=%s push=%s en la sala=%s "
        "aviso=%s", message_pk, inside, pushed, present, noticed,
    )
    if inside:
        relay_room_message.delay(message_pk, inside)
    if pushed:
        send_room_push.delay(message_pk, pushed)


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
                tone=status_tone("", work_order),
            )
    except Exception:  # noqa: BLE001 -- el alta del servicio sigue
        logger.exception(
            "# [CHAT ROOM] No se pudo publicar el servicio %s.",
            work_order.work_order_number,
        )
        return None


SERVICE_FOLDER = "SERVICIOS_ASISTENCIA"
SERVICE_NAME = "SERVICIO"
EXTENSIONS = {
    "application/pdf": "pdf", "image/png": "png", "image/webp": "webp",
    "image/jpeg": "jpg",
}


def store_service_document(data, content_type):
    """
    Keep a service sheet in GCS; attachment dict or None.

    ---

    Guarda en GCS una hoja de servicio (foto o PDF), venga de donde
    venga (sala, WhatsApp a Alia o Servicios del panel), en la carpeta
    única `SERVICIOS_ASISTENCIA` con el nombre
    `SERVICIO_AAMMDD_HHMMSS.EXT` (hora de Madrid), como decidió Miguel
    Ángel (S138). Si en ese segundo ya hay otra, ordinal `_2`, `_3`...
    Devuelve el adjunto (`blob`, `name`, `type`), o None si no se pudo.
    """
    from spare_parts.gcs_service import get_storage_client, upload_bytes

    extension = EXTENSIONS.get(content_type, "bin")
    stamp = timezone.localtime().strftime("%y%m%d_%H%M%S")
    try:
        bucket = get_storage_client().bucket(ATTACHMENT_BUCKET)
        ordinal = 1
        while True:
            suffix = "" if ordinal == 1 else "_%d" % ordinal
            name = "%s_%s%s.%s" % (SERVICE_NAME, stamp, suffix, extension)
            blob_name = "%s/%s" % (SERVICE_FOLDER, name)
            if not bucket.blob(blob_name).exists():
                break
            ordinal += 1
        upload_bytes(
            ATTACHMENT_BUCKET, blob_name, data, content_type=content_type,
        )
    except Exception:  # noqa: BLE001 -- el servicio se da igual
        logger.exception("# [CHAT ROOM] No se pudo guardar la hoja.")
        return None
    logger.info("# [CHAT ROOM] Hoja de servicio guardada: %s", blob_name)
    return {"blob": blob_name, "name": name, "type": content_type}


TONE_GREY = "grey"
# Colour circle of each tone, for WhatsApp (no colours there).
# Círculo de color de cada tono, para WhatsApp (allí no hay colores).
TONE_EMOJI = {
    "red": "🔴", "yellow": "🟡", "green": "🟢", "grey": "⚪",
    "blue": "🔵", "orange": "🟠",
}


def status_tone(status, work_order):
    """
    Legend colour of an albarán in this status.

    ---

    Color de la leyenda del tablero de tráfico (dossier 4.4, S138) para
    un albarán en este estado: rojo creado o pendiente, amarillo
    enviado o en servicio, verde terminado y firmado (regresando), gris
    cerrado en base o anulado, azul programado, naranja incidencia
    (aviso fallido). Mismas reglas que `assistance_traffic.unit_colour`.
    """
    from budgets import assistance_traffic as traffic
    from budgets.models import WorkOrderAssistanceUnit as Unit

    if status == Unit.STATUS_NOTIFY_FAILED:
        return traffic.COLOUR_ORANGE
    if status in traffic.IN_SERVICE_STATUSES:
        return traffic.COLOUR_YELLOW
    if status in traffic.RETURNING_STATUSES:
        return traffic.COLOUR_GREEN
    if status in traffic.GONE_STATUSES:
        return TONE_GREY
    if work_order.service_date and (
        work_order.service_date > timezone.localdate()
    ):
        return traffic.COLOUR_BLUE
    return traffic.COLOUR_RED


def _driver_name(company_user):
    """
    Short name of an albarán driver.

    ---

    Nombre corto del conductor de un albarán (por su ficha si la tiene).
    """
    if company_user is None:
        return "sin conductor"
    person = getattr(company_user, "person_identity", None)
    if person is not None:
        return person_name(person)
    user = company_user.user
    return user.get_full_name().strip() or user.get_username()


def unit_event_text(event):
    """
    Room line of an albarán change, or "" if it is not posted.

    ---

    Línea de la sala de un cambio de albarán: albarán, conductor y
    máquina, y el cambio (de estado a estado, asignación o asignación
    retirada), con el detalle si lo hay. El alta del albarán no se
    publica: el servicio ya sale al darse de alta.
    """
    from budgets.models import WorkOrderAssistanceUnit as Unit
    from budgets.models import WorkOrderAssistanceUnitEvent as Event

    if event.kind == Event.KIND_CREATED:
        return ""
    unit = event.unit
    labels = dict(Unit.STATUS_CHOICES)
    machine = (
        unit.machine_asset.code if unit.machine_asset_id else unit.machine
    ) or "sin máquina"
    head = "Albarán %s · %s · %s" % (
        unit.albaran_number, _driver_name(unit.operator), machine,
    )
    if event.kind == Event.KIND_STATUS:
        change = "%s → %s" % (
            labels.get(event.from_status, event.from_status or "—"),
            labels.get(event.to_status, event.to_status),
        )
    elif event.kind == Event.KIND_ASSIGN:
        change = "asignado"
    else:
        change = "asignación retirada"
    text = "%s: *%s*" % (head, change)
    if event.detail:
        text = "%s (%s)" % (text, event.detail)
    return text


def post_unit_event(event_pk):
    """
    The bot posts an albarán change in the Asistencia room.

    ---

    El bot publica en la sala Asistencia un cambio de albarán (S138), y
    avisa como cualquier mensaje del bot. Nunca rompe el cambio de
    estado.
    """
    from budgets.models import WorkOrderAssistanceUnitEvent as Event

    event = Event.objects.select_related(
        "unit__work_order__company", "unit__operator__user",
        "unit__machine_asset",
    ).filter(pk=event_pk).first()
    if event is None:
        return None
    try:
        text = unit_event_text(event)
        if not text:
            return None
        work_order = event.unit.work_order
        status = (
            event.to_status if event.kind == Event.KIND_STATUS
            else event.unit.status
        )
        with transaction.atomic():
            return post_message(
                assistance_room(work_order.company), text, author=None,
                author_name=BOT_NAME, kind=ChatMessage.KIND_BOT,
                work_order=work_order,
                tone=status_tone(status, work_order),
            )
    except Exception:  # noqa: BLE001 -- el cambio de estado sigue
        logger.exception(
            "# [CHAT ROOM] No se pudo publicar el cambio %s.", event_pk,
        )
        return None


def store_source_document(company, data, content_type):
    """
    Keep a TIREA document in GCS and return its blob name.

    ---

    Guarda en GCS el documento de TIREA de un servicio (foto o PDF),
    como hoja de servicio (`store_service_document`), y devuelve el
    nombre del blob, o "" si no se pudo.
    """
    attachment = store_service_document(data, content_type)
    return attachment["blob"] if attachment else ""


def remember_document(intake, attachment):
    """
    Note a service sheet in its service conversation.

    ---

    Anota una hoja de servicio en su conversación de servicio, para
    enlazarla al servicio al lanzarlo o borrarla si se cancela.
    """
    from budgets.models import ServiceIntake

    data = dict(intake.data or {})
    documents = list(data.get("documents") or [])
    if attachment["blob"] not in documents:
        documents.append(attachment["blob"])
    data["documents"] = documents
    intake.data = data
    ServiceIntake.objects.filter(pk=intake.pk).update(data=data)


def discard_documents(intake):
    """
    Really delete the service sheets of a cancelled conversation.

    ---

    Borra de verdad del cubo las hojas de servicio de una conversación
    cancelada (Miguel Ángel, S138: "si el servicio es cancelado, se
    descarta el archivo [...] borrándolo realmente del bucket"). Nunca
    la que ya esté enlazada a un servicio. En la sala el mensaje queda,
    sin el archivo y con "(descartado)".
    """
    from budgets.models import WorkOrderAssistance
    from spare_parts.gcs_service import delete_file

    documents = list((intake.data or {}).get("documents") or [])
    for blob in documents:
        if not blob.startswith(SERVICE_FOLDER + "/"):
            continue
        if WorkOrderAssistance.objects.filter(
            source_document_blob=blob,
        ).exists():
            continue
        try:
            delete_file(ATTACHMENT_BUCKET, blob)
        except Exception:  # noqa: BLE001 -- se registra y se sigue
            logger.exception("# [CHAT ROOM] No se pudo borrar %s.", blob)
            continue
        for message in ChatMessage.objects.filter(attachment_blob=blob):
            message.attachment_blob = ""
            message.attachment_name = (
                "%s (descartado)" % message.attachment_name
            )[:200]
            message.save(update_fields=["attachment_blob", "attachment_name"])
        logger.info("# [CHAT ROOM] Hoja descartada y borrada: %s", blob)


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
    if not blob.startswith(SERVICE_FOLDER + "/"):
        return "", ""
    return blob, str(payload.get("t", ""))


# ---------------------------------------------------------------------------
# Inside the room through WhatsApp (S138).
# Dentro de la sala por WhatsApp (S138).
# ---------------------------------------------------------------------------

ENTER_COMMAND = "#asistencia"
LEAVE_COMMAND = "#salir"
UPLOAD_PREFIX = "asistencia/sala"
GCS_SCHEME = "gcs:"


def _twilio_send(phone, text, media_url=None):
    """
    Send a free WhatsApp message (inside the 24 h window).

    ---

    Manda un mensaje libre por WhatsApp (dentro de la ventana de 24 h)
    y devuelve su SID. Las excepciones de Twilio se propagan.
    """
    from whatsapp.tasks import _build_twilio_client, _get_whatsapp_sender
    from whatsapp.window_service import to_e164

    sender = _get_whatsapp_sender()
    if not sender.startswith("whatsapp:"):
        sender = "whatsapp:%s" % sender
    kwargs = {
        "from_": sender, "to": "whatsapp:%s" % to_e164(phone),
        "body": text,
    }
    if media_url:
        kwargs["media_url"] = [media_url]
    return _build_twilio_client().messages.create(**kwargs).sid


def _say(phone, text):
    """
    Send a short bot answer, never breaking the caller.

    ---

    Contesta algo corto del bot por WhatsApp sin romper nunca al que
    llama (webhook o tarea).
    """
    try:
        return _twilio_send(phone, text)
    except Exception:  # noqa: BLE001 -- se registra y se sigue
        logger.exception("# [CHAT ROOM] No se pudo contestar a %s.", phone)
        return ""


def member_for_phone(company, phone):
    """
    The Asistencia room member who owns this phone, or None.

    ---

    El miembro de la sala Asistencia dueño de este teléfono, o None.
    """
    from document_explorer.person_phone_service import (
        resolve_person_by_phone,
    )

    person = resolve_person_by_phone(company, phone)
    if person is None:
        return None
    return ChatRoomMember.objects.select_related("room", "person").filter(
        room__company=company, room__slug=ASSISTANCE_SLUG, person=person,
    ).first()


def wants_voice(company, phone):
    """
    Whether a WhatsApp voice note of this phone goes to transcription.

    ---

    Si una nota de voz de WhatsApp de este teléfono se transcribe
    (S138): de los miembros de la sala y de quien da servicios. El
    resto sigue como siempre.
    """
    if member_for_phone(company, phone) is not None:
        return True
    from budgets.service_intake import service_giver
    from ivr_config.models import Contact

    contact = Contact.objects.filter(
        company=company, phone_number=phone,
    ).select_related("company_user").first()
    return service_giver(getattr(contact, "company_user", None))


def member_for_company_user(company_user):
    """
    The Asistencia room member of a panel user, or None.

    ---

    El miembro de la sala Asistencia de un usuario del panel (por su
    ficha de persona), o None.
    """
    person = getattr(company_user, "person_identity", None)
    if person is None:
        return None
    return ChatRoomMember.objects.select_related("room", "person").filter(
        room__company=company_user.company, room__slug=ASSISTANCE_SLUG,
        person=person,
    ).first()


def enter_whatsapp(member, phone):
    """
    Put the member inside the room through WhatsApp.

    ---

    Mete al miembro en la sala por WhatsApp y se lo dice. Nada si ya
    estaba dentro.
    """
    if member.whatsapp_inside:
        return False
    ChatRoomMember.objects.filter(pk=member.pk).update(
        whatsapp_inside=True, whatsapp_joined_at=timezone.now(),
    )
    member.whatsapp_inside = True
    _say(phone, (
        "Estás en la sala #%s. Lo que escribas aquí va a la sala y te "
        "llegará lo que escriban los demás. Escribe %s para salir."
    ) % (member.room.slug, LEAVE_COMMAND))
    logger.info("# [CHAT ROOM] Miembro %s dentro por WhatsApp.", member.pk)
    return True


def leave_whatsapp(member):
    """
    Take the member out of the room through WhatsApp.

    ---

    Saca al miembro de la sala por WhatsApp: vuelve a recibir solo el
    aviso de mensajes nuevos.
    """
    ChatRoomMember.objects.filter(pk=member.pk).update(
        whatsapp_inside=False,
    )
    member.whatsapp_inside = False
    logger.info("# [CHAT ROOM] Miembro %s fuera por WhatsApp.", member.pk)


def handle_whatsapp_command(company, from_number, body):
    """
    #asistencia and #salir sent by WhatsApp (True if it was one).

    ---

    Órdenes de la sala por WhatsApp: `#asistencia` entra y `#salir`
    sale. Solo los miembros de la sala (Miguel Ángel, S138: un grupo
    reducido, no los chóferes). Devuelve True si era una orden.
    """
    command = (body or "").strip().lower()
    if command not in (ENTER_COMMAND, LEAVE_COMMAND):
        return False
    member = member_for_phone(company, from_number)
    if member is None:
        _say(from_number, "No estás en la sala de Asistencia.")
        return True
    if command == ENTER_COMMAND:
        if not enter_whatsapp(member, from_number):
            _say(from_number, (
                "Ya estás en la sala #%s. Escribe %s para salir."
            ) % (member.room.slug, LEAVE_COMMAND))
        return True
    if member.whatsapp_inside:
        leave_whatsapp(member)
        _say(from_number, (
            "Has salido de la sala #%s. Te avisaré cuando haya mensajes "
            "nuevos."
        ) % member.room.slug)
    else:
        _say(from_number, "No estabas dentro de la sala.")
    return True


def handle_web_command(viewer, body):
    """
    #asistencia and #salir written in the web room; notice or None.

    ---

    Las órdenes `#asistencia` y `#salir` escritas en la web de la sala
    (Miguel Ángel, S138: también desde la sala se entra y se sale de la
    sala por WhatsApp). No se publican; devuelven el aviso que ve quien
    las escribe, o None si el texto no es una orden.
    """
    from document_explorer.person_phone_service import mobile_of
    from whatsapp.window_service import window_open

    command = (body or "").strip().lower()
    if command not in (ENTER_COMMAND, LEAVE_COMMAND):
        return None
    member = viewer.member
    if member is None:
        return "No eres miembro de la sala."
    if command == LEAVE_COMMAND:
        if not member.whatsapp_inside:
            return "No estabas dentro de la sala por WhatsApp."
        leave_whatsapp(member)
        return (
            "Has salido de la sala por WhatsApp: solo te llegará el aviso "
            "de mensajes nuevos."
        )
    if member.whatsapp_inside:
        return "Ya estás dentro de la sala por WhatsApp."
    phone = mobile_of(member.person)
    if not phone:
        return "No tienes móvil en tu ficha."
    if not window_open(member.room.company, phone):
        # Free WhatsApp texts need the 24 h window open.
        # Los textos libres de WhatsApp necesitan la ventana abierta.
        return (
            "Para recibir la sala por WhatsApp, escribe %s al número de "
            "WhatsApp de la empresa." % ENTER_COMMAND
        )
    enter_whatsapp(member, phone)
    return "Estás dentro de la sala también por WhatsApp."


def store_upload(data, content_type, name=""):
    """
    Keep a file sent to the room in GCS; attachment dict or None.

    ---

    Guarda en GCS un archivo mandado a la sala (foto o PDF) y devuelve
    el adjunto (`blob`, `name`, `type`), o None si no se pudo.
    """
    import uuid

    from spare_parts.gcs_service import upload_bytes

    from chat.voice_service import AUDIO_EXTENSIONS, base_type

    content_type = base_type(content_type) or content_type
    extension = {
        "application/pdf": "pdf", "image/png": "png",
        "image/webp": "webp", "image/jpeg": "jpg",
        **AUDIO_EXTENSIONS,
    }.get(content_type, "bin")
    blob_name = "%s/%s/%s.%s" % (
        UPLOAD_PREFIX, timezone.localdate().strftime("%Y/%m"),
        uuid.uuid4().hex, extension,
    )
    try:
        upload_bytes(
            ATTACHMENT_BUCKET, blob_name, data, content_type=content_type,
        )
    except Exception:  # noqa: BLE001 -- el mensaje sale sin adjunto
        logger.exception("# [CHAT ROOM] No se pudo guardar el adjunto.")
        return None
    clean = (name or "").replace("/", "_").strip()
    if clean and "." not in clean:
        clean = "%s.%s" % (clean, extension)
    return {
        "blob": blob_name,
        "name": clean or "adjunto.%s" % extension,
        "type": content_type,
    }


def post_whatsapp_message(member_pk, body, media_url="", content_type="",
                          attachment=None, transcript=""):
    """
    Post in the room what a member sent by WhatsApp (text or file).

    ---

    Publica en la sala lo que un miembro ha mandado por WhatsApp: el
    texto y, si trae, la foto o el PDF (se baja de Twilio y se guarda
    en GCS).
    """
    member = ChatRoomMember.objects.select_related("room", "person").filter(
        pk=member_pk,
    ).first()
    if member is None:
        return None
    if attachment is None and media_url:
        from document_explorer.worker_request_service import (
            _download_media,
        )

        try:
            attachment = store_upload(
                _download_media(media_url), content_type,
            )
        except Exception:  # noqa: BLE001 -- sale el texto igual
            logger.exception("# [CHAT ROOM] Adjunto de WhatsApp perdido.")
    if not (body or attachment):
        return None
    message = post_message(
        member.room, body or "", author=member.person,
        author_name=person_name(member.person), attachment=attachment,
        transcript=transcript,
    )
    ChatRoomMember.objects.filter(pk=member.pk).update(
        last_seen_at=timezone.now(),
    )
    return message


def answers_elsewhere(company, member, phone, button_payload="",
                      has_media=False):
    """
    Whether a WhatsApp message answers another platform notice.

    ---

    Si un mensaje de WhatsApp contesta a otro aviso de la plataforma y
    no a la sala (S138, Miguel Ángel: los avisos de otras cosas van
    fuera de la sala aunque se esté dentro por WhatsApp). Entonces
    sigue su camino de siempre:

    - un botón de cualquier plantilla (repostaje, circular...);
    - una pregunta de repostaje que espera el número escrito;
    - una conversación de avería en curso;
    - una foto o PDF de un documento que se le ha pedido.
    """
    if button_payload:
        return True
    from fleet.models import RefuelQuestion
    from ivr_config.models import Contact

    if RefuelQuestion.objects.filter(
        person=member.person, status=RefuelQuestion.STATUS_AWAITING_VALUE,
    ).exists():
        return True
    contact = Contact.objects.filter(
        company=company, phone_number=phone,
    ).only("routing_state").first()
    if contact is not None and (
        contact.routing_state != Contact.ROUTING_STATE_NONE
    ):
        return True
    if has_media:
        from document_explorer.worker_request_service import open_requests

        if open_requests(member.person):
            return True
    return False


def route_whatsapp(company, from_number, body, media_url="",
                   content_type="", voice=None, button_payload=""):
    """
    A member inside the room writes by WhatsApp: to the room.

    ---

    Si quien escribe está dentro de la sala por WhatsApp (y no tiene
    una conversación de servicio abierta, que va antes por Alia), su
    mensaje va a la sala. Devuelve True si lo ha atendido. Con
    adjunto se publica en Celery (bajarlo puede tardar más de lo que
    espera Twilio).
    """
    member = member_for_phone(company, from_number)
    if member is None or not member.whatsapp_inside:
        return False
    if answers_elsewhere(
        company, member, from_number, button_payload,
        has_media=bool(media_url),
    ):
        logger.info(
            "# [CHAT ROOM] Miembro %s contesta a otro aviso: fuera de la "
            "sala.", member.pk,
        )
        return False
    if voice:
        # S138: a voice note, already transcribed (body is its text).
        # Nota de voz ya transcrita (body es su texto).
        post_whatsapp_message(
            member.pk, "", attachment=voice, transcript=body,
        )
    elif media_url:
        from chat.tasks import post_whatsapp_to_room

        post_whatsapp_to_room.delay(
            member.pk, body, media_url, content_type,
        )
    else:
        post_whatsapp_message(member.pk, body)
    if body:
        call_alia(
            getattr(member.person, "company_user", None), member.room,
            body, surface="whatsapp",
        )
    return True


def relay_line(message):
    """
    One room message as a WhatsApp line.

    ---

    Un mensaje de la sala como línea de WhatsApp: `<Nombre> texto`, o
    `-Alia- texto` para el bot, como en la sala.
    """
    if message.kind == ChatMessage.KIND_BOT:
        head = "-%s-" % message.author_name
        if message.tone in TONE_EMOJI:
            head = "%s %s" % (TONE_EMOJI[message.tone], head)
    else:
        head = "<%s>" % message.author_name
    text = message.body or ""
    if message.transcript:
        text = ("%s 🎤 %s" % (text, message.transcript)).strip()
    if message.attachment_blob and not text:
        text = message.attachment_name
    return "%s %s" % (head, text)


def deliver_relay(message_pk, member_pks):
    """
    Send a room message to the members inside by WhatsApp (Celery).

    ---

    Manda un mensaje de la sala a los miembros que están dentro por
    WhatsApp, con su archivo si lo tiene. Si a alguno se le ha cerrado
    la ventana de 24 h, sale de la sala y recibe el aviso normal
    (plantilla), como decidió Miguel Ángel (S138).
    """
    from document_explorer.person_phone_service import mobile_of
    from whatsapp.window_service import window_open

    message = ChatMessage.objects.select_related("room__company").filter(
        pk=message_pk,
    ).first()
    if message is None:
        return
    company = message.room.company
    from chat.voice_service import WHATSAPP_AUDIO, base_type, is_audio

    media_url = None
    playable = not is_audio(message.attachment_type) or (
        base_type(message.attachment_type) in WHATSAPP_AUDIO
    )
    if message.attachment_blob and playable:
        # S138: a web recording (webm) does not play in WhatsApp: only
        # its text goes.
        # Una grabación web (webm) no se reproduce en WhatsApp: va solo
        # su texto.
        from spare_parts.gcs_service import generate_signed_url

        try:
            media_url = generate_signed_url(
                ATTACHMENT_BUCKET, message.attachment_blob,
            )
        except Exception:  # noqa: BLE001 -- sale el texto y el nombre
            logger.exception("# [CHAT ROOM] Sin URL firmada del adjunto.")
    text = relay_line(message)
    members = ChatRoomMember.objects.select_related("person", "room").filter(
        pk__in=member_pks, whatsapp_inside=True,
    )
    for member in members:
        phone = mobile_of(member.person)
        if not phone:
            leave_whatsapp(member)
            continue
        if not window_open(company, phone):
            leave_whatsapp(member)
            if _claim_notice(member.pk, timezone.now()):
                deliver_notice(member.pk)
            continue
        try:
            _twilio_send(phone, text, media_url=media_url)
        except Exception:  # noqa: BLE001 -- los demás siguen
            logger.exception(
                "# [CHAT ROOM] Mensaje %s no llegó a %s.", message_pk, phone,
            )


# ---------------------------------------------------------------------------
# The service conversation with Alia happens in the room (S138).
# La conversación de servicio con Alia ocurre en la sala (S138).
# ---------------------------------------------------------------------------

def intake_member(intake):
    """
    The room member of whoever gives the service, or None.

    ---

    El miembro de la sala de quien da el servicio, o None (entonces la
    conversación sigue solo por WhatsApp, como antes).
    """
    return member_for_company_user(intake.requested_by)


def intake_inbound(intake, body, media_url, content_type, from_number,
                   voice=None):
    """
    A WhatsApp message of a service conversation: into the room.

    ---

    Un mensaje de WhatsApp de una conversación de servicio: si quien da
    el servicio es miembro de la sala, entra en ella (dar un servicio a
    Alia es entrar en la sala, Miguel Ángel, S138) y su mensaje, con el
    documento si lo trae, sale en la sala antes que la respuesta de
    Alia. El documento se guarda una sola vez, como hoja de servicio, y
    se devuelve su dirección `gcs:` para que Alia lo lea de ahí (None si
    no hay documento o no es miembro).
    """
    member = intake_member(intake)
    if member is None:
        return None
    _set_surface(intake, "whatsapp")
    enter_whatsapp(member, from_number)
    attachment = None
    if voice:
        # S138: voice note, already transcribed; not a service sheet.
        # Nota de voz ya transcrita; no es hoja de servicio.
        try:
            post_whatsapp_message(
                member.pk, "", attachment=voice, transcript=body,
            )
        except Exception:  # noqa: BLE001 -- Alia contesta igual
            logger.exception("# [CHAT ROOM] Nota de voz sin publicar.")
        return None
    if media_url:
        try:
            attachment = store_service_document(
                media_bytes(media_url), content_type,
            )
        except Exception:  # noqa: BLE001 -- sale el texto igual
            logger.exception("# [CHAT ROOM] Hoja de WhatsApp perdida.")
        if attachment is not None:
            remember_document(intake, attachment)
    try:
        post_whatsapp_message(member.pk, body, attachment=attachment)
    except Exception:  # noqa: BLE001 -- Alia lee la hoja igual
        logger.exception("# [CHAT ROOM] Mensaje de servicio sin publicar.")
    return GCS_SCHEME + attachment["blob"] if attachment else None


def _set_surface(intake, surface):
    """
    Note where the giver wrote last (whatsapp or room).

    ---

    Anota desde dónde escribió por última vez quien da el servicio
    (`whatsapp` o `room`), para saber si contestarle también fuera de
    la sala.
    """
    from budgets.models import ServiceIntake

    data = dict(intake.data or {})
    data["last_surface"] = surface
    intake.data = data
    ServiceIntake.objects.filter(pk=intake.pk).update(data=data)


def deliver_intake_text(intake, text, from_number):
    """
    Alia's answer in a service conversation; returns the WhatsApp SID.

    ---

    La respuesta de Alia en una conversación de servicio. Si quien da
    el servicio es miembro de la sala, sale en la sala (y por la sala
    le llega si está dentro por WhatsApp); si no está dentro y escribió
    por WhatsApp, también se le manda directamente. Si no es miembro,
    por WhatsApp como siempre. Devuelve el SID del WhatsApp directo, o
    "".
    """
    from budgets.models import ServiceIntake

    member = intake_member(intake)
    if member is not None:
        post_message(
            member.room, text, author=None, author_name=BOT_NAME,
            kind=ChatMessage.KIND_BOT,
        )
        fresh = ServiceIntake.objects.filter(pk=intake.pk).values_list(
            "data", flat=True,
        ).first() or {}
        member.refresh_from_db(fields=["whatsapp_inside"])
        if member.whatsapp_inside or (
            fresh.get("last_surface") == "room"
        ) or not from_number:
            return ""
    if not from_number:
        return ""
    return _twilio_send(from_number, text)


def gives_services(viewer):
    """
    Whether who looks at the room can give services.

    ---

    Si quien mira la sala da servicios (supervisor de asistencia o
    administrador): sus PDF y fotos son hojas de servicio.
    """
    from budgets.service_intake import service_giver

    return service_giver(viewer.company_user)


ALIA_MENTION = re.compile(r"(^|[^\w@])@?alia\b", re.IGNORECASE)


def mentions_alia(text):
    """
    Whether a message calls Alia by name.

    ---

    Si un mensaje nombra a Alia (`@Alia`, "Alia, ¿quién está libre?").
    """
    return bool(ALIA_MENTION.search(text or ""))


def start_room_service(viewer, room, body="", attachment=None):
    """
    Hand a room message of a service giver to Alia, if it applies.

    ---

    Pasa a Alia lo que escribe en la web de la sala quien da servicios
    (`call_alia`, superficie sala).
    """
    return call_alia(
        viewer.company_user, room, body, attachment=attachment,
        surface="room",
    )


def call_alia(company_user, room, body="", attachment=None,
              surface="room"):
    """
    Give a room message to Alia when it is for her.

    ---

    Pasa a Alia un mensaje de la sala cuando es para ella (S138, todos
    los caminos llevan a Alia):

    - De quien da servicios: un PDF o una foto abre (o sigue) la
      conversación de servicio; un texto (o la transcripción de un
      mensaje de voz) va a Alia si ya hay conversación abierta o si la
      nombra (`@Alia`).
    - De quien no da servicios y la nombra: Alia contesta en la sala
      que solo atiende a quien da servicios.

    `surface`: desde dónde escribió (`room` o `whatsapp`), para saber
    si contestarle también fuera de la sala. Devuelve True si se ha
    pasado a Alia.
    """
    from budgets.models import ServiceIntake
    from budgets.service_intake import (
        open_intake,
        service_giver,
        start_intake,
    )
    from whatsapp.tasks import _get_whatsapp_sender, service_intake_reply

    called = mentions_alia(body)
    if not service_giver(company_user):
        if called:
            post_message(
                room, "Solo atiendo peticiones de quien da servicios "
                "(supervisores de asistencia y administradores).",
                author=None, author_name=BOT_NAME,
                kind=ChatMessage.KIND_BOT,
            )
        return False
    intake = open_intake(company_user, ServiceIntake.CHANNEL_WHATSAPP)
    if intake is None and attachment is None and not called:
        return False
    if intake is None:
        from budgets.assistance_resources import operator_phone

        intake = start_intake(
            company_user, ServiceIntake.CHANNEL_WHATSAPP,
            operator_phone(company_user) or "",
        )
    _set_surface(intake, surface)
    media_url = content_type = ""
    if attachment is not None:
        remember_document(intake, attachment)
        media_url = GCS_SCHEME + attachment["blob"]
        content_type = attachment["type"]
    service_intake_reply.delay(
        intake.pk, body, media_url, content_type, _get_whatsapp_sender(),
        intake.phone_number or "", decide=False, posted=True,
    )
    return True


def post_voice(room_pk, attachment, author_person_pk=None,
               author_name="", company_user_pk=None, member_pk=None):
    """
    Transcribe a voice message recorded in the room and post it.

    ---

    Transcribe un mensaje de voz grabado en la web de la sala y lo
    publica con su texto (desde Celery). Si quien habla da servicios,
    el texto va a Alia como si lo hubiera escrito (`call_alia`).
    """
    from chat.voice_service import transcribe
    from document_explorer.models import PersonIdentity
    from ivr_config.models import CompanyUser
    from spare_parts.gcs_service import download_bytes

    room = ChatRoom.objects.filter(pk=room_pk).first()
    if room is None:
        return None
    try:
        data = download_bytes(ATTACHMENT_BUCKET, attachment["blob"])
    except Exception:  # noqa: BLE001 -- sale sin texto
        logger.exception("# [CHAT VOZ] No se pudo bajar el audio.")
        data = b""
    text = transcribe(data, attachment["type"])
    author = PersonIdentity.objects.filter(pk=author_person_pk).first()
    message = post_message(
        room, "", author=author, author_name=author_name,
        attachment=attachment, transcript=text,
    )
    if member_pk:
        ChatRoomMember.objects.filter(pk=member_pk).update(
            last_seen_at=timezone.now(),
        )
    company_user = CompanyUser.objects.filter(pk=company_user_pk).first()
    if text and company_user is not None:
        call_alia(company_user, room, text, surface="room")
    return message


def media_bytes(media_url):
    """
    Bytes of a service document: Twilio media or a room upload in GCS.

    ---

    Bytes de un documento de servicio: un adjunto de Twilio, o uno
    subido a la sala (`gcs:<blob>`).
    """
    if media_url.startswith(GCS_SCHEME):
        from spare_parts.gcs_service import download_bytes

        return download_bytes(
            ATTACHMENT_BUCKET, media_url[len(GCS_SCHEME):],
        )
    from document_explorer.worker_request_service import _download_media

    return _download_media(media_url)
