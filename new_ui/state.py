# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/state.py
"""
What each user leaves set in the new interface (UiState).

---

Lo que cada usuario deja puesto en la nueva interfaz (sección, filtros,
columnas, pestañas, tamaños, selección...), en su propia tabla
(UiState). Copia adaptada de panel/navigation_persistence.py y
panel/views_navigation_state.py (S163): la nueva interfaz no usa el
guardado de la antigua, para poder borrar cualquiera de las dos sin
romper la otra.
"""

import json

from django.http import HttpResponseBadRequest, JsonResponse
from django.views import View

from new_ui.mixins import SuperuserRequiredMixin
from new_ui.models import UiState

RESET_PARAM = "reset"


def saved_state(company_user, screen_key):
    """
    The saved state of one screen for one user, or None.

    ---

    El estado guardado de una pantalla para un usuario, o None.
    """
    if company_user is None or company_user.pk is None:
        return None
    return (UiState.objects
            .filter(company_user=company_user, screen_key=screen_key)
            .values_list("state", flat=True).first())


def get_key(company_user, screen_key, key, default=None):
    """
    One key of a screen's saved state.

    ---

    Una clave del estado guardado de una pantalla.
    """
    saved = saved_state(company_user, screen_key)
    if isinstance(saved, dict):
        return saved.get(key, default)
    return default


def save_keys(company_user, screen_key, values):
    """
    Merge top-level keys into a screen's saved state.

    ---

    Suma claves de primer nivel al estado guardado de una pantalla.
    """
    obj, _created = UiState.objects.get_or_create(
        company_user=company_user, screen_key=screen_key,
        defaults={"state": {}},
    )
    state = obj.state if isinstance(obj.state, dict) else {}
    state.update(values)
    obj.state = state
    obj.save(update_fields=["state", "updated_at"])


def apply_list_navigation(request, screen_key, keys):
    """
    Save the list keys of a request, or restore the saved ones.

    ---

    Si la petición trae alguna clave del listado, la guarda; si no,
    recupera las últimas guardadas ("?reset=1" guarda un estado vacío).
    Debe ejecutarse antes de que la vista lea request.GET.
    """
    company_user = getattr(request.user, "company_user", None)
    if company_user is None:
        return
    if RESET_PARAM in request.GET:
        save_keys(company_user, screen_key, {"filters": {}})
        return
    if any(key in request.GET for key in keys):
        save_keys(company_user, screen_key, {
            "filters": {key: request.GET.get(key, "") for key in keys}})
        return
    filters = get_key(company_user, screen_key, "filters")
    if not isinstance(filters, dict):
        return
    mutable = request.GET.copy()
    for key in keys:
        value = filters.get(key)
        if isinstance(value, str) and value:
            mutable[key] = value
    request.GET = mutable


class StateSaveView(SuperuserRequiredMixin, View):
    """
    POST JSON: merge it into the user's state of one screen.

    ---

    POST con un JSON: lo suma (primer nivel) al estado guardado de esa
    pantalla para el usuario (new_ui_state.js).
    """

    def post(self, request, screen_key):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return HttpResponseBadRequest("JSON inválido.")
        if not isinstance(payload, dict) or len(screen_key) > 80:
            return HttpResponseBadRequest("Se esperaba un objeto JSON.")
        save_keys(request.user.company_user, screen_key, payload)
        return JsonResponse({"ok": True})
