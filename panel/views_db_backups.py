# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_db_backups.py
"""
Administration > Database backups, for administrators only (H24, S146).

---

Administración > Copias de seguridad, solo para administradores (H24,
S146). Miguel Ángel: "una parte que solamente sea accesible para los
administradores para poder restaurar en caso de pérdida de
información." Formato único de listados (directriz 4.24): panel fijo
(buscar y filtrar: texto, Estado, En el cubo, Selección; acciones: hacer
una copia ahora, descargar y restaurar la marcada), lista con orden
múltiple, selección persistida (screen_key "db_backups"), visor
"Selección actual" y pantalla completa. Mientras una copia o una
restauración está en marcha, la lista se refresca sola cada 5 segundos.

Restaurar sustituye la base de datos de producción por la copia elegida
(antes se hace una copia del estado actual, ver
document_explorer.db_backup_service.restore_backup). Solo el rol
Administrador: el Supervisor de Administración no entra.
"""
from urllib.parse import quote

from django.http import (
    HttpResponse, HttpResponseForbidden, StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views import View

from document_explorer.models import DatabaseBackup
from ivr_config.models import CompanyUser
from panel.mixins import CompanyUserRequiredMixin
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)

SCREEN_KEY = "db_backups"
FILTER_KEYS = ("search", "status", "bucket", "sort")
RESTORE_WORD = "RESTAURAR"
_MAX_SORT_KEYS = 4

_SORT_VALUES = {
    "date": lambda b: b.started_at,
    "file": lambda b: b.file_name,
    "status": lambda b: b.get_status_display(),
    "size": lambda b: b.size_bytes or None,
    "onedrive": lambda b: b.downloaded_at,
    "bucket": lambda b: b.in_bucket,
    "restore": lambda b: b.get_restore_status_display() or None,
}
_COLUMNS = (
    ("date", "Fecha"),
    ("file", "Archivo"),
    ("status", "Estado"),
    ("size", "Tamaño"),
    ("onedrive", "En OneDrive"),
    ("bucket", "En el cubo"),
    ("restore", "Restauración"),
)


class AdminOnlyMixin(CompanyUserRequiredMixin):
    """
    Only the Administrador role (not Supervisor de Administración).
    ---
    Solo el rol Administrador; cualquier otro recibe 403.
    """

    def dispatch(self, request, *args, **kwargs):
        company_user = getattr(request.user, "company_user", None)
        if (request.user.is_authenticated and company_user is not None
                and company_user.role != CompanyUser.ROLE_ADMIN):
            return HttpResponseForbidden(
                "Acceso denegado. Las copias de seguridad son solo para "
                "administradores.")
        return super().dispatch(request, *args, **kwargs)


def _param(request, key, default=""):
    return request.GET.get(key) or request.POST.get("_f_" + key, default)


def _parse_sort(raw):
    keys, seen = [], set()
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in _SORT_VALUES and key not in seen:
            keys.append((key, token.startswith("-")))
            seen.add(key)
    return keys[:_MAX_SORT_KEYS]


def _sort_rows(rows, sort_keys):
    rows = sorted(rows, key=lambda b: b.started_at, reverse=True)
    for key, desc in reversed(sort_keys):
        getter = _SORT_VALUES[key]
        present = [b for b in rows if getter(b) is not None]
        missing = [b for b in rows if getter(b) is None]
        rows = sorted(present, key=getter, reverse=desc) + missing
    return rows


def _sort_controls(raw):
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
                (k, d) for k, d in sort_keys if k != key]
        else:
            arrow, priority = "", ""
            new_keys = [(key, False)] + sort_keys
        columns.append({
            "key": key, "label": label, "arrow": arrow,
            "priority": priority,
            "next": ",".join(("-" if d else "") + k
                             for k, d in new_keys[:_MAX_SORT_KEYS]),
        })
    return {
        "sort_columns": columns,
        "sort_active": bool(sort_keys),
        "current_sort": ",".join(("-" if d else "") + k
                                 for k, d in sort_keys),
    }


def _annotate(backup):
    backup.in_bucket = bool(
        backup.status in (DatabaseBackup.STATUS_READY,
                          DatabaseBackup.STATUS_DOWNLOADED)
        and backup.removed_from_bucket_at is None)
    backup.in_onedrive = bool(backup.downloaded_at
                              and backup.removed_from_local_at is None)
    backup.label = backup.file_name
    return backup


def _list_context(request):
    """
    Context of the table: filtered and sorted copies.
    ---
    Contexto de la tabla: copias filtradas y ordenadas. "status": ""
    = todas, "none" = ninguna, si no, las marcadas. "bucket": "", "yes"
    o "no".
    """
    only_selected = (request.GET.get("only_selected")
                     or request.POST.get("_f_only_selected")) == "1"
    qs = DatabaseBackup.objects.all()
    if only_selected:
        wanted = [int(pk) for pk in (
            request.GET.get("selected_ids")
            or request.POST.get("_f_selected_ids", "")).split(",")
            if pk.isdigit()]
        qs = qs.filter(pk__in=wanted)
    else:
        status = _param(request, "status")
        if status == "none":
            qs = qs.none()
        elif status:
            qs = qs.filter(status__in=status.split(","))
        for word in _param(request, "search").split():
            qs = qs.filter(file_name__icontains=word)
    rows = [_annotate(b) for b in qs]
    bucket = _param(request, "bucket")
    if bucket in ("yes", "no") and not only_selected:
        rows = [b for b in rows if b.in_bucket == (bucket == "yes")]
    rows = _sort_rows(rows, _parse_sort(_param(request, "sort")))
    running = DatabaseBackup.objects.filter(
        status=DatabaseBackup.STATUS_RUNNING).exists() or (
        DatabaseBackup.objects.filter(
            restore_status=DatabaseBackup.RESTORE_RUNNING).exists())
    return {
        "rows": rows,
        "is_running": running,
        "filter_search": _param(request, "search"),
        "filter_status": _param(request, "status"),
        "filter_bucket": bucket,
        **_sort_controls(_param(request, "sort")),
    }


