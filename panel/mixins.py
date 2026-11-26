
# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/mixins.py
"""
Authentication and authorisation mixins for the panel application.
Provides layered access control for CompanyUser accounts.

Mixin hierarchy:
  PanelLoginRequiredMixin      — authentication gate (redirects to
  /panel/login/).
  CompanyUserRequiredMixin     — active CompanyUser + password-change
  enforcement.
  AdminRoleRequiredMixin       — restricts to ADMIN role only.
  WorkshopRequiredMixin        — restricts to WORKSHOP and ADMIN roles.
  SupervisorAccessMixin        — restricts to SUPERVISOR and ADMIN roles.
                                 Introduced in Hito 8 / Bloque G for PDF
                                 work-order
                                 review and export workflow.
  AssistanceRequiredMixin      — restricts to ASSISTANCE and ADMIN roles.
                                 Introduced in Hito 16 for the budget wizard.
  BudgetAuditAccessMixin       — restricts to ADMIN, or ASSISTANCE with the
                                 per-user can_view_budget_breakdown flag.
                                 Introduced for special ASSISTANCE users who
                                 need budget history/breakdown visibility.
  SuperuserRequiredMixin       — restricts to Django is_superuser=True, not a
                                 CompanyUser role. Introduced in S021 for
                                 sections meant for a single trusted account
                                 (e.g. draft work orders), replacing the
                                 hardcoded-username antipattern previously
                                 used in the sidebar for the Django Admin link.
---
Mixins de autenticación y autorización para la aplicación panel.
Proporciona control de acceso por capas para las cuentas CompanyUser.

Jerarquía de mixins:
  PanelLoginRequiredMixin      — barrera de autenticación (redirige a
  /panel/login/).
  CompanyUserRequiredMixin     — CompanyUser activo + forzado de cambio de
  contraseña.
  AdminRoleRequiredMixin       — restringe al rol ADMIN exclusivamente.
  WorkshopRequiredMixin        — restringe a los roles WORKSHOP y ADMIN.
  SupervisorAccessMixin        — restringe a los roles SUPERVISOR y ADMIN.
                                 Introducido en Hito 8 / Bloque G para el flujo
                                 de
                                 revisión y exportación de partes de trabajo
                                 PDF.
  AssistanceRequiredMixin      — restringe a los roles ASSISTANCE y ADMIN.
                                 Introducido en Hito 16 para el asistente de
                                 presupuestos.
  BudgetAuditAccessMixin       — restringe a ADMIN, o ASSISTANCE con el flag
                                 por usuario can_view_budget_breakdown.
                                 Introducido para usuarios ASISTENCIA
                                 especiales
                                 que necesitan visibilidad de
                                 historial/desglose.
  SuperuserRequiredMixin       — restringe a is_superuser=True de Django, no a
                                 un rol de CompanyUser. Introducido en S021
                                 para
                                 secciones pensadas para una única cuenta de
                                 confianza (p. ej. borradores de partes),
                                 sustituyendo el antipatrón de username
                                 hardcodeado usado antes en el sidebar para el
                                 enlace al Django Admin.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models import Q
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
    Mixin that requires the authenticated user to have an active CompanyUser
    record.
    Redirects to /panel/login/ with an error message if no active CompanyUser
    is found.
    ---
    Mixin que requiere que el usuario autenticado tenga un registro CompanyUser
    activo.
    Redirige a /panel/login/ con un mensaje de error si no se encuentra un
    CompanyUser activo.
    """

    def dispatch(self, request, *args, **kwargs):
        """
        Verify that the authenticated user has an active linked CompanyUser.
        Unauthenticated users are redirected to login before the CompanyUser
        check.
        ---
        Verifica que el usuario autenticado tiene un CompanyUser activo
        vinculado.
        Los usuarios no autenticados son redirigidos al login antes de la
        comprobación.
        """
        # Redirect unauthenticated users to login immediately.
        # Redirigir a usuarios no autenticados al login de inmediato.
        if not request.user.is_authenticated:
            return redirect(self.login_url)

        # Verify the user has an active CompanyUser record linked.
        # Verificar que el usuario tiene un registro CompanyUser activo
        # vinculado.
        company_user = getattr(request.user, "company_user", None)
        if company_user is None or not company_user.is_active:
            messages.error(
                request,
                "Tu cuenta no tiene acceso al panel. Contacta con tu "
                "administrador."
            )
            return redirect(self.login_url)

        # Force password change on first login or after admin reset.
        # Forzar cambio de contraseña en el primer acceso o tras reset del
        # ADMIN.
        password_change_url = "/panel/password/change/"
        if (
            company_user.must_change_password
            and request.path != password_change_url
        ):
            return redirect(password_change_url)

        return super().dispatch(request, *args, **kwargs)


