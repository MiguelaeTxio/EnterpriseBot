# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/views_room.py
"""
H37 (S138). Views of the platform chat rooms, served under /sala/.

---

H37 (S138). Vistas de las salas de chat de la plataforma, bajo
/sala/. Página propia (no la del panel) porque entran también
trabajadores sin cuenta del panel, con su enlace personal; se puede
instalar como app en cualquier móvil (manifiesto y service worker con
ámbito /sala/).
"""
import json
import logging
from pathlib import Path

from django.http import (
    Http404,
    HttpResponse,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from chat import room_service
from chat.models import ChatMessage, ChatRoom, ChatRoomMember

logger = logging.getLogger(__name__)

_SW_PATH = Path(__file__).resolve().parent / "static_src" / "room_sw.js"
MAX_BODY = 2000
PAGE_SIZE = 200


def _room_or_404(request, slug):
    """
    The room of this slug that the request can see, or 404.

    ---

    La sala de este identificador. Sin empresa en la URL: una persona
    con enlace personal no tiene sesión del panel, así que la sala se
    busca por la cookie o por la sesión; si hay varias empresas con la
    misma sala, la de quien mira.
    """
    rooms = ChatRoom.objects.select_related("company").filter(slug=slug)
    for room in rooms:
        if room_service.viewer_for(request, room) is not None:
            return room
    raise Http404("Sala no encontrada.")


def _message_json(message, room):
    """
    One message as JSON for the page.

    ---

    Un mensaje en JSON para la página (la hora en hora local).
    """
    local = timezone.localtime(message.created_at)
    data = {
        "id": message.pk,
        "time": local.strftime("%H:%M"),
        "date": local.strftime("%d/%m/%Y"),
        "kind": message.kind,
        "author": message.author_name,
        "body": message.body,
    }
    if message.attachment_blob:
        data["attachment_url"] = "/sala/%s/adjunto/%d/" % (
            room.slug, message.pk,
        )
        data["attachment_name"] = message.attachment_name
    return data


@never_cache
@require_GET
def home(request):
    """
    GET /sala/: the Asistencia room (the only one for now).

    ---

    GET /sala/: la sala Asistencia (de momento la única).
    """
    return redirect("chat_room:room", slug=room_service.ASSISTANCE_SLUG)


@never_cache
@require_GET
def enter(request, token):
    """
    GET /sala/entrar/<token>/: personal link of a member.

    ---

    Enlace personal de un miembro: deja la sesión abierta en este
    dispositivo y lleva a la sala.
    """
    member = ChatRoomMember.objects.select_related("room").filter(
        link_token=token,
    ).first()
    if member is None:
        return render(request, "chat/room/no_access.html", status=404)
    response = redirect("chat_room:room", slug=member.room.slug)
    room_service.set_member_cookie(response, member)
    logger.info("# [CHAT ROOM] Entrada por enlace del miembro %s.",
                member.pk)
    return response


@never_cache
@require_GET
def room_page(request, slug):
    """
    GET /sala/<slug>/: the room page (IRC format).

    ---

    La página de la sala, con formato de sala de IRC. Los mensajes los
    pide la propia página a /mensajes/.
    """
    company_user = (
        getattr(request.user, "company_user", None)
        if request.user.is_authenticated else None
    )
    if (
        slug == room_service.ASSISTANCE_SLUG
        and company_user is not None
        and company_user.role in room_service.MANAGER_ROLES
    ):
        # The managers open the room from the panel the first time.
        # Quien gestiona la sala la abre desde el panel la primera vez.
        room_service.assistance_room(company_user.company)
    rooms = ChatRoom.objects.select_related("company").filter(slug=slug)
    room = viewer = None
    for candidate in rooms:
        viewer = room_service.viewer_for(request, candidate)
        if viewer is not None:
            room = candidate
            break
    if room is None:
        return render(request, "chat/room/no_access.html", status=403)
    room_service.mark_seen(viewer.member)
    members = ChatRoomMember.objects.filter(room=room).select_related(
        "person",
    )
    member_names = sorted(
        room_service.person_name(member.person) for member in members
    )
    return render(request, "chat/room/room.html", {
        "room": room,
        "viewer": viewer,
        "member_names": member_names,
        "can_write": bool(viewer.name),
    })


@never_cache
@require_GET
def messages_feed(request, slug):
    """
    GET /sala/<slug>/mensajes/?after=<id>: new messages (JSON).

    ---

    Mensajes nuevos de la sala desde `after` (los últimos 200 si no se
    da). Cada consulta cuenta como estar dentro de la sala.
    """
    room = _room_or_404(request, slug)
    viewer = room_service.viewer_for(request, room)
    room_service.mark_seen(viewer.member)
    try:
        after = int(request.GET.get("after", "0") or 0)
    except ValueError:
        after = 0
    messages = ChatMessage.objects.filter(room=room)
    if after:
        messages = messages.filter(pk__gt=after).order_by("pk")[:PAGE_SIZE]
    else:
        messages = reversed(list(
            messages.order_by("-pk")[:PAGE_SIZE]
        ))
    return JsonResponse({
        "messages": [_message_json(item, room) for item in messages],
    })


@never_cache
@require_POST
def send(request, slug):
    """
    POST /sala/<slug>/enviar/: write a message.

    ---

    Escribe un mensaje en la sala (JSON `{"body": ...}`).
    """
    room = _room_or_404(request, slug)
    viewer = room_service.viewer_for(request, room)
    if not viewer.name:
        return HttpResponseForbidden("Sin nombre con el que escribir.")
    try:
        body = str(json.loads(request.body or b"{}").get("body", ""))
    except (ValueError, AttributeError):
        body = ""
    body = body.strip()[:MAX_BODY]
    if not body:
        return JsonResponse({"error": "Mensaje vacío."}, status=400)
    message = room_service.post_message(
        room, body, author=viewer.person, author_name=viewer.name,
    )
    room_service.mark_seen(viewer.member)
    return JsonResponse({"message": _message_json(message, room)})


@never_cache
@require_GET
def attachment(request, slug, pk):
    """
    GET /sala/<slug>/adjunto/<pk>/: file of a message.

    ---

    El archivo de un mensaje (el documento de TIREA de un servicio),
    bajado de GCS, solo para quien puede ver la sala.
    """
    from spare_parts.gcs_service import download_bytes

    room = _room_or_404(request, slug)
    message = get_object_or_404(ChatMessage, pk=pk, room=room)
    if not message.attachment_blob:
        raise Http404("Sin adjunto.")
    data = download_bytes(
        room_service.ATTACHMENT_BUCKET, message.attachment_blob,
    )
    response = HttpResponse(
        data,
        content_type=message.attachment_type or "application/octet-stream",
    )
    response["Content-Disposition"] = 'inline; filename="%s"' % (
        message.attachment_name.replace('"', "") or "adjunto",
    )
    return response


@never_cache
@require_GET
def member_candidates(request, slug):
    """
    GET /sala/<slug>/miembros/candidatos/?q=: workers to add (JSON).

    ---

    Trabajadores en activo que se pueden añadir, para el botón
    "Añadir" (solo quien gestiona la sala).
    """
    room = _room_or_404(request, slug)
    viewer = room_service.viewer_for(request, room)
    if not viewer.can_manage:
        return HttpResponseForbidden("Sin permiso.")
    people = room_service.candidates(room, request.GET.get("q", ""))[:50]
    return JsonResponse({"people": [
        {"id": person.pk, "name": room_service.person_full_name(person)}
        for person in people
    ]})


@never_cache
@require_POST
def member_add(request, slug):
    """
    POST /sala/<slug>/miembros/anadir/: add a worker to the room.

    ---

    Añade un trabajador a la sala (JSON `{"person": <pk>}`), solo
    quien gestiona la sala.
    """
    from document_explorer.models import PersonIdentity

    room = _room_or_404(request, slug)
    viewer = room_service.viewer_for(request, room)
    if not viewer.can_manage:
        return HttpResponseForbidden("Sin permiso.")
    try:
        person_pk = int(json.loads(request.body or b"{}").get("person"))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"error": "Persona no válida."}, status=400)
    person = PersonIdentity.objects.filter(
        pk=person_pk, company=room.company, is_active_employee=True,
    ).first()
    if person is None:
        return JsonResponse({"error": "Persona no válida."}, status=400)
    room_service.add_member(room, person, added_by=viewer.company_user)
    names = sorted(
        room_service.person_name(member.person)
        for member in ChatRoomMember.objects.filter(
            room=room,
        ).select_related("person")
    )
    return JsonResponse({"members": names})


