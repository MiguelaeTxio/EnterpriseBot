# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_inbox.py
"""
H30 (S126). "Bandeja de entrada" tab of the documentation hub.

---

H30 (S126). Pestaña "Bandeja de entrada" del hub de Documentación.
Diseño de Miguel Ángel (S126): la supervisora sube aquí, arrastrando o
con el diálogo (archivos sueltos o una carpeta entera, PDF, imágenes o
ZIP), los firmados que descarga de Docuten o cualquier otro documento
de un trabajador; el servidor los clasifica y los archiva en la ficha
(`document_explorer.inbox_service`). Formato de la directriz 4.24:
panel fijo (zona de subida, filtros y acción sobre la selección) y
lista con scroll propio, orden múltiple, casillas y navegación
persistida por usuario (4.15). Solo supervisores de documentación y
administradores (`DocsUploadAccessMixin`).
"""
import json

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from document_explorer.inbox_service import (
    InboxUploadError, register_upload, requeue_items,
)
from document_explorer.models import InboxItem
from panel.mixins import DocsUploadAccessMixin
from panel.navigation_persistence import (
    apply_list_navigation, get_saved_state_key,
)

SCREEN_KEY = "inbox"
FILTER_KEYS = ("search", "status", "sort")
MAX_ROWS = 500

_SORT_VALUES = {
    "created": lambda i: i.created_at,
    "name": lambda i: i.original_name.upper(),
    "status": lambda i: i.get_status_display(),
    "person": lambda i: i.person_label.upper() or None,
    "type": lambda i: i.document_type.label if i.document_type else None,
    "uploaded_by": lambda i: i.uploaded_by_label.upper() or None,
}
_MAX_SORT_KEYS = 4
_COLUMNS = (
    ("created", "Subido"),
    ("name", "Archivo"),
    ("status", "Estado"),
    ("person", "Trabajador"),
    ("type", "Tipo"),
    ("uploaded_by", "Subido por"),
)
_STATUS_BADGES = {
    InboxItem.STATUS_PENDING: "text-bg-secondary",
    InboxItem.STATUS_PROCESSING: "text-bg-info",
    InboxItem.STATUS_ARCHIVED: "text-bg-success",
    InboxItem.STATUS_DUPLICATE: "text-bg-light border",
    InboxItem.STATUS_REJECTED: "text-bg-warning",
    InboxItem.STATUS_ERROR: "text-bg-danger",
}


def _person_label(person):
    """
    "SURNAMES, Name" of a worker, or "".

    ---

    "APELLIDOS, Nombre" del trabajador, o "".
    """
    if person is None:
        return ""
    surnames = " ".join(
        part for part in (person.first_surname, person.second_surname)
        if part
    )
    return "%s, %s" % (surnames, person.given_name)


def _user_label(company_user):
    """
    Display name of a panel user, or "".

    ---

    Nombre visible de un usuario del panel, o "".
    """
    if company_user is None:
        return ""
    return (
        company_user.user.get_full_name() or company_user.user.username
    )


def _parse_sort(raw):
    """
    "key,-key,..." -> [(key, descending)], valid unique keys only.

    ---

    "clave,-clave,..." -> [(clave, descendente)], solo claves válidas y
    sin repetir, como máximo _MAX_SORT_KEYS (formato S116/S117).
    """
    keys, seen = [], set()
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in _SORT_VALUES and key not in seen:
            keys.append((key, token.startswith("-")))
            seen.add(key)
    return keys[:_MAX_SORT_KEYS]