def _company_user_for_role_check(request):
    """
    Returns the active CompanyUser of the request when a role check can
    be performed, or None when the request must fall through to the
    authentication checks of CompanyUserRequiredMixin (anonymous user,
    no CompanyUser, inactive CompanyUser).

    Every role mixin of this module must run its role check BEFORE
    calling super().dispatch(): super().dispatch() ends in
    View.dispatch(), which runs the real handler (get/post). Checking
    the role afterwards (the pattern used until S117) let a user
    without permission execute a POST -- delete, deactivate... -- and
    only then receive the 403/redirect, with the change already
    written to the database.
    ---
    Devuelve el CompanyUser activo de la petición cuando se puede
    comprobar el rol, o None cuando la petición debe seguir hacia las
    comprobaciones de autenticación de CompanyUserRequiredMixin
    (anónimo, sin CompanyUser, CompanyUser inactivo).

    Todo mixin de rol de este módulo debe comprobar el rol ANTES de
    llamar a super().dispatch(): super().dispatch() termina en
    View.dispatch(), que ejecuta el manejador real (get/post).
    Comprobar el rol después (patrón usado hasta S117) dejaba a un
    usuario sin permiso ejecutar un POST -- borrar, dar de baja... --
    y solo después recibir el 403/redirección, con el cambio ya
    escrito en la base de datos.
    """
    if not request.user.is_authenticated:
        return None
    company_user = getattr(request.user, "company_user", None)
    if company_user is None or not company_user.is_active:
        return None
    # S163 (26/11): con la puerta por áreas encendida, quien tiene «Ver
    # y modificar» en el área de esta pantalla pasa la regla de rol
    # (PanelAreaGateMiddleware deja el nivel en la petición).
    if getattr(request, "panel_area_level", None) == "EDIT":
        return None
    return company_user


class WorkshopRequiredMixin(CompanyUserRequiredMixin):
    """
    Mixin that grants access to CompanyUsers with the WORKSHOP or ADMIN role.
    Any other role receives HTTP 403 Forbidden.
    Intended for workshop work-order entry views introduced in Hito 7.
    ---
    Mixin que concede acceso a CompanyUsers con rol WORKSHOP o ADMIN.
    Cualquier otro rol recibe HTTP 403 Forbidden.
    Destinado a las vistas de entrada de partes de taller introducidas en el
    Hito 7.
    """

    # S163 (26/11): roles a nivel de clase, para que Permisos › Árbol
    # lea la misma lista que decide aquí quién entra.
    allowed_roles = {
        CompanyUser.ROLE_WORKSHOP,
        CompanyUser.ROLE_WORKSHOPBOSS,
        CompanyUser.ROLE_ADMIN,
        CompanyUser.ROLE_ADMIN_SUPERVISOR,
    }

    def dispatch(self, request, *args, **kwargs):
        """
        Verify that the authenticated CompanyUser holds the WORKSHOP or ADMIN
        role.
        Role is checked before running the view (S117).
        ---
        Verifica que el CompanyUser autenticado posee el rol WORKSHOP o ADMIN.
        El rol se comprueba antes de ejecutar la vista (S117).
        """
        # Role check BEFORE running the view -- see
        # _company_user_for_role_check().
        # Comprobación de rol ANTES de ejecutar la vista -- ver
        # _company_user_for_role_check().
        company_user = _company_user_for_role_check(request)
        if company_user is None:
            return super().dispatch(request, *args, **kwargs)

        # Grant access only to WORKSHOP and ADMIN roles.
        # Conceder acceso a WORKSHOP, WORKSHOPBOSS y ADMIN.
        # Grant access to WORKSHOP, WORKSHOPBOSS and ADMIN roles.
        if company_user.role not in self.allowed_roles:
            return HttpResponseForbidden(
                "Acceso denegado. Esta sección requiere el rol de Operario o "
                "Jefe de taller."
            )

        return super().dispatch(request, *args, **kwargs)


