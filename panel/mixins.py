
# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/mixins.py
"""
Authentication and authorisation mixins for the panel application.
Provides layered access control for CompanyUser accounts.

Mixin hierarchy:
  PanelLoginRequiredMixin      — authentication gate (redirects to /panel/login/).
  CompanyUserRequiredMixin     — active CompanyUser + password-change enforcement.
  AdminRoleRequiredMixin       — restricts to ADMIN role only.
  WorkshopRequiredMixin        — restricts to WORKSHOP and ADMIN roles.
  SupervisorAccessMixin        — restricts to SUPERVISOR and ADMIN roles.
                                 Introduced in Hito 8 / Bloque G for PDF work-order
                                 review and export workflow.
  AssistanceRequiredMixin      — restricts to ASSISTANCE and ADMIN roles.
                                 Introduced in Hito 16 for the budget wizard.
  BudgetAuditAccessMixin       — restricts to ADMIN, or ASSISTANCE with the
                                 per-user can_view_budget_breakdown flag.
                                 Introduced for special ASSISTANCE users who
                                 need budget history/breakdown visibility.
---
Mixins de autenticación y autorización para la aplicación panel.
Proporciona control de acceso por capas para las cuentas CompanyUser.

Jerarquía de mixins:
  PanelLoginRequiredMixin      — barrera de autenticación (redirige a /panel/login/).
  CompanyUserRequiredMixin     — CompanyUser activo + forzado de cambio de contraseña.
  AdminRoleRequiredMixin       — restringe al rol ADMIN exclusivamente.
  WorkshopRequiredMixin        — restringe a los roles WORKSHOP y ADMIN.
  SupervisorAccessMixin        — restringe a los roles SUPERVISOR y ADMIN.
                                 Introducido en Hito 8 / Bloque G para el flujo de
                                 revisión y exportación de partes de trabajo PDF.
  AssistanceRequiredMixin      — restringe a los roles ASSISTANCE y ADMIN.
                                 Introducido en Hito 16 para el asistente de presupuestos.
  BudgetAuditAccessMixin       — restringe a ADMIN, o ASSISTANCE con el flag
                                 por usuario can_view_budget_breakdown.
                                 Introducido para usuarios ASISTENCIA especiales
                                 que necesitan visibilidad de historial/desglose.
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
        # Conceder acceso a WORKSHOP, WORKSHOPBOSS y ADMIN.
        # Grant access to WORKSHOP, WORKSHOPBOSS and ADMIN roles.
        allowed_roles = {
            CompanyUser.ROLE_WORKSHOP,
            CompanyUser.ROLE_WORKSHOPBOSS,
            CompanyUser.ROLE_ADMIN,
        }
        if company_user.role not in allowed_roles:
            return HttpResponseForbidden(
                "Acceso denegado. Esta sección requiere el rol de Operario o Jefe de taller."
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


class AssistanceRequiredMixin(CompanyUserRequiredMixin):
    """
    Mixin that grants access to CompanyUsers with the ASSISTANCE or ADMIN role.
    Introduced in Hito 16 for the ASISTENCIA budget wizard.
    Any other role receives a redirect to the dashboard with an error message.
    ---
    Mixin que concede acceso a CompanyUsers con rol ASSISTANCE o ADMIN.
    Introducido en el Hito 16 para el asistente de presupuestos de ASISTENCIA.
    Cualquier otro rol recibe una redireccion al dashboard con mensaje de error.
    """

    def dispatch(self, request, *args, **kwargs):
        """
        Verify that the authenticated CompanyUser holds the ASSISTANCE
        or ADMIN role. Delegates to parent for authentication and
        CompanyUser checks first.
        ---
        Verifica que el CompanyUser autenticado posee el rol ASSISTANCE
        o ADMIN. Delega al padre las comprobaciones de autenticacion
        y CompanyUser primero.
        """
        response = super().dispatch(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return response

        company_user = getattr(request.user, "company_user", None)
        if company_user is None:
            return response

        allowed_roles = {
            CompanyUser.ROLE_ASSISTANCE,
            CompanyUser.ROLE_ADMIN,
        }
        if company_user.role not in allowed_roles:
            messages.error(
                request,
                "Acceso denegado. Esta seccion requiere el rol de "
                "Operario de Asistencia o Administrador.",
            )
            return redirect("/panel/")

        return response


class BudgetAuditAccessMixin(CompanyUserRequiredMixin):
    """
    Mixin that grants access to the budget history list and detail/
    breakdown views. ADMIN always has access. ASSISTANCE has access only
    when their CompanyUser.can_view_budget_breakdown flag is True — a
    granular per-user override, not a role-wide grant, introduced for
    special ASSISTANCE users who need audit visibility into calculated
    budgets without any other ADMIN privilege.
    Any other role, or an ASSISTANCE user without the flag, receives a
    redirect to the dashboard with an error message.
    ---
    Mixin que concede acceso al listado de historial de presupuestos y a
    las vistas de detalle/desglose. ADMIN tiene acceso siempre.
    ASSISTANCE tiene acceso solo cuando su flag
    CompanyUser.can_view_budget_breakdown es True — un override granular
    por usuario, no una concesión a todo el rol, introducido para
    usuarios ASISTENCIA especiales que necesitan visibilidad de
    auditoría sobre los presupuestos calculados sin ningún otro
    privilegio de ADMIN.
    Cualquier otro rol, o un usuario ASSISTANCE sin el flag, recibe una
    redirección al dashboard con mensaje de error.
    """

    def dispatch(self, request, *args, **kwargs):
        """
        Verify that the authenticated CompanyUser holds ADMIN, or holds
        ASSISTANCE with can_view_budget_breakdown=True. Delegates to
        parent for authentication and CompanyUser checks first.
        ---
        Verifica que el CompanyUser autenticado posee ADMIN, o posee
        ASSISTANCE con can_view_budget_breakdown=True. Delega al padre
        las comprobaciones de autenticación y CompanyUser primero.
        """
        response = super().dispatch(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return response

        company_user = getattr(request.user, "company_user", None)
        if company_user is None:
            return response

        has_access = (
            company_user.role == CompanyUser.ROLE_ADMIN
            or (
                company_user.role == CompanyUser.ROLE_ASSISTANCE
                and company_user.can_view_budget_breakdown
            )
        )
        if not has_access:
            messages.error(
                request,
                "Acceso denegado. Esta sección requiere el rol de "
                "Administrador, o el permiso de visualización de "
                "desglose de presupuestos.",
            )
            return redirect("/panel/")

        return response


class SupervisorAccessMixin(CompanyUserRequiredMixin):
    """
    Mixin that grants access to CompanyUsers with the SUPERVISOR or ADMIN role.
    Introduced in Hito 8 / Bloque G for the PDF work-order review and export
    workflow. Covers: WorkOrderUploadView, WorkOrderListView, WorkOrderExportView
    and WorkOrderMarkReviewedView.

    Access matrix:
      ADMIN      — full access (upload, list, review, export).
      SUPERVISOR — same as ADMIN for work-order views only; no access to IVR
                   configuration views (sections, contacts, users, call flows…).
      Any other role — HTTP 403 Forbidden, redirected to dashboard with error message.
    ---
    Mixin que concede acceso a CompanyUsers con rol SUPERVISOR o ADMIN.
    Introducido en el Hito 8 / Bloque G para el flujo de revisión y exportación
    de partes de trabajo PDF. Cubre: WorkOrderUploadView, WorkOrderListView,
    WorkOrderExportView y WorkOrderMarkReviewedView.

    Matriz de acceso:
      ADMIN      — acceso completo (subida, lista, revisión, exportación).
      SUPERVISOR — igual que ADMIN únicamente en vistas de partes; sin acceso a
                   vistas de configuración IVR (secciones, contactos, usuarios,
                   flujos de llamada…).
      Cualquier otro rol — HTTP 403 Forbidden, redirigido al dashboard con mensaje
                           de error.
    """

    def dispatch(self, request, *args, **kwargs):
        """
        Verify that the authenticated CompanyUser holds the SUPERVISOR or ADMIN role.
        Delegates to parent for authentication and CompanyUser checks first.
        On insufficient role, redirects to the dashboard with an error message
        instead of returning a bare 403, to provide a better UX within the panel.
        ---
        Verifica que el CompanyUser autenticado posee el rol SUPERVISOR o ADMIN.
        Delega al padre para las comprobaciones de autenticación y CompanyUser primero.
        En caso de rol insuficiente, redirige al dashboard con un mensaje de error
        en lugar de devolver un 403 desnudo, para mejorar la experiencia en el panel.
        """
        # Delegate authentication and CompanyUser checks to parent first.
        # Delegar las comprobaciones de autenticación y CompanyUser al padre primero.
        response = super().dispatch(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return response

        company_user = getattr(request.user, "company_user", None)
        if company_user is None:
            return response

        # Grant access only to SUPERVISOR and ADMIN roles.
        # Conceder acceso a SUPERVISOR, WORKSHOPBOSS y ADMIN.
        # Grant access to SUPERVISOR, WORKSHOPBOSS and ADMIN roles.
        allowed_roles = {
            CompanyUser.ROLE_SUPERVISOR,
            CompanyUser.ROLE_WORKSHOPBOSS,
            CompanyUser.ROLE_ADMIN,
        }
        if company_user.role not in allowed_roles:
            messages.error(
                request,
                "Acceso denegado. Esta sección requiere el rol de Supervisor, Jefe de taller o Administrador.",
            )
            return redirect("/panel/")

        return response


class DocsUploadAccessMixin(CompanyUserRequiredMixin):
    """
    Mixin that grants access to CompanyUsers with the DOCS_SUPERVISOR
    or ADMIN role. Introduced in Hito 23 for the cost-center
    documentation upload flow (MachineDocumentBatchUploadView). The
    read-only listing view uses plain CompanyUserRequiredMixin instead
    -- per Miguel Ángel's explicit decision, the listing is visible to
    any authenticated panel user, only the upload is restricted.
    ---
    Mixin que concede acceso a CompanyUsers con rol DOCS_SUPERVISOR o
    ADMIN. Introducido en el Hito 23 para el flujo de subida de
    documentación de centros de gasto
    (MachineDocumentBatchUploadView). La vista de listado de solo
    lectura usa CompanyUserRequiredMixin directamente en su lugar --
    por decisión explícita de Miguel Ángel, el listado es visible para
    cualquier usuario autenticado del panel, solo la subida está
    restringida.
    """

    def dispatch(self, request, *args, **kwargs):
        """
        Verify that the authenticated CompanyUser holds the
        DOCS_SUPERVISOR or ADMIN role.
        ---
        Verifica que el CompanyUser autenticado posee el rol
        DOCS_SUPERVISOR o ADMIN.
        """
        response = super().dispatch(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return response

        company_user = getattr(request.user, "company_user", None)
        if company_user is None:
            return response

        allowed_roles = {
            CompanyUser.ROLE_DOCS_SUPERVISOR,
            CompanyUser.ROLE_ADMIN,
        }
        if company_user.role not in allowed_roles:
            messages.error(
                request,
                "Acceso denegado. Esta sección requiere el rol de "
                "Supervisor de Documentación o Administrador.",
            )
            return redirect("/panel/")

        return response


class WorkOrderFormAccessMixin(CompanyUserRequiredMixin):
    """
    Mixin that grants access to the work-order entry form
    (WorkOrderEntryFormView) for the WORKSHOP, SUPERVISOR and ADMIN roles.

    This mixin exists because the form view serves two distinct use cases:
      - WORKSHOP operators create and edit their own daily parts.
      - SUPERVISOR and ADMIN review and edit any operator's digital parts
        from the admin history view (WorkOrderAdminHistoryView).

    WorkshopRequiredMixin cannot be used because it excludes SUPERVISOR.
    SupervisorAccessMixin cannot be used because it excludes WORKSHOP.
    This mixin is the intersection that covers both cases cleanly.

    Access matrix:
      ADMIN        — full access (create, edit any part).
      SUPERVISOR   — full access (edit any operator's part from history).
      WORKSHOPBOSS — full access (edit any operator's part from history,
                     same scope as SUPERVISOR — confirmed 2026-07-08).
      WORKSHOP     — access to create and edit their own parts only
                     (enforced inside WorkOrderEntryFormView via _is_elevated).
      Any other role — redirect to dashboard with error message.
    ---
    Mixin que concede acceso al formulario de entrada de partes
    (WorkOrderEntryFormView) para los roles WORKSHOP, SUPERVISOR y ADMIN.

    Existe porque la vista sirve dos casos de uso distintos:
      - Operarios WORKSHOP crean y editan sus propios partes diarios.
      - SUPERVISOR y ADMIN revisan y editan partes de cualquier operario
        desde la vista de historial (WorkOrderAdminHistoryView).

    WorkshopRequiredMixin no puede usarse porque excluye a SUPERVISOR.
    SupervisorAccessMixin no puede usarse porque excluye a WORKSHOP.
    Este mixin es la interseccion que cubre ambos casos de forma limpia.

    Matriz de acceso:
      ADMIN        — acceso completo (crear, editar cualquier parte).
      SUPERVISOR   — acceso completo (editar partes de cualquier operario).
      WORKSHOPBOSS — acceso completo (editar partes de cualquier operario
                     desde el historial, mismo alcance que SUPERVISOR —
                     confirmado 2026-07-08).
      WORKSHOP     — acceso para crear y editar sus propios partes
                     (restriccion a propios aplicada en WorkOrderEntryFormView
                     mediante la variable _is_elevated).
      Cualquier otro rol — redireccion al dashboard con mensaje de error.
    """

    def dispatch(self, request, *args, **kwargs):
        """
        Verify that the authenticated CompanyUser holds one of the allowed
        roles for work-order form access. Delegates authentication and
        CompanyUser checks to parent first.
        ---
        Verifica que el CompanyUser autenticado posee uno de los roles
        permitidos para el formulario de partes. Delega al padre las
        comprobaciones de autenticacion y CompanyUser primero.
        """
        response = super().dispatch(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return response

        company_user = getattr(request.user, "company_user", None)
        if company_user is None:
            return response

        allowed_roles = {
            CompanyUser.ROLE_WORKSHOP,
            CompanyUser.ROLE_WORKSHOPBOSS,
            CompanyUser.ROLE_SUPERVISOR,
            CompanyUser.ROLE_ADMIN,
        }
        if company_user.role not in allowed_roles:
            messages.error(
                request,
                "Acceso denegado. Esta sección requiere el rol de "
                "Operario, Jefe de taller, Supervisor o Administrador.",
            )
            return redirect("/panel/")

        return response



