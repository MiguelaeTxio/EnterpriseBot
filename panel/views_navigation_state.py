# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_navigation_state.py
"""
H31 (S75). Persistencia de navegación -- qué pestaña estaba activa y
qué filtros/orden tenía cada pestaña, por CompanyUser y por pantalla
(`PanelNavigationState`, ver panel/models.py). Decisión explícita de
Miguel Ángel: "el que cambie la pestaña soy yo. No me la cambia el
sistema [...] los filtros deben ser persistentes siempre" -- tabla
real en BD, no localStorage, para que sobreviva a cerrar el navegador
o cambiar de dispositivo.

Genérica por diseño (`screen_key` en la URL) para que otras pantallas
del panel puedan reutilizar el mismo mecanismo en el futuro sin una
vista nueva -- de momento solo `documentation_hub` la usa.
"""
import json

from django.http import HttpResponseBadRequest, JsonResponse
from django.views import View

from panel.mixins import CompanyUserRequiredMixin
from panel.models import PanelNavigationState


class NavigationStateSaveView(CompanyUserRequiredMixin, View):
    """
    POST: guarda (upsert) el estado de navegación de una pantalla para
    el CompanyUser autenticado. Cuerpo JSON de forma libre -- MERGE
    superficial (nivel 1) sobre el estado ya guardado, nunca
    sobrescritura completa: el frontend manda actualizaciones
    parciales (p. ej. solo `{"active_tab": "personal"}` al cambiar de
    pestaña, o solo `{"filters": {"personal": {...}}}` al buscar
    dentro de una pestaña) -- fusionar en vez de sobrescribir evita
    que guardar el filtro de una pestaña borre el `active_tab` ya
    guardado, o viceversa. El segundo nivel (`filters.<pestaña>`) SÍ
    se sobrescribe entero por pestaña -- un guardado de filtros de
    "personal" reemplaza el diccionario completo de esa pestaña, no
    lo fusiona campo a campo (evita arrastrar un `q` viejo si el
    frontend manda el conjunto completo de filtros vigente).
    """

    def post(self, request, screen_key):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return HttpResponseBadRequest("JSON inválido.")
        if not isinstance(payload, dict):
            return HttpResponseBadRequest("Se esperaba un objeto JSON.")

        company_user = request.user.company_user
        obj, _created = PanelNavigationState.objects.get_or_create(
            company_user=company_user, screen_key=screen_key,
            defaults={"state": {}},
        )
        state = obj.state if isinstance(obj.state, dict) else {}

        if "active_tab" in payload:
            state["active_tab"] = payload["active_tab"]
        if "filters" in payload and isinstance(payload["filters"], dict):
            existing_filters = state.get("filters") if isinstance(state.get("filters"), dict) else {}
            for tab_key, tab_filters in payload["filters"].items():
                existing_filters[tab_key] = tab_filters
            state["filters"] = existing_filters

        obj.state = state
        obj.save(update_fields=["state", "updated_at"])
        return JsonResponse({"ok": True})