class AdminRoleRequiredMixin(CompanyUserRequiredMixin):
    """
    Mixin that requires the authenticated CompanyUser to have the ADMIN role.
    Returns HTTP 403 Forbidden if the user has the OPERATOR role.
    ---
    Mixin que requiere que el CompanyUser autenticado tenga el rol ADMIN.
    Devuelve HTTP 403 Forbidden si el usuario tiene el rol OPERATOR.
    """

    # S163 (26/11): leído también por Permisos › Árbol.
    allowed_roles = set(CompanyUser.ADMIN_ROLES)

    def dispatch(self, request, *args, **kwargs):
        """
        Verify that the authenticated CompanyUser holds the ADMIN role.
        Role is checked before running the view (S117).
        ---
        Verifica que el CompanyUser autenticado posee el rol ADMIN.
        El rol se comprueba antes de ejecutar la vista (S117).
        """
        # Role check BEFORE running the view -- see
        # _company_user_for_role_check().
        # Comprobación de rol ANTES de ejecutar la vista -- ver
        # _company_user_for_role_check().
        company_user = _company_user_for_role_check(request)
        if company_user is None:
            return super().dispatch(request, *args, **kwargs)

        # Block access if the user does not hold the ADMIN role.
        # Bloquear el acceso si el usuario no posee el rol ADMIN.
        # S141: también el supervisor de administración.
        if company_user.role not in self.allowed_roles:
            return HttpResponseForbidden(
                "Acceso denegado. Esta sección requiere el rol de "
                "Administrador."
            )

        return super().dispatch(request, *args, **kwargs)


class AssistanceRequiredMixin(CompanyUserRequiredMixin):
    """
    Mixin that grants access to CompanyUsers with the ASSISTANCE or ADMIN role.
    Introduced in Hito 16 for the ASISTENCIA budget wizard.
    Any other role receives a redirect to the dashboard with an error message.
    ---
    Mixin que concede acceso a CompanyUsers con rol ASSISTANCE o ADMIN.
    Introducido en el Hito 16 para el asistente de presupuestos de ASISTENCIA.
    Cualquier otro rol recibe una redireccion al dashboard con mensaje de
    error.
    """

    # S163 (26/11): roles a nivel de clase, para que Permisos › Árbol
    # lea la misma lista que decide aquí quién entra.
    allowed_roles = {
        CompanyUser.ROLE_ASSISTANCE,
        CompanyUser.ROLE_ASSIST_SUPERVISOR,
        CompanyUser.ROLE_ADMIN,
    }

    def dispatch(self, request, *args, **kwargs):
        """
        Verify that the authenticated CompanyUser holds the ASSISTANCE
        or ADMIN role. Role is checked before running the
        view (S117).
        ---
        Verifica que el CompanyUser autenticado posee el rol ASSISTANCE
        o ADMIN. El rol se comprueba antes de
        ejecutar la vista (S117).
        """
        company_user = _company_user_for_role_check(request)
        if company_user is None:
            return super().dispatch(request, *args, **kwargs)

        if company_user.role not in self.allowed_roles:
            messages.error(
                request,
                "Acceso denegado. Esta sección requiere el rol de "
                "Operario o Supervisor de Asistencia, o Administrador.",
            )
            return redirect("/panel/")

        return super().dispatch(request, *args, **kwargs)


