# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/navigation_persistence.py
"""
Per-user persistence of list filters and sorting (directive 4.15 and
4.24 of the master document), shared by every list of the panel.

It reuses the generic PanelNavigationState (never a new mechanism): a
request that carries any of the list keys (a filter form submit, a
sort click, "Quitar orden"...) stores them; a full load without any of
them restores the last ones stored by that same user. "?reset=1" (the
"clear filters" link) stores an empty state.

---

Persistencia por usuario de filtros y orden de los listados
(directrices 4.15 y 4.24 del documento maestro), compartida por todos
los listados del panel.

Reutiliza el PanelNavigationState genérico (nunca un mecanismo nuevo):
una petición que trae alguna de las claves del listado (enviar el
formulario de filtros, un clic de orden, "Quitar orden"...) las
guarda; una carga completa sin ninguna de ellas recupera las últimas
guardadas por ese mismo usuario. "?reset=1" (el enlace de "limpiar
filtros") guarda un estado vacío.
"""

import contextvars
import copy

from panel.models import PanelNavigationState

RESET_PARAM = "reset"

# S157: el estado de navegación de cada usuario se leía con una consulta
# por pantalla y clave, 6-11 veces en cada petición (filtros, selección,
# columnas, anchos, menú lateral, pestaña del hub...). Durante una
# petición (NavigationStateCacheMiddleware) se trae entero con una sola
# consulta; cualquier guardado (post_save) lo descarta y la siguiente
# lectura lo vuelve a traer.
_STATES = contextvars.ContextVar("panel_navigation_states", default=None)


def saved_state(company_user, screen_key):
    """
    The saved state of one screen for one user, or None.
    ---
    El estado guardado de una pantalla para un usuario, o None. Dentro
    de una petición, todos los del usuario con una sola consulta; se
    devuelve una copia (quien lo lea puede modificarlo sin tocar la
    caché).
    """
    cache = _STATES.get()
    if cache is None or company_user is None or company_user.pk is None:
        return (
            PanelNavigationState.objects
            .filter(company_user=company_user, screen_key=screen_key)
            .values_list("state", flat=True)
            .first()
        )
    states = cache.get(company_user.pk)
    if states is None:
        states = dict(
            PanelNavigationState.objects
            .filter(company_user_id=company_user.pk)
            .values_list("screen_key", "state")
        )
        cache[company_user.pk] = states
    return copy.deepcopy(states.get(screen_key))


def forget_saved_states(sender, instance, **kwargs):
    """
    post_save: drops the cached states of that user.
    ---
    post_save: descarta los estados en caché de ese usuario.
    """
    cache = _STATES.get()
    if cache is not None:
        cache.pop(instance.company_user_id, None)


class NavigationStateCacheMiddleware:
    """
    One cache of navigation states per request.
    ---
    Una caché de estados de navegación por petición (saved_state).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _STATES.set({})
        try:
            return self.get_response(request)
        finally:
            _STATES.reset(token)


def apply_list_navigation(request, screen_key, keys):
    """
    Saves or restores the list state for request.user.company_user.
    Must run before the view reads request.GET.
    ---
    Guarda o recupera el estado del listado para
    request.user.company_user. Debe ejecutarse antes de que la vista
    lea request.GET.
    """
    company_user = getattr(request.user, "company_user", None)
    if company_user is None:
        return

    if RESET_PARAM in request.GET:
        _store(company_user, screen_key, {})
        return

    if any(key in request.GET for key in keys):
        _store(
            company_user,
            screen_key,
            {key: request.GET.get(key, "") for key in keys},
        )
        return

    saved = saved_state(company_user, screen_key)
    filters = saved.get("filters") if isinstance(saved, dict) else None
    if not isinstance(filters, dict):
        return
    mutable = request.GET.copy()
    for key in keys:
        value = filters.get(key)
        if isinstance(value, str) and value:
            mutable[key] = value
    request.GET = mutable


def _store(company_user, screen_key, filters):
    """
    Upserts the filters of one screen for one user, keeping any other
    key already stored for that screen (e.g. the row selection, S117).
    ---
    Inserta o actualiza los filtros de una pantalla para un usuario,
    conservando cualquier otra clave ya guardada de esa pantalla (p. ej.
    la selección de filas, S117).
    """
    obj, _created = PanelNavigationState.objects.get_or_create(
        company_user=company_user,
        screen_key=screen_key,
        defaults={"state": {}},
    )
    state = obj.state if isinstance(obj.state, dict) else {}
    state["filters"] = filters
    obj.state = state
    obj.save(update_fields=["state", "updated_at"])


def get_saved_state_key(company_user, screen_key, key, default=None):
    """
    Returns one key of the saved navigation state of a screen.
    ---
    Devuelve una clave del estado de navegación guardado de una
    pantalla.
    """
    saved = saved_state(company_user, screen_key)
    if isinstance(saved, dict):
        return saved.get(key, default)
    return default
