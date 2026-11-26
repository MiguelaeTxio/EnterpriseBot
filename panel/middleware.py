# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/middleware.py
"""
Middleware layer for the panel application.
Blocks CompanyUser access to the standard Django admin interface.
---
Capa de middleware para la aplicación panel.
Bloquea el acceso de CompanyUser a la interfaz de administración estándar de Django.
"""

from django.http import HttpResponseForbidden


class CompanyUserAdminBlockMiddleware:
    """
    Middleware that prevents CompanyUser accounts from accessing /admin/.
    Users with is_staff=True (superusers) are allowed through without restriction.
    Any authenticated user linked to a CompanyUser record is blocked from /admin/.
    ---
    Middleware que impide a las cuentas CompanyUser acceder a /admin/.
    Los usuarios con is_staff=True (superusuarios) pasan sin restricción.
    Cualquier usuario autenticado vinculado a un registro CompanyUser queda bloqueado en /admin/.
    """

    def __init__(self, get_response):
        """
        One-time configuration and initialisation.
        ---
        Configuración e inicialización única al arrancar el servidor.
        """
        self.get_response = get_response

    def __call__(self, request):
        """
        Block CompanyUser access to any path starting with /admin/.
        Superusers (is_staff=True) bypass this check entirely.
        ---
        Bloquea el acceso de CompanyUser a cualquier ruta que empiece por /admin/.
        Los superusuarios (is_staff=True) omiten esta comprobación por completo.
        """
        # Only evaluate authenticated users attempting to access /admin/.
        # Solo se evalúan usuarios autenticados que intentan acceder a /admin/.
        if (
            request.path.startswith("/admin/")
            and request.user.is_authenticated
            and not request.user.is_staff
            and hasattr(request.user, "company_user")
        ):
            return HttpResponseForbidden(
                "Acceso denegado. El panel de administración no está disponible para tu cuenta."
            )

        return self.get_response(request)


class HtmxLoginRedirectMiddleware:
    """
    S117 -- fallo real reportado por Miguel Ángel con captura: con la
    sesión caducada, al cambiar un filtro de Centros de gasto la página
    de LOGIN aparecía incrustada dentro de la tabla. Las peticiones htmx
    siguen la redirección 302 al login de forma transparente y htmx
    mete ese HTML en el hueco de destino.

    Para cualquier petición htmx (cabecera HX-Request) cuya respuesta
    redirija al login del panel, se devuelve en su lugar un 200 vacío
    con HX-Redirect: htmx navega la página ENTERA al login (que, como
    siempre, lleva al inicio del panel tras entrar). Un único punto,
    válido para todas las vistas del panel sin tocarlas.
    ---
    For any htmx request whose response redirects to the panel login,
    return an empty 200 with HX-Redirect so htmx navigates the whole
    page to the login instead of swapping the login HTML into the
    target element.
    """

    LOGIN_PATH = "/panel/login/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from urllib.parse import urlparse

        from django.http import HttpResponse

        response = self.get_response(request)
        if (
            request.headers.get("HX-Request") == "true"
            and response.status_code in (301, 302, 303, 307, 308)
            and urlparse(response.get("Location", "")).path.startswith(self.LOGIN_PATH)
        ):
            htmx_response = HttpResponse(status=200)
            htmx_response["HX-Redirect"] = self.LOGIN_PATH
            return htmx_response
        return response



class PanelAreaGateMiddleware:
    """
    S163 (26/11): the panel area gate.

    ---

    Puerta por áreas del panel actual (S163, Miguel Ángel: «nadie entra
    a nada que no tenga dado»). Con panel.access_rules.ENFORCE
    encendido: quien no tiene permiso en el área de la pantalla
    («panel.<área>» en Permisos) no entra; con «Ver» entra y siguen
    mandando las reglas de cada pantalla; con «Ver y modificar» pasa
    también las reglas de rol. El superusuario pasa siempre. Apagado,
    no hace nada.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        from django.contrib import messages
        from django.shortcuts import redirect

        from panel import access_rules

        if not access_rules.ENFORCE or not request.path.startswith(
                "/panel/"):
            return None
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or user.is_superuser:
            return None
        company_user = getattr(user, "company_user", None)
        match = getattr(request, "resolver_match", None)
        if company_user is None or not company_user.is_active or not match:
            return None
        slug, level = access_rules.area_level_of_route(
            company_user, match.route)
        if slug is None:
            return None
        request.panel_area_level = level
        if level != "NONE":
            return None
        if request.method != "GET" or request.headers.get("HX-Request"):
            return HttpResponseForbidden(
                "Sin acceso a esta parte del panel.")
        messages.error(request, "No tienes acceso a esa parte del panel.")
        return redirect("/panel/")