class AssistanceWorkOrderAccessMixin(CompanyUserRequiredMixin):
    """
    Access to the assistance work orders: ADMIN, ASSISTANCE and
    ASSIST_SUPERVISOR.

    ---

    H37 (S132). Acceso a las órdenes de trabajo de asistencia (detalle,
    alta, unidades, aviso, albarán y PDF): ADMIN, operario de asistencia
    (como hasta ahora con AssistanceRequiredMixin) y supervisor de
    asistencia, que las gestiona desde la página Servicios. Rol
    comprobado antes de ejecutar la vista (S117).
    """

    # S163 (26/11): roles a nivel de clase, para que Permisos › Árbol
    # lea la misma lista que decide aquí quién entra.
    allowed_roles = {
        CompanyUser.ROLE_ADMIN,
        CompanyUser.ROLE_ASSISTANCE,
        CompanyUser.ROLE_ASSIST_SUPERVISOR,
    }

    def dispatch(self, request, *args, **kwargs):
        """
        Check the role, then run the view.

        ---

        Comprueba el rol y después ejecuta la vista.
        """
        company_user = _company_user_for_role_check(request)
        if company_user is None:
            return super().dispatch(request, *args, **kwargs)

        if company_user.role not in self.allowed_roles:
            messages.error(
                request,
                "Acceso denegado. Esta sección requiere el rol de "
                "Operario o Supervisor de Asistencia, o Administrador.",
            )
            return redirect("/panel/")

        return super().dispatch(request, *args, **kwargs)


class AssistanceAlbaranAccessMixin(CompanyUserRequiredMixin):
    """
    Albarán of a unit: work order roles, or the unit's own driver.

    ---

    H37 (S132). Albarán y PDF de una unidad (`pk` de
    WorkOrderAssistanceUnit): los roles de las órdenes de trabajo
    (ADMIN, ASSISTANCE, ASSIST_SUPERVISOR) y, además, el conductor de
    esa unidad sea cual sea su rol. Los conductores de asistencia son
    trabajadores de la sección (DRIVER, WORKSHOP...) y abren su albarán
    desde el aviso de WhatsApp. Rol comprobado antes de ejecutar la
    vista (S117).
    """

    # S163 (26/11): roles a nivel de clase, para que Permisos › Árbol
    # lea la misma lista que decide aquí quién entra.
    allowed_roles = {
        CompanyUser.ROLE_ADMIN,
        CompanyUser.ROLE_ASSISTANCE,
        CompanyUser.ROLE_ASSIST_SUPERVISOR,
    }

    def dispatch(self, request, *args, **kwargs):
        """
        Check the role or the unit driver, then run the view.

        ---

        Comprueba el rol o que sea el conductor de la unidad y después
        ejecuta la vista.
        """
        from budgets.models import WorkOrderAssistanceUnit

        company_user = _company_user_for_role_check(request)
        if company_user is None:
            return super().dispatch(request, *args, **kwargs)

        is_unit_driver = WorkOrderAssistanceUnit.objects.filter(
            pk=kwargs.get("pk"),
            work_order__company=company_user.company,
        ).filter(
            Q(operator=company_user) | Q(operator_2=company_user),
        ).exists()
        if (company_user.role not in self.allowed_roles
                and not is_unit_driver):
            messages.error(
                request,
                "Acceso denegado. Este albarán es de otro conductor.",
            )
            return redirect("/panel/")

        return super().dispatch(request, *args, **kwargs)


class AssistanceSupervisorAccessMixin(CompanyUserRequiredMixin):
    """
    Access for ADMIN and ASSIST_SUPERVISOR only.

    ---

    H37 (S132). Acceso solo para ADMIN y supervisor de asistencia
    (ASSIST_SUPERVISOR):
    - La página Servicios (albaranes, mapa y control). Miguel Ángel:
      "esa página la van a poder ver única y exclusivamente
      administradores y supervisores de asistencia".
    - Toda la gestión de Asistencia que antes era solo de ADMIN
      (aseguradoras, tarifas, bases, calendarios, conceptos, franja
      nocturna, peajes, exportaciones y borrado de presupuestos).
      Miguel Ángel, S132: el supervisor de asistencia tiene que poder
      entrar a todas las entradas de Asistencia.
    Rol comprobado antes de ejecutar la vista (S117).
    """

    # S163 (26/11): roles a nivel de clase, para que Permisos › Árbol
    # lea la misma lista que decide aquí quién entra.
    allowed_roles = {
        CompanyUser.ROLE_ADMIN,
        CompanyUser.ROLE_ASSIST_SUPERVISOR,
    }

    def dispatch(self, request, *args, **kwargs):
        """
        Check the role, then run the view.

        ---

        Comprueba el rol y después ejecuta la vista.
        """
        company_user = _company_user_for_role_check(request)
        if company_user is None:
            return super().dispatch(request, *args, **kwargs)

        if company_user.role not in self.allowed_roles:
            messages.error(
                request,
                "Acceso denegado. Esta sección requiere el rol de "
                "Supervisor de Asistencia o Administrador.",
            )
            return redirect("/panel/")

        return super().dispatch(request, *args, **kwargs)


