# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/mixins.py
"""
Access control of the new interface.

---

Control de acceso de la nueva interfaz. Hasta S163 (26/11) solo para
superusuarios; desde entonces, por permisos (Permisos, perfiles):

- Permisos: solo el superusuario.
- Cada ruta pide la clave de su sección o vista (tabla PREFIX_KEYS; los
  listados, fichas y exportaciones la toman de ?s=&t=).
- Mirar (GET) pide «Ver»; cambiar algo (POST...) pide «Ver y
  modificar». Las preferencias de pantalla (estado, menú, grupos de
  selección, plantillas de pantalla) solo piden poder entrar.
- Una ruta que no esté en la tabla queda para el superusuario: así una
  pantalla nueva nace cerrada.
Sin sesión, al inicio de sesión del panel.
"""

from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

LOGIN_URL = "/panel/login/"
ROOT = "/panel/nueva-interfaz/"
ANY = "*"
SUPERUSER = "!"

# Rutas cuya clave sale de ?s= y ?t= (listados, fichas, exportar...).
FROM_PARAMS = {"", "listado", "fila", "exportar", "tarjeta"}
# Preferencias de pantalla de cada uno: basta con poder entrar.
UI_PREFS = {"menu", "estado", "grupos", "plantillas-pantalla"}

PREFIX_KEYS = {
    "permisos": SUPERUSER,
    # Personal
    "persona": "per", "personas": "per", "acceso": "per",
    "solicitudes": "per", "fichajes": "per", "albaranes": "per",
    "trabajadores": "per", "bajas": "per", "ausencias": "per",
    "partes": "per", "epis": "per", "avisar": "per", "pedir": "per",
    "vacaciones": "per",
    # Empresa
    "requisitos": "doc", "dosieres": "doc", "circulares": "doc",
    "avisos": "doc", "horarios": "doc", "tipos-fichaje": "doc",
    "personal": "doc", "pagos": "doc.liquidaciones",
    "cae": "doc.correos_cae", "seguros": "doc.seguros",
    "firmas": "doc.firmas", "nominas": "doc.nominas",
    # Centros de gasto
    "maquina": "cdg", "maquinas": "cdg", "revisiones": "cdg",
    "lecturas": "cdg", "accesorios": "cdg", "repostajes": "cdg",
    "libro-historial": "cdg", "revisiones-que-faltan": "cdg",
    "seguridad": "cdg", "equipos": "cdg",
    # Tráfico (S165)
    "trafico": "tra",
    # Documentos de cualquiera de las tres
    "documentos": ANY, "documento": ANY, "subir": ANY,
}
# Excepciones dentro de un prefijo: (prefijo, trozo de ruta) -> clave.
PATH_KEYS = (
    ("vacaciones", "/reglas/", "doc.vacaciones"),
    ("vacaciones", "/tipos-ausencia/", "doc.tipos_ausencia"),
    ("vacaciones", "/ajustes/", "doc.vacaciones"),
    ("vacaciones", "/cuadrante/", "per.saldo_vacaciones"),
    ("vacaciones", "/nombres/", "per.saldo_vacaciones"),
    ("epis", "/catalogo/", "doc.catalogo_epis"),
    ("epis", "/lotes/", "doc.lotes_epis"),
    ("nominas", "/entregas/", "doc.entregas_nominas"),
    ("pagos", "/origen/", "per"),
)
SECTION_KEYS = ("doc", "per", "cdg", "tra")


def required_key(request):
    """
    The permission key a new-interface request needs.

    ---

    La clave de Permisos que pide esta petición (o ANY / SUPERUSER).
    """
    rest = request.path[len(ROOT):] if request.path.startswith(ROOT) else ""
    first = rest.split("/", 1)[0]
    if first in FROM_PARAMS:
        params = request.GET if request.method == "GET" else request.POST
        section = params.get("s") or request.GET.get("s", "")
        tab = params.get("t") or request.GET.get("t", "")
        if section == "permisos":
            return SUPERUSER
        if section in SECTION_KEYS:
            return "%s.%s" % (section, tab) if tab else section
        return ANY
    if first in UI_PREFS:
        return ANY
    for prefix, piece, key in PATH_KEYS:
        if first == prefix and piece in "/" + rest:
            return key
    return PREFIX_KEYS.get(first, SUPERUSER)


def allowed(company_user, request):
    """
    True if this user may make this request.

    ---

    True si el usuario puede hacer esta petición: «Ver» para mirar,
    «Ver y modificar» para cambiar algo.
    """
    from new_ui.models import UiViewGrant
    from new_ui.permissions import RANK, effective_levels

    if company_user.user.is_superuser:
        return True
    key = required_key(request)
    if key == SUPERUSER:
        return False
    rest = request.path[len(ROOT):] if request.path.startswith(ROOT) else ""
    looking = (request.method in ("GET", "HEAD")
               or rest.split("/", 1)[0] in UI_PREFS)
    need = RANK[UiViewGrant.LEVEL_VIEW if looking
                else UiViewGrant.LEVEL_EDIT]
    keys = list(SECTION_KEYS) if key == ANY else [key]
    levels = effective_levels(company_user, keys)
    return any(RANK[levels[k][0]] >= need for k in keys)


def can_enter(company_user):
    """
    True if the user can open at least one section of the new interface.

    ---

    True si puede abrir al menos una sección (para el enlace del menú).
    """
    from new_ui.permissions import RANK, effective_levels

    if company_user is None:
        return False
    if company_user.user.is_superuser:
        return True
    levels = effective_levels(company_user, list(SECTION_KEYS))
    return any(RANK[level] for level, _origin in levels.values())


class SuperuserRequiredMixin:
    """
    Active panel users with permission for the request.

    ---

    Usuarios del panel activos con permiso para la petición (el nombre
    se mantiene: lo usan todas las vistas; desde S163, 26/11, ya no es
    solo superusuario).
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(LOGIN_URL)
        company_user = getattr(request.user, "company_user", None)
        if company_user is None or not company_user.is_active:
            messages.error(request, "Tu cuenta no tiene acceso al panel. "
                                    "Contacta con tu administrador.")
            return redirect(LOGIN_URL)
        # Como en el panel: primero el cambio de contraseña pendiente.
        if company_user.must_change_password:
            return redirect("/panel/password/change/")
        if not allowed(company_user, request):
            if request.method == "GET" and not request.headers.get(
                    "HX-Request") and required_key(request) not in (
                    ANY, SUPERUSER) and request.path == ROOT:
                messages.error(request, "No tienes acceso a esa sección.")
                return redirect(ROOT)
            return HttpResponseForbidden(
                "No tienes permiso para esto en la nueva interfaz.")
        return super().dispatch(request, *args, **kwargs)