def _sort_controls(raw):
    """
    Next "sort" value, arrow and priority of every column header.

    ---

    Valor de "sort" que envía cada cabecera, su flecha y su prioridad
    (reglas de 4.24: clic promueve a principal, clic en la principal
    invierte). Resuelto aquí, nunca en la plantilla.
    """
    sort_keys = _parse_sort(raw)
    active = [key for key, _desc in sort_keys]
    columns = []
    for key, label in _COLUMNS:
        if key in active:
            idx = active.index(key)
            desc = sort_keys[idx][1]
            arrow = "down" if desc else "up"
            priority = idx + 1 if len(sort_keys) > 1 else ""
            new_desc = (not desc) if idx == 0 else desc
            new_keys = [(key, new_desc)] + [
                (k, d) for k, d in sort_keys if k != key
            ]
        else:
            arrow, priority = "", ""
            new_keys = [(key, False)] + sort_keys
        columns.append({
            "key": key, "label": label, "arrow": arrow,
            "priority": priority,
            "next": ",".join(
                ("-" if d else "") + k for k, d in new_keys[:_MAX_SORT_KEYS]
            ),
        })
    return {
        "sort_columns": columns,
        "sort_active": bool(sort_keys),
        "current_sort": ",".join(
            ("-" if d else "") + k for k, d in sort_keys
        ),
    }


def _sort_rows(rows, sort_keys):
    """
    Stable multi-key sort (newest first by default); empties last.

    ---

    Orden estable por varias claves (por defecto, lo más reciente
    arriba); los vacíos siempre al final.
    """
    rows = sorted(rows, key=lambda i: (i.created_at, i.pk), reverse=True)
    for key, desc in reversed(sort_keys):
        getter = _SORT_VALUES[key]
        present = [i for i in rows if getter(i) is not None]
        missing = [i for i in rows if getter(i) is None]
        rows = sorted(present, key=getter, reverse=desc) + missing
    return rows


def _annotate(item):
    """
    Attach display data resolved in the view (dumb templates).

    ---

    Añade los datos que pinta la fila, resueltos aquí (plantillas
    tontas): etiquetas, color del estado y enlaces a la ficha y al
    documento guardado.
    """
    item.person_label = _person_label(item.person)
    item.uploaded_by_label = _user_label(item.uploaded_by)
    item.status_badge = _STATUS_BADGES.get(item.status, "text-bg-secondary")
    item.person_url = (
        reverse("panel:documentation_personal_detail", args=[item.person_id])
        if item.person_id else ""
    )
    item.document_url = (
        reverse("panel:documentation_document_view", args=[item.entry_id])
        if item.entry_id else ""
    )
    item.is_open = item.status in InboxItem.OPEN_STATUSES
    item.can_retry = item.status in InboxItem.RETRYABLE_STATUSES
    return item


def _param(request, key, default=""):
    """
    Read from GET, falling back to the _f_ copy posted by actions.

    ---

    Lee de GET y, si no está, de la copia _f_ que envían las acciones.
    """
    return request.GET.get(key) or request.POST.get("_f_" + key, default)


def _list_context(request):
    """
    Context of the table fragment: filtered, annotated, sorted rows.

    ---

    Contexto del fragmento de tabla: filas filtradas, anotadas y
    ordenadas (las últimas MAX_ROWS subidas).
    """
    search = _param(request, "search").strip()
    status = _param(request, "status")
    qs = InboxItem.objects.select_related(
        "person", "document_type", "uploaded_by__user",
    ).order_by("-created_at", "-pk")
    valid_statuses = {code for code, _label in InboxItem.STATUS_CHOICES}
    if status in valid_statuses:
        qs = qs.filter(status=status)
    elif status == "attention":
        qs = qs.filter(status__in=InboxItem.RETRYABLE_STATUSES)
    rows = [_annotate(item) for item in qs[:MAX_ROWS]]
    if search:
        needle = search.upper()
        rows = [
            i for i in rows
            if needle in " ".join((
                i.original_name, i.container_name, i.reason,
                i.person_label, i.uploaded_by_label,
                i.document_type.label if i.document_type else "",
            )).upper()
        ]
    if request.GET.get("only_selected") == "1":
        wanted = {
            pk for pk in request.GET.get("selected_ids", "").split(",")
            if pk.isdigit()
        }
        rows = [i for i in rows if str(i.pk) in wanted]
    rows = _sort_rows(rows, _parse_sort(_param(request, "sort")))
    return {
        "items": rows,
        "filter_search": search,
        "filter_status": status,
        "status_choices": InboxItem.STATUS_CHOICES,
        "is_filtered": bool(search or status),
        "has_open": any(i.is_open for i in rows),
        **_sort_controls(_param(request, "sort")),
    }


