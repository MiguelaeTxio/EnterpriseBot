# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/mixins.py
"""
Authentication and authorisation mixins for the panel application.
Provides layered access control for CompanyUser accounts.
---
Mixins de autenticación y autorización para la aplicación panel.
Proporciona control de acceso por capas para las cuentas CompanyUser.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from ivr_config.models import CompanyUser


class PanelLoginRequiredMixin(LoginRequiredMixin):
    """
    Mixin that requires the user to be authenticated.
    Redirects unauthenticated users to /panel/login/.
    ---
    Mixin que requiere que el usuario esté autenticado.
    Redirige a los usuarios no autenticados a /panel/login/.
    """

    login_url = "/panel/login/"


class CompanyUserRequiredMixin(PanelLoginRequiredMixin):
    """
    Mixin that requires the authenticated user to have an active CompanyUser record.
    Redirects to /panel/login/ with an error message if no active CompanyUser is found.
    ---
    Mixin que requiere que el usuario autenticado tenga un registro CompanyUser activo.
    Redirige a /panel/login/ con un mensaje de error si no se encuentra un CompanyUser activo.
    """

    def dispatch(self, request, *args, **kwargs):
        """
        Verify that the authenticated user has an active linked CompanyUser.
        Unauthenticated users are redirected to login before the CompanyUser check.
        ---
        Verifica que el usuario autenticado tiene un CompanyUser activo vinculado.
        Los usuarios no autenticados son redirigidos al login antes de la comprobación.
        """
        # Redirect unauthenticated users to login immediately.
        # Redirigir a usuarios no autenticados al login de inmediato.
        if not request.user.is_authenticated:
            return redirect(self.login_url)

        # Verify the user has an active CompanyUser record linked.
        # Verificar que el usuario tiene un registro CompanyUser activo vinculado.
        company_user = getattr(request.user, "company_user", None)
        if company_user is None or not company_user.is_active:
            messages.error(
                request,
                "Tu cuenta no tiene acceso al panel. Contacta con tu administrador."
            )
            return redirect(self.login_url)

        # Force password change on first login or after admin reset.
        # Forzar cambio de contraseña en el primer acceso o tras reset del ADMIN.
        password_change_url = "/panel/password/change/"
        if company_user.must_change_password and request.path != password_change_url:
            return redirect(password_change_url)

        return super().dispatch(request, *args, **kwargs)


class WorkshopRequiredMixin(CompanyUserRequiredMixin):
    """
    Mixin that grants access to CompanyUsers with the WORKSHOP or ADMIN role.
    Any other role receives HTTP 403 Forbidden.
    Intended for workshop work-order entry views introduced in Hito 7.
    ---
    Mixin que concede acceso a CompanyUsers con rol WORKSHOP o ADMIN.
    Cualquier otro rol recibe HTTP 403 Forbidden.
    Destinado a las vistas de entrada de partes de taller introducidas en el Hito 7.
    """

    def dispatch(self, request, *args, **kwargs):
        """
        Verify that the authenticated CompanyUser holds the WORKSHOP or ADMIN role.
        Delegates to parent for authentication and CompanyUser checks first.
        ---
        Verifica que el CompanyUser autenticado posee el rol WORKSHOP o ADMIN.
        Delega al padre para las comprobaciones de autenticación y CompanyUser primero.
        """
        # Delegate authentication and CompanyUser checks to parent first.
        # Delegar las comprobaciones de autenticación y CompanyUser al padre primero.
        response = super().dispatch(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return response

        company_user = getattr(request.user, "company_user", None)
        if company_user is None:
            return response

        # Grant access only to WORKSHOP and ADMIN roles.
        # Conceder acceso únicamente a los roles WORKSHOP y ADMIN.
        allowed_roles = {
            CompanyUser.ROLE_WORKSHOP,
            CompanyUser.ROLE_ADMIN,
        }
        if company_user.role not in allowed_roles:
            return HttpResponseForbidden(
                "Acceso denegado. Esta sección requiere el rol de Operario de taller."
            )

        return response


class AdminRoleRequiredMixin(CompanyUserRequiredMixin):
    """
    Mixin that requires the authenticated CompanyUser to have the ADMIN role.
    Returns HTTP 403 Forbidden if the user has the OPERATOR role.
    ---
    Mixin que requiere que el CompanyUser autenticado tenga el rol ADMIN.
    Devuelve HTTP 403 Forbidden si el usuario tiene el rol OPERATOR.
    """

    def dispatch(self, request, *args, **kwargs):
        """
        Verify that the authenticated CompanyUser holds the ADMIN role.
        Delegates to parent for authentication and CompanyUser checks first.
        ---
        Verifica que el CompanyUser autenticado posee el rol ADMIN.
        Delega al padre para las comprobaciones de autenticación y CompanyUser primero.
        """
        # Delegate authentication and CompanyUser checks to parent first.
        # Delegar las comprobaciones de autenticación y CompanyUser al padre primero.
        response = super().dispatch(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return response

        company_user = getattr(request.user, "company_user", None)
        if company_user is None:
            return response

        # Block access if the user does not hold the ADMIN role.
        # Bloquear el acceso si el usuario no posee el rol ADMIN.
        if company_user.role != "ADMIN":
            return HttpResponseForbidden(
                "Acceso denegado. Esta sección requiere el rol de Administrador."
            )

        return response
