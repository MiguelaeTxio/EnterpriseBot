# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/navigation_history.py
"""
H37 (S132). Per-user page history in the database, for "Volver".

---

H37 (S132). Historial de páginas de cada usuario en base de datos, para
que el botón "Volver" vuelva a la página desde la que se llegó. Miguel
Ángel, S132: *"si yo estoy en la habitación número 1 y voy a la
habitación central y le doy a volver, tengo que volver a la habitación
1 [...] Si estoy en la habitación 5, entro a la habitación central y
le doy a volver, debo de volver a la habitación desde la que venía"*;
y *"aquí se navega gracias a base de datos [...] si se cierra el
navegador y se vuelve a abrir, la navegación se conserva"*.

Mismo mecanismo de toda la navegación del panel (directriz 4.15):
`PanelNavigationState`, una fila por usuario con `screen_key`
`back_stack` y `state = {"stack": [url, url, ...]}`. Funciona como las
migas de pan del recorrido real del usuario:

- Cada página completa del panel que se abre (GET, no htmx, respuesta
  HTML 200) se apila. Si la página ya estaba en la pila (mismo path,
  con cualquier querystring), la pila se corta ahí: el usuario ha
  vuelto a ella, y lo que había después ya no es su camino.
- S144 (Miguel Ángel: desde Fichajes, a la ficha, al Calendario por el
  menú del botón derecho y "Volver" acababa en Vacaciones): las
  pestañas del hub de Documentación comparten dirección
  (/panel/documentacion/), así que cada pestaña cuenta como una página
  distinta (`?tab=`). La entrada del hub se guarda con la pestaña en la
  que estaba el usuario al salir (la que el hub tiene recordada), para
  que "Volver" lo deje en esa misma pestaña; y una página se reconoce
  por su path y su parámetro `tab`.
- `request.panel_back_url` es la página anterior a la actual en esa
  pila, y el procesador de contexto `back_url_context` la pone en
  todas las plantillas como `panel_back_url`. El botón "Volver" enlaza
  ahí; si no hay página anterior, no se pinta.
"""
from urllib.parse import parse_qs, urlsplit

from panel.models import PanelNavigationState

SCREEN_KEY = "back_stack"
MAX_DEPTH = 30
PANEL_PREFIX = "/panel/"
# Endpoints that are never pages of their own.
# Endpoints que nunca son páginas por sí mismos.
EXCLUDED_PREFIXES = ("/panel/navegacion/",)
# S144: el hub de Documentación, una dirección para todas sus pestañas.
HUB_PATH = "/panel/documentacion/"
HUB_SCREEN_KEY = "documentation_hub"


def _path_of(url):
    """
    Path of a stored URL, without its querystring.

    ---

    Path de una URL guardada, sin la querystring.
    """
    return url.split("?", 1)[0]


def _tab_of(url):
    values = parse_qs(urlsplit(url).query).get("tab")
    return values[0] if values else ""


def _key(url):
    """
    What identifies a page in the stack: its path and its `tab`.
    ---
    Lo que identifica una página en la pila (S144): su path y su
    parámetro `tab` (las pestañas del hub comparten path).
    """
    return _path_of(url), _tab_of(url)


def _with_hub_tab(url, tab):
    """
    The hub URL with an explicit tab (the remembered one if missing).
    ---
    La URL del hub con la pestaña explícita: la suya si la trae; si no,
    `tab` (la que el hub tiene recordada).
    """
    if _path_of(url) != HUB_PATH or _tab_of(url) or not tab:
        return url
    return "%s%stab=%s" % (url, "&" if "?" in url else "?", tab)


def _hub_at_tab(url, tab):
    """
    The hub URL pointing at `tab` (the tab it was left on).
    ---
    La URL del hub apuntando a `tab`: dentro del hub se cambia de
    pestaña sin cargar página, así que al salir se apunta la pestaña en
    la que estaba de verdad.
    """
    if _path_of(url) != HUB_PATH or not tab:
        return url
    return "%s?tab=%s" % (HUB_PATH, tab)


def _hub_tab(company_user):
    """
    The tab the documentation hub has remembered for this user.
    ---
    La pestaña que el hub de Documentación tiene recordada (la última
    en la que estuvo el usuario).
    """
    state = PanelNavigationState.objects.filter(
        company_user=company_user, screen_key=HUB_SCREEN_KEY,
    ).values_list("state", flat=True).first()
    tab = state.get("active_tab") if isinstance(state, dict) else ""
    return tab if isinstance(tab, str) else ""


def _is_page_request(request):
    """
    True for a full-page GET of the panel by a panel user.

    ---

    True si es la carga de una página completa del panel por un usuario
    del panel: GET, no htmx, y (si el navegador lo indica) navegación
    de documento, no una petición de recursos.
    """
    if request.method != "GET":
        return False
    path = request.path
    if not path.startswith(PANEL_PREFIX):
        return False
    if any(path.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return False
    if request.headers.get("HX-Request"):
        return False
    fetch_dest = request.headers.get("Sec-Fetch-Dest")
    if fetch_dest and fetch_dest != "document":
        return False
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    return getattr(user, "company_user", None) is not None


def _next_stack(stack, current):
    """
    New stack and back URL after opening `current`.

    ---

    Pila nueva y URL de "Volver" tras abrir `current`.
    """
    current_key = _key(current)
    for index in range(len(stack) - 1, -1, -1):
        if _key(stack[index]) == current_key:
            back = stack[index - 1] if index > 0 else ""
            return stack[:index] + [current], back
    back = stack[-1] if stack else ""
    return (stack + [current])[-MAX_DEPTH:], back


class NavigationHistoryMiddleware:
    """
    Keep each user's page stack and expose the "Volver" URL.

    ---

    Mantiene la pila de páginas de cada usuario y expone la URL de
    "Volver" en `request.panel_back_url`. Solo guarda la página cuando
    la respuesta es HTML con estado 200: una descarga (PDF, Excel) o
    una redirección no entran en la pila.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.panel_back_url = ""
        if not _is_page_request(request):
            return self.get_response(request)

        company_user = request.user.company_user
        nav_state = PanelNavigationState.objects.filter(
            company_user=company_user, screen_key=SCREEN_KEY,
        ).first()
        state = nav_state.state if nav_state else {}
        stack = state.get("stack") if isinstance(state, dict) else None
        if not isinstance(stack, list):
            stack = []
        current = request.get_full_path()
        # S144: el hub, con su pestaña. La que tiene recordada ahora es
        # en la que estaba al salir (la entrada de arriba de la pila) y
        # en la que se abre si se entra sin ?tab=.
        if HUB_PATH in [_path_of(current)] + [_path_of(u) for u in stack]:
            hub_tab = _hub_tab(company_user)
            if stack:
                stack = stack[:-1] + [_hub_at_tab(stack[-1], hub_tab)]
            current = _with_hub_tab(current, hub_tab)
        new_stack, back_url = _next_stack(stack, current)
        request.panel_back_url = back_url

        response = self.get_response(request)

        content_type = response.get("Content-Type", "")
        if response.status_code == 200 and content_type.startswith(
            "text/html",
        ):
            PanelNavigationState.objects.update_or_create(
                company_user=company_user,
                screen_key=SCREEN_KEY,
                defaults={"state": {"stack": new_stack}},
            )
        return response


def back_url_context(request):
    """
    Template context: the "Volver" URL of the current page.

    ---

    Contexto de plantilla: `panel_back_url`, la URL de "Volver" de la
    página actual ("" si no hay página anterior).
    """
    return {"panel_back_url": getattr(request, "panel_back_url", "")}
