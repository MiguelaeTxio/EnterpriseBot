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