class DbBackupListPageView(AdminOnlyMixin, View):
    """
    GET: Backups page (fixed panel, list, selection).
    ---
    GET: página Copias de seguridad.
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        saved_selection = get_saved_state_key(
            request.user.company_user, SCREEN_KEY, "selection", [])
        if not isinstance(saved_selection, list):
            saved_selection = []
        return render(request, "panel/db_backups/list.html", {
            **_list_context(request),
            "status_choices": DatabaseBackup.STATUS_CHOICES,
            "active_nav": "db_backups",
            "screen_key": SCREEN_KEY,
            "saved_selection": saved_selection,
            "restore_word": RESTORE_WORD,
        })


class DbBackupListResultsView(AdminOnlyMixin, View):
    """
    GET: table only (filters, sort, refresh while running).
    ---
    GET: solo la tabla (filtros, orden y refresco mientras trabaja).
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        return render(request, "panel/db_backups/_table.html",
                      _list_context(request))


def _table_response(request, message, error=False):
    response = HttpResponse(render_to_string(
        "panel/db_backups/_table.html", _list_context(request),
        request=request,
    ))
    response["X-Backups-Message"] = quote(message)
    if error:
        response["X-Backups-Error"] = "1"
    return response


class DbBackupActionView(AdminOnlyMixin, View):
    """
    POST: take a copy now, or restore the marked copy.
    ---
    POST: hacer una copia ahora (no necesita marcar nada) o restaurar la
    copia marcada (exactamente una, que siga en el cubo, y escribiendo
    RESTAURAR en la confirmación). Las dos van a Celery: la lista se
    refresca sola mientras trabajan.
    """

    def post(self, request):
        from document_explorer.tasks import (
            backup_database_task,
            restore_database_task,
        )

        busy = DatabaseBackup.objects.filter(
            status=DatabaseBackup.STATUS_RUNNING).exists() or (
            DatabaseBackup.objects.filter(
                restore_status=DatabaseBackup.RESTORE_RUNNING).exists())
        action = request.POST.get("action", "")
        if busy:
            return _table_response(
                request, "Ya hay una copia o una restauración en marcha.",
                error=True)
        if action == "backup_now":
            backup_database_task.delay()
            return _table_response(
                request, "Copia en marcha: aparece en la lista en unos "
                         "segundos y el agente H28 la baja a OneDrive.")
        if action != "restore":
            return _table_response(request, "Acción desconocida.",
                                   error=True)
        ids = [int(pk) for pk in request.POST.getlist("selected")
               if pk.isdigit()]
        if len(ids) != 1:
            return _table_response(
                request, "Marca una sola copia para restaurar.", error=True)
        backup = DatabaseBackup.objects.filter(pk=ids[0]).first()
        if backup is None or not _annotate(backup).in_bucket:
            return _table_response(
                request, "Esa copia ya no está en el cubo: no se puede "
                         "restaurar desde aquí.", error=True)
        if request.POST.get("confirm_word", "").strip() != RESTORE_WORD:
            return _table_response(
                request, "Para restaurar hay que escribir %s." %
                RESTORE_WORD, error=True)
        restore_database_task.delay(backup.pk, request.user.username)
        return _table_response(
            request, "Restauración de %s en marcha. Primero se hace una "
                     "copia del estado actual." % backup.file_name)


class DbBackupDownloadView(AdminOnlyMixin, View):
    """
    GET: download one copy that is still in the bucket.
    ---
    GET: descarga una copia que siga en el cubo, leída por trozos.
    """

    def get(self, request, pk):
        from document_explorer.db_backup_service import (
            CHUNK_BYTES,
            open_blob,
        )

        backup = _annotate(get_object_or_404(DatabaseBackup, pk=pk))
        if not backup.in_bucket:
            return HttpResponse(
                "Esa copia ya no está en el cubo; está en OneDrive: %s"
                % (backup.local_path or "—"), status=404,
                content_type="text/plain; charset=utf-8")
        handle = open_blob(backup)

        def _chunks():
            try:
                while True:
                    chunk = handle.read(CHUNK_BYTES)
                    if not chunk:
                        break
                    yield chunk
            finally:
                handle.close()

        response = StreamingHttpResponse(
            _chunks(), content_type="application/gzip")
        response["Content-Length"] = str(backup.size_bytes)
        response["Content-Disposition"] = (
            'attachment; filename="%s"' % backup.file_name)
        return response