class BaseCalendarAccessMixin(CompanyUserRequiredMixin):
    """
    Bases and labour calendars: assistance supervisors and both admins.

    ---

    H24 (S141). Bases y Calendarios laborales: los de
    AssistanceSupervisorAccessMixin más el supervisor de administración
    (Miguel Ángel: de Asistencia, el supervisor de administración solo
    entra a Bases y Calendarios laborales). Rol comprobado antes de
    ejecutar la vista (S117).
    """

    allowed_roles = {
        CompanyUser.ROLE_ADMIN,
        CompanyUser.ROLE_ADMIN_SUPERVISOR,
        CompanyUser.ROLE_ASSIST_SUPERVISOR,
    }

    def dispatch(self, request, *args, **kwargs):
        """
        Check the role, then run the view.

        ---

        Comprueba el rol y después ejecuta la vista.
        """
        company_user = _company_user_for_role_check(request)
        if company_user is None:
            return super().dispatch(request, *args, **kwargs)
        if company_user.role not in self.allowed_roles:
            messages.error(
                request,
                "Acceso denegado. Esta sección requiere el rol de "
                "Supervisor de Asistencia, Supervisor de Administración "
                "o Administrador.",
            )
            return redirect("/panel/")
        return super().dispatch(request, *args, **kwargs)


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
        ASSISTANCE with can_view_budget_breakdown=True. Checked
        before running the view (S117).
        ---
        Verifica que el CompanyUser autenticado posee ADMIN, o posee
        ASSISTANCE con can_view_budget_breakdown=True. Se
        comprueba antes de ejecutar la vista (S117).
        """
        company_user = _company_user_for_role_check(request)
        if company_user is None:
            return super().dispatch(request, *args, **kwargs)

        # H37 (S132): the assistance supervisor too (Paloma, S132).
        # H37 (S132): también el supervisor de asistencia.
        has_access = (
            company_user.role == CompanyUser.ROLE_ADMIN
            or company_user.role == CompanyUser.ROLE_ASSIST_SUPERVISOR
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

        return super().dispatch(request, *args, **kwargs)


class SupervisorAccessMixin(CompanyUserRequiredMixin):
    """
    Mixin that grants access to CompanyUsers with the SUPERVISOR or ADMIN role.
    Introduced in Hito 8 / Bloque G for the PDF work-order review and export
    workflow. Covers: WorkOrderUploadView, WorkOrderListView,
    WorkOrderExportView
    and WorkOrderMarkReviewedView.

    Access matrix:
      ADMIN      — full access (upload, list, review, export).
      SUPERVISOR — same as ADMIN for work-order views only; no access to IVR
                   configuration views (sections, contacts, users, call
                   flows…).
      Any other role — HTTP 403 Forbidden, redirected to dashboard with error
      message.
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
      Cualquier otro rol — HTTP 403 Forbidden, redirigido al dashboard con
      mensaje
                           de error.
    """

    # S163 (26/11): roles a nivel de clase, para que Permisos › Árbol
    # lea la misma lista que decide aquí quién entra.
    allowed_roles = {
        CompanyUser.ROLE_SUPERVISOR,
        CompanyUser.ROLE_WORKSHOPBOSS,
        CompanyUser.ROLE_ADMIN,
        CompanyUser.ROLE_ADMIN_SUPERVISOR,
    }

    def dispatch(self, request, *args, **kwargs):
        """
        Verify that the authenticated CompanyUser holds the SUPERVISOR or ADMIN
        role.
        Role is checked before running the view (S117).
        On insufficient role, redirects to the dashboard with an error message
        instead of returning a bare 403, to provide a better UX within the
        panel.
        ---
        Verifica que el CompanyUser autenticado posee el rol SUPERVISOR o
        ADMIN.
        El rol se comprueba antes de ejecutar la vista (S117).
        En caso de rol insuficiente, redirige al dashboard con un mensaje de
        error
        en lugar de devolver un 403 desnudo, para mejorar la experiencia en el
        panel.
        """
        # Role check BEFORE running the view -- see
        # _company_user_for_role_check().
        # Comprobación de rol ANTES de ejecutar la vista -- ver
        # _company_user_for_role_check().
        company_user = _company_user_for_role_check(request)
        if company_user is None:
            return super().dispatch(request, *args, **kwargs)

        # Grant access only to SUPERVISOR and ADMIN roles.
        # Conceder acceso a SUPERVISOR, WORKSHOPBOSS y ADMIN.
        # Grant access to SUPERVISOR, WORKSHOPBOSS and ADMIN roles.
        if company_user.role not in self.allowed_roles:
            messages.error(
                request,
                "Acceso denegado. Esta sección requiere el rol de Supervisor, "
                "Jefe de taller o Administrador.",
            )
            return redirect("/panel/")

        return super().dispatch(request, *args, **kwargs)


class FleetAccessMixin(CompanyUserRequiredMixin):
    """
    Read access to the cost-centre list ("Centros de gasto",
    /panel/fleet/): ADMIN, SUPERVISOR, WORKSHOPBOSS and -- since S117,
    explicit request of Miguel Ángel -- DOCS_SUPERVISOR (Yolanda
    Bandera), who keeps the active/inactive status of the fleet up to
    date as part of the machinery documentation work (H30).
    ---
    Acceso de lectura al listado de centros de gasto (/panel/fleet/):
    ADMIN, SUPERVISOR, WORKSHOPBOSS y -- desde S117, petición explícita
    de Miguel Ángel -- DOCS_SUPERVISOR (Yolanda Bandera), que mantiene
    al día el estado activo/inactivo de la flota como parte del
    trabajo documental de maquinaria (H30).
    """

    allowed_roles = {
        CompanyUser.ROLE_ADMIN,
        CompanyUser.ROLE_ADMIN_SUPERVISOR,
        CompanyUser.ROLE_SUPERVISOR,
        CompanyUser.ROLE_WORKSHOPBOSS,
        CompanyUser.ROLE_DOCS_SUPERVISOR,
    }

    def dispatch(self, request, *args, **kwargs):
        """
        Checks the role before running the view.
        ---
        Comprueba el rol antes de ejecutar la vista.
        """
        company_user = _company_user_for_role_check(request)
        if (
            company_user is not None
            and company_user.role not in self.allowed_roles
        ):
            messages.error(
                request,
                "Acceso denegado. Esta sección requiere el rol de "
                "Supervisor, Jefe de taller, Supervisor de "
                "Documentación o Administrador.",
            )
            return redirect("/panel/")
        return super().dispatch(request, *args, **kwargs)


class FleetManageAccessMixin(FleetAccessMixin):
    """
    Write access to cost centres (create, edit, deactivate/reactivate,
    individually or in bulk): ADMIN and DOCS_SUPERVISOR (S117).
    Permanent deletion stays ADMIN-only (AdminRoleRequiredMixin).
    ---
    Acceso de escritura a centros de gasto (alta, edición, baja/
    reactivación, individual o masiva): ADMIN y DOCS_SUPERVISOR (S117).
    El borrado definitivo sigue siendo solo de ADMIN
    (AdminRoleRequiredMixin).
    """

    allowed_roles = {
        CompanyUser.ROLE_ADMIN,
        CompanyUser.ROLE_ADMIN_SUPERVISOR,
        CompanyUser.ROLE_DOCS_SUPERVISOR,
    }

    def dispatch(self, request, *args, **kwargs):
        """
        Checks the role before running the view; returns 403 (these
        endpoints are always called via fetch/htmx, never navigated).
        ---
        Comprueba el rol antes de ejecutar la vista; devuelve 403
        (estos endpoints se llaman siempre por fetch/htmx, nunca se
        navega a ellos).
        """
        company_user = _company_user_for_role_check(request)
        if (
            company_user is not None
            and company_user.role not in self.allowed_roles
        ):
            return HttpResponseForbidden(
                "Acceso denegado. Esta acción requiere el rol de "
                "Supervisor de Documentación o Administrador."
            )
        return CompanyUserRequiredMixin.dispatch(
            self, request, *args, **kwargs,
        )


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

    # S163 (26/11): roles a nivel de clase, para que Permisos › Árbol
    # lea la misma lista que decide aquí quién entra.
    allowed_roles = {
        CompanyUser.ROLE_DOCS_SUPERVISOR,
        CompanyUser.ROLE_ADMIN,
        CompanyUser.ROLE_ADMIN_SUPERVISOR,
    }

    def dispatch(self, request, *args, **kwargs):
        """
        Verify that the authenticated CompanyUser holds the
        DOCS_SUPERVISOR or ADMIN role.
        ---
        Verifica que el CompanyUser autenticado posee el rol
        DOCS_SUPERVISOR o ADMIN.
        """
        company_user = _company_user_for_role_check(request)
        if company_user is None:
            return super().dispatch(request, *args, **kwargs)

        if company_user.role not in self.allowed_roles:
            messages.error(
                request,
                "Acceso denegado. Esta sección requiere el rol de "
                "Supervisor de Documentación o Administrador.",
            )
            return redirect("/panel/")

        return super().dispatch(request, *args, **kwargs)


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

    # S163 (26/11): roles a nivel de clase, para que Permisos › Árbol
    # lea la misma lista que decide aquí quién entra.
    allowed_roles = {
        CompanyUser.ROLE_WORKSHOP,
        CompanyUser.ROLE_WORKSHOPBOSS,
        CompanyUser.ROLE_SUPERVISOR,
        CompanyUser.ROLE_ADMIN,
        CompanyUser.ROLE_ADMIN_SUPERVISOR,
    }

    def dispatch(self, request, *args, **kwargs):
        """
        Verify that the authenticated CompanyUser holds one of the allowed
        roles for work-order form access. Checked before
        running the view (S117).
        ---
        Verifica que el CompanyUser autenticado posee uno de los roles
        permitidos para el formulario de partes. Se comprueba
        antes de ejecutar la vista (S117).
        """
        company_user = _company_user_for_role_check(request)
        if company_user is None:
            return super().dispatch(request, *args, **kwargs)

        if company_user.role not in self.allowed_roles:
            messages.error(
                request,
                "Acceso denegado. Esta sección requiere el rol de "
                "Operario, Jefe de taller, Supervisor o Administrador.",
            )
            return redirect("/panel/")

        return super().dispatch(request, *args, **kwargs)


class SuperuserRequiredMixin(CompanyUserRequiredMixin):
    """
    Mixin that restricts access to Django superusers
    (request.user.is_superuser).
    Unlike every other mixin in this module, this does NOT check
    CompanyUser.role
    -- it checks the underlying Django auth.User flag directly. Introduced in
    S021 as the replacement for the hardcoded-username antipattern
    (request.user.username == 'alvarez_admin') previously used in
    panel/templates/panel/_nav_items.html to gate the Django Admin link.
    Granting this level of access to another account in the future is a BD
    change (User.is_superuser = True), never a code change.
    ---
    Mixin que restringe el acceso a superusuarios de Django
    (request.user.is_superuser). A diferencia de cualquier otro mixin de este
    módulo, este NO comprueba CompanyUser.role -- comprueba directamente el
    flag de auth.User de Django. Introducido en S021 como sustituto del
    antipatrón de username hardcodeado (request.user.username ==
    'alvarez_admin') usado antes en panel/templates/panel/_nav_items.html
    para gatear el enlace al Django Admin. Dar este nivel de acceso a otra
    cuenta en el futuro es un cambio de BD (User.is_superuser = True), nunca
    un cambio de código.
    """

    def dispatch(self, request, *args, **kwargs):
        """
        Verify that the authenticated user is a Django superuser.
        Role is checked before running the view (S117).
        ---
        Verifica que el usuario autenticado es superusuario de Django.
        Se comprueba antes de ejecutar la vista (S117).
        """
        if _company_user_for_role_check(request) is None:
            return super().dispatch(request, *args, **kwargs)

        if not request.user.is_superuser:
            messages.error(
                request,
                "Acceso denegado. Esta sección está reservada.",
            )
            return redirect("/panel/")

        return super().dispatch(request, *args, **kwargs)