def _item_payload(item, note=""):
    """
    JSON of one item for the upload progress list.

    ---

    JSON de un archivo para la lista de progreso de la subida.
    """
    _annotate(item)
    return {
        "id": item.pk,
        "name": item.original_name,
        "container": item.container_name,
        "status": item.status,
        "status_label": item.get_status_display(),
        "status_badge": item.status_badge,
        "reason": item.reason,
        "person": item.person_label,
        "person_url": item.person_url,
        "document_url": item.document_url,
        "is_open": item.is_open,
        "note": note,
    }


class InboxTabView(DocsUploadAccessMixin, View):
    """
    GET: whole tab (fixed panel and list), loaded by htmx.

    ---

    GET: la pestaña completa (panel fijo y lista), cargada por htmx
    desde hub.html.
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        saved_selection = get_saved_state_key(
            request.user.company_user, SCREEN_KEY, "selection", [],
        )
        if not isinstance(saved_selection, list):
            saved_selection = []
        return render(request, "panel/inbox/_pane.html", {
            **_list_context(request),
            "screen_key": SCREEN_KEY,
            "saved_selection": saved_selection,
        })


class InboxResultsView(DocsUploadAccessMixin, View):
    """
    GET: only the table (search, filter, sort), stored per user.

    ---

    GET: solo la tabla (búsqueda, filtro, orden), guardada por usuario.
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        return render(
            request, "panel/inbox/_table.html", _list_context(request),
        )


class InboxUploadView(DocsUploadAccessMixin, View):
    """
    POST: one file of the drop zone (a ZIP expands into its files).

    ---

    POST: un archivo de la zona de subida (el navegador los manda de
    uno en uno para mostrar el avance). Un ZIP se abre en sus
    archivos. Responde JSON, nunca en silencio: qué ha quedado en cola,
    qué ya estaba y qué no se admite.
    """

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return JsonResponse(
                {"ok": False, "error": "No ha llegado ningún archivo."},
                status=400,
            )
        name = upload.name.replace("\\", "/").rsplit("/", 1)[-1]
        try:
            results = register_upload(
                name, upload.read(), request.user.company_user,
            )
        except InboxUploadError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        items, warnings = [], []
        for item, _created, note in results:
            if item is None:
                warnings.append(note)
            else:
                items.append(_item_payload(item, note))
        return JsonResponse({"ok": True, "items": items, "warnings": warnings})


class InboxStatusView(DocsUploadAccessMixin, View):
    """
    GET: current status of some items (polled while they are open).

    ---

    GET: estado actual de varios archivos (?ids=1,2,3), que la
    pantalla consulta mientras siguen en cola o clasificándose.
    """

    def get(self, request):
        ids = [
            int(pk) for pk in request.GET.get("ids", "").split(",")
            if pk.isdigit()
        ][:MAX_ROWS]
        items = InboxItem.objects.select_related(
            "person", "uploaded_by__user",
        ).filter(pk__in=ids)
        return JsonResponse({
            "ok": True, "items": [_item_payload(item) for item in items],
        })


class InboxRetryView(DocsUploadAccessMixin, View):
    """
    POST: classify again the selected non-conforming/failed items.

    ---

    POST: vuelve a clasificar los archivos marcados que salieron no
    conformes o con error (p. ej. tras corregir la ficha del
    trabajador). Responde JSON con el resumen.
    """

    def post(self, request):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return JsonResponse(
                {"ok": False, "error": "Petición no válida."}, status=400,
            )
        ids = [
            int(pk) for pk in payload.get("selected") or []
            if str(pk).isdigit()
        ]
        if not ids:
            return JsonResponse(
                {"ok": False, "error": "No hay nada seleccionado."},
                status=400,
            )
        items = list(InboxItem.objects.select_related("entry").filter(
            pk__in=ids,
        ))
        requeued, skipped = requeue_items(
            items, request.user.company_user,
        )
        message = "%d archivo(s) en cola para clasificar de nuevo." % (
            requeued,
        )
        if skipped:
            message += (
                " %d saltado(s): solo se reclasifican los no conformes y "
                "los que dieron error." % skipped
            )
        return JsonResponse({"ok": True, "message": message})
