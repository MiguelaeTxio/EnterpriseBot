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
- `request.panel_back_url` es la página anterior a la actual en esa
  pila, y el procesador de contexto `back_url_context` la pone en
  todas las plantillas como `panel_back_url`. El botón "Volver" enlaza
  ahí; si no hay página anterior, no se pinta.
"""
from panel.models import PanelNavigationState

SCREEN_KEY = "back_stack"
MAX_DEPTH = 30
PANEL_PREFIX = "/panel/"
# Endpoints that are never pages of their own.
# Endpoints que nunca son páginas por sí mismos.
EXCLUDED_PREFIXES = ("/panel/navegacion/",)


def _path_of(url):
    """
    Path of a stored URL, without its querystring.

    ---

    Path de una URL guardada, sin la querystring.
    """
    return url.split("?", 1)[0]


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
    current_path = _path_of(current)
    for index in range(len(stack) - 1, -1, -1):
        if _path_of(stack[index]) == current_path:
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
        new_stack, back_url = _next_stack(stack, request.get_full_path())
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