@never_cache
@require_GET
def service_worker(request):
    """
    GET /sala/sw.js: service worker with scope /sala/.

    ---

    Service worker de la sala, servido dentro de /sala/ para que su
    ámbito sea exactamente esa ruta.
    """
    response = HttpResponse(
        _SW_PATH.read_text(encoding="utf-8"),
        content_type="application/javascript; charset=utf-8",
    )
    response["Service-Worker-Allowed"] = "/sala/"
    return response


@never_cache
@require_GET
def manifest(request):
    """
    GET /sala/manifest.json: manifest to install the room as an app.

    ---

    Manifiesto para instalar la sala como app en la pantalla de inicio
    (Android o iPhone).
    """
    data = {
        "name": "Sala de Asistencia — Grupo Álvarez",
        "short_name": "Sala",
        "start_url": "/sala/%s/" % room_service.ASSISTANCE_SLUG,
        "scope": "/sala/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#0d6efd",
        "icons": [
            {"src": "/static/panel/img/albaran_icon_192.png",
             "sizes": "192x192", "type": "image/png"},
            {"src": "/static/panel/img/albaran_icon_512.png",
             "sizes": "512x512", "type": "image/png"},
        ],
    }
    return HttpResponse(
        json.dumps(data, ensure_ascii=False),
        content_type="application/manifest+json; charset=utf-8",
    )
