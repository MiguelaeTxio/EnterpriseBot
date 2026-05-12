# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views.py
"""
View definitions for the panel application.
Implements class-based views for authentication, the main dashboard and all
work-order processing workflow views.

Hito 8 / Bloque G additions:
  WorkOrderMarkReviewedView — HTMX toggle for the reviewed flag (SUPERVISOR+ADMIN).
  WorkOrderListView         — refactored with four querysets for tabbed UI (H1).
  WorkOrderUploadView       — mixin changed to SupervisorAccessMixin.
  WorkOrderExportView       — mixin changed to SupervisorAccessMixin; export_mode
                              parameter support for single_sheet / multi_sheet (H4).
---
Definiciones de vistas para la aplicación panel.
Implementa vistas basadas en clases para autenticación, el panel principal y
todas las vistas del flujo de procesamiento de partes de trabajo.

Incorporaciones Hito 8 / Bloque G:
  WorkOrderMarkReviewedView — toggle HTMX para el flag reviewed (SUPERVISOR+ADMIN).
  WorkOrderListView         — refactorizada con cuatro querysets para UI de pestañas (H1).
  WorkOrderUploadView       — mixin cambiado a SupervisorAccessMixin.
  WorkOrderExportView       — mixin cambiado a SupervisorAccessMixin; soporte del
                              parámetro export_mode para single_sheet / multi_sheet (H4).
"""

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib import messages as django_messages
from django.views.generic import TemplateView, View, ListView, UpdateView, CreateView, DeleteView
from django.shortcuts import redirect, render
from django.db import models as django_models
from django.db.models import Q, Prefetch
from django.utils.timezone import now
from django.forms import modelformset_factory

from panel.mixins import CompanyUserRequiredMixin, AdminRoleRequiredMixin, WorkshopRequiredMixin, SupervisorAccessMixin
from panel.models import AnalyticsProfile
from panel.forms import (
    PanelAuthenticationForm,
    PresenceStatusForm,
    SectionForm,
    SectionScheduleForm,
    ContactForm,
    CallFlowForm,
    CorporateVoiceProfileForm,
    BlockedCallerForm,
    CompanyUserCreateForm,
    PanelPasswordChangeForm,
    PanelSetPasswordForm,
    DataCaptureSetForm,
)
from ivr_config.models import (
    Section,
    SectionSchedule,
    Contact,
    PresenceStatus,
    CompanyUser,
    CallFlow,
    PhoneNumber,
    CorporateVoiceProfile,
    BlockedCaller,
    DataCaptureSet,
)
from whatsapp.models import WhatsAppTemplate, WhatsAppSession
from work_order_processor.models import WorkOrder, WorkOrderEntry, WorkOrderEntryLine
from work_order_processor.tasks import process_work_order_pdf
from fleet.models import MachineAsset
import logging
import plotly.graph_objects as go
import plotly.io as pio

logger = logging.getLogger(__name__)


class OperatorDashboardView(WorkshopRequiredMixin, TemplateView):
    """
    Landing view for CompanyUsers with the WORKSHOP role.
    Displays a selector with the three work-order entry paths:
    Form (structured web form), STT (speech-to-text dictation) and
    Upload (photo or PDF with Gemini Vision extraction).
    Accessible to WORKSHOP and ADMIN roles (WorkshopRequiredMixin).
    ---
    Vista de aterrizaje para CompanyUsers con rol WORKSHOP.
    Muestra un selector con las tres vías de entrada de partes:
    Form (formulario web estructurado), STT (dictado por voz) y
    Upload (foto o PDF con extracción Gemini Vision).
    Accesible para los roles WORKSHOP y ADMIN (WorkshopRequiredMixin).
    """

    template_name = "panel/operator/dashboard.html"

    def get_context_data(self, **kwargs):
        """
        Build context with company, company_user and own_presence for the operator dashboard.
        ---
        Construye el contexto con company, company_user y own_presence para el dashboard
        del operario de taller.
        """
        context = super().get_context_data(**kwargs)

        # CompanyUserRequiredMixin guarantees company_user exists at this point.
        # CompanyUserRequiredMixin garantiza que company_user existe en este punto.
        company_user = self.request.user.company_user
        company      = company_user.company

        # Retrieve current active presence status for the authenticated user.
        # Obtener el estado de presencia activo actual del usuario autenticado.
        own_presence = PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

        context["company"]      = company
        context["company_user"] = company_user
        context["own_presence"] = own_presence
        context["active_nav"]   = "operator_dashboard"

        return context


class WorkerSignupView(View):
    """
    Public self-registration view for workshop operators.
    Resolves the target company server-side (Grupo Álvarez pilot).
    Creates an auth.User and a CompanyUser with role=WORKSHOP on valid POST.
    No authentication required — this view is intentionally public.
    Architecture is prepared for multi-company extension: the company
    resolution logic is isolated in _resolve_company() for easy replacement.
    ---
    Vista de auto-registro público para operarios de taller.
    Resuelve la empresa destino en el servidor (piloto Grupo Álvarez).
    Crea un auth.User y un CompanyUser con rol=WORKSHOP en un POST válido.
    No requiere autenticación — esta vista es intencionalmente pública.
    La arquitectura está preparada para extensión multiempresa: la lógica de
    resolución de empresa está aislada en _resolve_company() para fácil sustitución.
    """

    template_name = "panel/workers/signup.html"

    def _resolve_company(self):
        """
        Resolves the target Company for new worker registrations.
        Current implementation: returns the Grupo Álvarez company (pilot).
        Returns None if the company does not exist, which causes the view
        to render an informative error page.
        ---
        Resuelve la Company destino para los nuevos registros de operarios.
        Implementación actual: devuelve la empresa Grupo Álvarez (piloto).
        Devuelve None si la empresa no existe, lo que hace que la vista
        renderice una página de error informativa.
        """
        from ivr_config.models import Company
        try:
            return Company.objects.get(name__icontains="Álvarez")
        except (Company.DoesNotExist, Company.MultipleObjectsReturned):
            return None

    def get(self, request, *args, **kwargs):
        """
        Renders the signup form. Redirects to operator dashboard if already
        authenticated to avoid re-registration.
        ---
        Renderiza el formulario de registro. Redirige al panel del operario
        si ya está autenticado para evitar re-registros.
        """
        from panel.forms import WorkerSignupForm
        if request.user.is_authenticated:
            return redirect("/panel/operator/")
        company = self._resolve_company()
        form    = WorkerSignupForm(company=company)
        return render(request, self.template_name, {
            "form":    form,
            "company": company,
        })

    def post(self, request, *args, **kwargs):
        """
        Validates the signup form. On success creates auth.User + CompanyUser
        with role=WORKSHOP, logs the user in and redirects to operator dashboard.
        On failure re-renders the form with validation errors.
        ---
        Valida el formulario de registro. En caso de éxito crea auth.User +
        CompanyUser con rol=WORKSHOP, autentica al usuario y redirige al panel
        del operario. En caso de fallo re-renderiza el formulario con errores.
        """
        from django.contrib.auth import login as auth_login
        from django.contrib.auth.models import User as AuthUser
        from panel.forms import WorkerSignupForm
        company = self._resolve_company()
        if company is None:
            django_messages.error(
                request,
                "No es posible completar el registro en este momento. "
                "Contacta con tu administrador.",
            )
            return render(request, self.template_name, {
                "form":    WorkerSignupForm(),
                "company": None,
            })
        form = WorkerSignupForm(request.POST, company=company)
        if not form.is_valid():
            return render(request, self.template_name, {
                "form":    form,
                "company": company,
            })
        # Create auth.User with the operator-chosen password.
        # Crear auth.User con la contraseña elegida por el operario.
        auth_user = AuthUser.objects.create_user(
            username   = form.cleaned_data["username"],
            first_name = form.cleaned_data["first_name"],
            last_name  = form.cleaned_data["last_name"],
            password   = form.cleaned_data["password"],
            is_staff     = False,
            is_superuser = False,
        )
        # Create CompanyUser linked to the resolved company with WORKSHOP role.
        # Crear CompanyUser vinculado a la empresa resuelta con rol WORKSHOP.
        CompanyUser.objects.create(
            user                 = auth_user,
            company              = company,
            role                 = CompanyUser.ROLE_WORKSHOP,
            is_active            = True,
            must_change_password = False,
            phone                = form.cleaned_data.get("phone", ""),
            dni                  = form.cleaned_data.get("dni", ""),
        )
        # Log the new user in immediately after registration.
        # Autenticar al nuevo usuario inmediatamente tras el registro.
        auth_login(request, auth_user)
        django_messages.success(
            request,
            f"¡Bienvenido, {auth_user.first_name}! Tu cuenta ha sido creada correctamente.",
        )
        return redirect("/panel/operator/")


class CompanyUserCreateView(AdminRoleRequiredMixin, View):
    """
    Allows an ADMIN to create a new CompanyUser for their company.
    Creates the underlying auth.User with the provided initial password and sets
    must_change_password=True so the new user must change it on first login.
    ---
    Permite a un ADMIN crear un nuevo CompanyUser para su empresa.
    Crea el auth.User subyacente con la contraseña inicial y establece
    must_change_password=True para forzar el cambio en el primer acceso.
    """

    template_name = "panel/users/create.html"

    def _get_own_presence(self, company_user):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

    def _get_context(self, request, form=None):
        """
        Builds base template context with company, company_user and own_presence.
        ---
        Construye el contexto base con company, company_user y own_presence.
        """
        cu = request.user.company_user
        return {
            "company":      cu.company,
            "company_user": cu,
            "own_presence": self._get_own_presence(cu),
            "active_nav":   "users",
            "form":         form or CompanyUserCreateForm(),
        }

    def get(self, request, *args, **kwargs):
        """
        Renders the user creation form.
        ---
        Renderiza el formulario de creación de usuario.
        """
        return render(request, self.template_name, self._get_context(request))

    def post(self, request, *args, **kwargs):
        """
        Validates the form, creates auth.User and CompanyUser, redirects on success.
        ---
        Valida el formulario, crea auth.User y CompanyUser, redirige en caso de éxito.
        """
        from django.contrib.auth.models import User as AuthUser
        form = CompanyUserCreateForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, self._get_context(request, form))
        company = request.user.company_user.company
        auth_user = AuthUser.objects.create_user(
            username     = form.cleaned_data["username"],
            first_name   = form.cleaned_data.get("first_name", ""),
            last_name    = form.cleaned_data.get("last_name", ""),
            password     = form.get_initial_password(),
            is_staff     = False,
            is_superuser = False,
        )
        CompanyUser.objects.create(
            user                 = auth_user,
            company              = company,
            role                 = form.cleaned_data["role"],
            is_active            = True,
            must_change_password = True,
        )
        django_messages.success(
            request,
            f"Usuario '{auth_user.username}' creado. "
            f"Deberá cambiar su contraseña en el primer acceso."
        )
        return redirect("/panel/users/")


class CompanyUserListView(AdminRoleRequiredMixin, ListView):
    """
    Lists all CompanyUser accounts belonging to the authenticated user's company.
    Accessible only to users with the ADMIN role.
    ---
    Lista todas las cuentas CompanyUser pertenecientes a la empresa del usuario autenticado.
    Solo accesible para usuarios con rol ADMIN.
    """

    model = CompanyUser
    template_name = "panel/users/list.html"
    context_object_name = "company_users"

    def get_queryset(self):
        """
        Returns CompanyUser records scoped to the authenticated user's company.
        ---
        Retorna los registros CompanyUser acotados a la empresa del usuario autenticado.
        """
        return CompanyUser.objects.filter(
            company=self.request.user.company_user.company
        ).select_related("user").order_by("user__username")

    def get_context_data(self, **kwargs):
        """
        Adds company and company_user to template context.
        ---
        Añade company y company_user al contexto de la plantilla.
        """
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "users"
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django.utils.timezone import now
        from django.db.models import Q
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class CompanyUserUpdateView(AdminRoleRequiredMixin, UpdateView):
    """
    Allows an ADMIN to update the role and active status of a CompanyUser
    belonging to the same company. Prevents editing users from other companies.
    ---
    Permite a un ADMIN actualizar el rol y el estado activo de un CompanyUser
    de la misma empresa. Impide editar usuarios de otras empresas.
    """

    model = CompanyUser
    template_name = "panel/users/form.html"
    fields = ["role", "is_active"]

    def get_queryset(self):
        """
        Restricts the queryset to CompanyUser records of the authenticated user's company.
        ---
        Restringe el queryset a los registros CompanyUser de la empresa del usuario autenticado.
        """
        return CompanyUser.objects.filter(
            company=self.request.user.company_user.company
        )

    def post(self, request, *args, **kwargs):
        """
        Handles standard update and the force-reset action.
        If POST contains 'force_reset', sets must_change_password=True and redirects.
        ---
        Gestiona la actualización estándar y la acción de forzar reset.
        Si el POST contiene 'force_reset', establece must_change_password=True y redirige.
        """
        self.object = self.get_object()
        if "force_reset" in request.POST:
            self.object.must_change_password = True
            self.object.save(update_fields=["must_change_password"])
            django_messages.success(
                request,
                f"Se ha forzado el cambio de contraseña para "
                f"'{self.object.user.username}'."
            )
            return redirect("/panel/users/")
        return super().post(request, *args, **kwargs)

    def get_success_url(self):
        """
        Redirects to the user list after a successful update.
        ---
        Redirige a la lista de usuarios tras una actualización correcta.
        """
        django_messages.success(
            self.request,
            f"Usuario '{self.object.user.username}' actualizado correctamente."
        )
        return "/panel/users/"

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user and own_presence to template context.
        ---
        Añade company, company_user y own_presence al contexto de la plantilla.
        """
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "users"
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django.utils.timezone import now
        from django.db.models import Q
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class SectionListView(AdminRoleRequiredMixin, ListView):
    """
    Lists all Section records belonging to the authenticated user's company.
    Accessible only to users with the ADMIN role.
    ---
    Lista todos los registros Section pertenecientes a la empresa del usuario autenticado.
    Solo accesible para usuarios con rol ADMIN.
    """

    model = Section
    template_name = "panel/sections/list.html"
    context_object_name = "sections"

    def get_queryset(self):
        """
        Returns Section records scoped to the authenticated user's company.
        ---
        Retorna los registros Section acotados a la empresa del usuario autenticado.
        """
        return Section.objects.filter(
            company=self.request.user.company_user.company
        ).prefetch_related("contacts").order_by("name")

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user and own_presence to template context.
        ---
        Añade company, company_user y own_presence al contexto de la plantilla.
        """
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "sections"
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django.utils.timezone import now
        from django.db.models import Q
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class SectionCreateView(AdminRoleRequiredMixin, CreateView):
    """
    Allows an ADMIN to create a new Section for their company.
    Automatically assigns the company from the authenticated user's CompanyUser.
    Manages an inline SectionSchedule formset for time slot configuration.
    Updated 2026-04-16 (Step 37.C — Estrategia B): call_flow queryset restricted
    to the company's own active CallFlows.
    ---
    Permite a un ADMIN crear una nueva Section para su empresa.
    Asigna automáticamente la empresa desde el CompanyUser del usuario autenticado.
    Gestiona un formset inline de SectionSchedule para la configuración de horarios.
    Actualización 2026-04-16 (Paso 37.C — Estrategia B): queryset de call_flow
    restringido a los CallFlows activos de la empresa.
    """

    model = Section
    form_class = SectionForm
    template_name = "panel/sections/form.html"

    def _get_schedule_formset_class(self):
        """
        Returns the SectionSchedule inline formset class with 5 empty extra forms.
        ---
        Retorna la clase de formset inline de SectionSchedule con 5 formularios extra vacíos.
        """
        return modelformset_factory(
            SectionSchedule,
            form=SectionScheduleForm,
            extra=5,
            can_delete=True,
        )

    def get_form(self, form_class=None):
        """
        Restricts the contacts queryset to the authenticated user's company.
        Restricts the call_flow queryset to the company's own active CallFlows
        (Estrategia B — Step 37.C). call_flow is optional.
        Restricts the data_capture_set queryset to the company's own DataCaptureSets.
        data_capture_set is optional — can also be created inline from the section form.
        ---
        Restringe el queryset de contactos a la empresa del usuario autenticado.
        Restringe el queryset de call_flow a los CallFlows activos de la empresa
        (Estrategia B — Paso 37.C). call_flow es opcional.
        Restringe el queryset de data_capture_set a los DataCaptureSets de la empresa.
        data_capture_set es opcional — también puede crearse inline desde el formulario de sección.
        """
        form = super().get_form(form_class)
        company = self.request.user.company_user.company
        form.fields["contacts"].queryset = Contact.objects.filter(
            company=company
        )
        form.fields["call_flow"].queryset = CallFlow.objects.filter(
            company=company,
            is_active=True,
        ).order_by("name")
        form.fields["call_flow"].required = False
        form.fields["data_capture_set"].queryset = DataCaptureSet.objects.filter(
            company=company,
        ).order_by("name")
        form.fields["data_capture_set"].required = False
        return form

    def get(self, request, *args, **kwargs):
        """
        Renders the section form with an empty schedule formset.
        ---
        Renderiza el formulario de sección con un formset de horarios vacío.
        """
        self.object = None
        form = self.get_form()
        ScheduleFormSet = self._get_schedule_formset_class()
        schedule_formset = ScheduleFormSet(
            queryset=SectionSchedule.objects.none(),
            prefix="schedules",
        )
        return self.render_to_response(
            self.get_context_data(form=form, schedule_formset=schedule_formset)
        )

    def post(self, request, *args, **kwargs):
        """
        Validates and saves both the section form and the schedule formset.
        ---
        Valida y guarda tanto el formulario de sección como el formset de horarios.
        """
        self.object = None
        form = self.get_form()
        ScheduleFormSet = self._get_schedule_formset_class()
        schedule_formset = ScheduleFormSet(
            request.POST,
            queryset=SectionSchedule.objects.none(),
            prefix="schedules",
        )
        if form.is_valid() and schedule_formset.is_valid():
            return self._form_valid(form, schedule_formset)
        return self.render_to_response(
            self.get_context_data(form=form, schedule_formset=schedule_formset)
        )

    def _form_valid(self, form, schedule_formset):
        """
        Saves the Section and all valid SectionSchedule entries.
        If 'capture_fields_json' is present in POST and non-empty, creates a new
        DataCaptureSet with the submitted fields and links it to the section,
        overriding any selector choice. If the selector has a value but no inline
        fields were submitted, the selected DataCaptureSet is linked as-is.
        ---
        Guarda la Section y todas las entradas SectionSchedule válidas.
        Si 'capture_fields_json' está presente en el POST y no está vacío, crea un
        nuevo DataCaptureSet con los campos enviados y lo vincula a la sección,
        sobreescribiendo cualquier selección del selector. Si el selector tiene valor
        pero no se enviaron campos inline, el DataCaptureSet seleccionado se vincula tal cual.
        """
        import json
        from django.contrib import messages as django_messages
        company = self.request.user.company_user.company
        form.instance.company = company

        # --- Gestión inline de DataCaptureSet ---
        # --- Inline DataCaptureSet management ---
        raw_json = self.request.POST.get("capture_fields_json", "").strip()
        capture_name = self.request.POST.get("capture_set_name", "").strip()
        if raw_json and raw_json != "[]":
            # Campos inline enviados: crear nuevo DataCaptureSet y vincularlo.
            # Inline fields submitted: create new DataCaptureSet and link it.
            try:
                parsed_fields = json.loads(raw_json)
            except (ValueError, TypeError):
                parsed_fields = []
            dcs_name = capture_name or f"Captura — {form.cleaned_data.get('name', 'Sección')}"
            new_dcs = DataCaptureSet.objects.create(
                company=company,
                name=dcs_name,
                fields=parsed_fields,
            )
            form.instance.data_capture_set = new_dcs

        self.object = form.save()
        schedules = schedule_formset.save(commit=False)
        for schedule in schedules:
            schedule.section = self.object
            schedule.save()
        for deleted in schedule_formset.deleted_objects:
            deleted.delete()
        django_messages.success(
            self.request,
            f"Sección '{self.object.name}' creada correctamente."
        )
        return redirect("/panel/sections/")

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user, own_presence, action flag and schedule_formset.
        ---
        Añade company, company_user, own_presence, flag de acción y schedule_formset.
        """
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "sections"
        context["action"] = "Crear"
        if "schedule_formset" not in context:
            ScheduleFormSet = self._get_schedule_formset_class()
            context["schedule_formset"] = ScheduleFormSet(
                queryset=SectionSchedule.objects.none(),
                prefix="schedules",
            )
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django.utils.timezone import now
        from django.db.models import Q
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class SectionUpdateView(AdminRoleRequiredMixin, UpdateView):
    """
    Allows an ADMIN to update an existing Section belonging to their company.
    Prevents editing sections from other companies.
    Manages an inline SectionSchedule formset pre-populated with existing time slots.
    ---
    Permite a un ADMIN actualizar una Section existente de su empresa.
    Impide editar secciones de otras empresas.
    Gestiona un formset inline de SectionSchedule prerellenado con las franjas existentes.
    """

    model = Section
    form_class = SectionForm
    template_name = "panel/sections/form.html"

    def _get_schedule_formset_class(self):
        """
        Returns the SectionSchedule inline formset class with 3 extra empty forms.
        ---
        Retorna la clase de formset inline de SectionSchedule con 3 formularios extra vacíos.
        """
        return modelformset_factory(
            SectionSchedule,
            form=SectionScheduleForm,
            extra=3,
            can_delete=True,
        )

    def get_queryset(self):
        """
        Restricts the queryset to Section records of the authenticated user's company.
        ---
        Restringe el queryset a los registros Section de la empresa del usuario autenticado.
        """
        return Section.objects.filter(
            company=self.request.user.company_user.company
        )

    def get_form(self, form_class=None):
        """
        Restricts the contacts queryset to the authenticated user's company.
        Restricts the call_flow queryset to the company's own active CallFlows
        (Estrategia B — Step 37.C). call_flow is optional.
        Restricts the data_capture_set queryset to the company's own DataCaptureSets.
        data_capture_set is optional — can also be created inline from the section form.
        ---
        Restringe el queryset de contactos a la empresa del usuario autenticado.
        Restringe el queryset de call_flow a los CallFlows activos de la empresa
        (Estrategia B — Paso 37.C). call_flow es opcional.
        Restringe el queryset de data_capture_set a los DataCaptureSets de la empresa.
        data_capture_set es opcional — también puede crearse inline desde el formulario de sección.
        """
        form = super().get_form(form_class)
        company = self.request.user.company_user.company
        form.fields["contacts"].queryset = Contact.objects.filter(
            company=company
        )
        form.fields["call_flow"].queryset = CallFlow.objects.filter(
            company=company,
            is_active=True,
        ).order_by("name")
        form.fields["call_flow"].required = False
        form.fields["data_capture_set"].queryset = DataCaptureSet.objects.filter(
            company=company,
        ).order_by("name")
        form.fields["data_capture_set"].required = False
        return form

    def get(self, request, *args, **kwargs):
        """
        Renders the section form pre-populated with existing schedules.
        ---
        Renderiza el formulario de sección prerellenado con los horarios existentes.
        """
        self.object = self.get_object()
        form = self.get_form()
        ScheduleFormSet = self._get_schedule_formset_class()
        schedule_formset = ScheduleFormSet(
            queryset=SectionSchedule.objects.filter(section=self.object).order_by("weekday", "time_open"),
            prefix="schedules",
        )
        return self.render_to_response(
            self.get_context_data(form=form, schedule_formset=schedule_formset)
        )

    def post(self, request, *args, **kwargs):
        """
        Validates and saves both the section form and the schedule formset.
        ---
        Valida y guarda tanto el formulario de sección como el formset de horarios.
        """
        self.object = self.get_object()
        form = self.get_form()
        ScheduleFormSet = self._get_schedule_formset_class()
        schedule_formset = ScheduleFormSet(
            request.POST,
            queryset=SectionSchedule.objects.filter(section=self.object).order_by("weekday", "time_open"),
            prefix="schedules",
        )
        if form.is_valid() and schedule_formset.is_valid():
            return self._form_valid(form, schedule_formset)
        return self.render_to_response(
            self.get_context_data(form=form, schedule_formset=schedule_formset)
        )

    def _form_valid(self, form, schedule_formset):
        """
        Saves the Section and all valid SectionSchedule entries.
        Handles deletion of removed schedule entries.
        If 'capture_fields_json' is present in POST and non-empty, updates the
        existing linked DataCaptureSet fields in-place, or creates a new one if
        none is linked. If the selector has a value but no inline fields were
        submitted, the selected DataCaptureSet is linked as-is.
        ---
        Guarda la Section y todas las entradas SectionSchedule válidas.
        Gestiona la eliminación de las franjas horarias eliminadas.
        Si 'capture_fields_json' está presente en el POST y no está vacío, actualiza
        los campos del DataCaptureSet vinculado existente en su lugar, o crea uno nuevo
        si no hay ninguno vinculado. Si el selector tiene valor pero no se enviaron
        campos inline, el DataCaptureSet seleccionado se vincula tal cual.
        """
        import json
        from django.contrib import messages as django_messages
        company = self.request.user.company_user.company

        # --- Gestión inline de DataCaptureSet ---
        # --- Inline DataCaptureSet management ---
        raw_json = self.request.POST.get("capture_fields_json", "").strip()
        capture_name = self.request.POST.get("capture_set_name", "").strip()
        if raw_json and raw_json != "[]":
            # Campos inline enviados: actualizar el vinculado existente o crear uno nuevo.
            # Inline fields submitted: update the existing linked one or create a new one.
            try:
                parsed_fields = json.loads(raw_json)
            except (ValueError, TypeError):
                parsed_fields = []
            existing_dcs = self.object.data_capture_set if self.object.data_capture_set_id else None
            if existing_dcs is not None:
                # Actualizar en su lugar preservando el vínculo y el nombre si no se cambió.
                # Update in-place preserving the link and name if not changed.
                if capture_name:
                    existing_dcs.name = capture_name
                existing_dcs.fields = parsed_fields
                existing_dcs.save(update_fields=["name", "fields", "updated_at"])
            else:
                # No hay DataCaptureSet vinculado: crear uno nuevo.
                # No linked DataCaptureSet: create a new one.
                dcs_name = capture_name or f"Captura — {form.cleaned_data.get('name', 'Sección')}"
                new_dcs = DataCaptureSet.objects.create(
                    company=company,
                    name=dcs_name,
                    fields=parsed_fields,
                )
                form.instance.data_capture_set = new_dcs

        self.object = form.save()
        schedules = schedule_formset.save(commit=False)
        for schedule in schedules:
            schedule.section = self.object
            schedule.save()
        for deleted in schedule_formset.deleted_objects:
            deleted.delete()
        django_messages.success(
            self.request,
            f"Sección '{self.object.name}' actualizada correctamente."
        )
        return redirect("/panel/sections/")

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user, own_presence, action flag and schedule_formset.
        ---
        Añade company, company_user, own_presence, flag de acción y schedule_formset.
        """
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "sections"
        context["action"] = "Guardar"
        if "schedule_formset" not in context:
            ScheduleFormSet = self._get_schedule_formset_class()
            context["schedule_formset"] = ScheduleFormSet(
                queryset=SectionSchedule.objects.filter(section=self.object).order_by("weekday", "time_open"),
                prefix="schedules",
            )
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django.utils.timezone import now
        from django.db.models import Q
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class ContactListView(AdminRoleRequiredMixin, ListView):
    """
    Lists all Contact records belonging to the authenticated user's company.
    Accessible only to users with the ADMIN role.
    ---
    Lista todos los registros Contact pertenecientes a la empresa del usuario autenticado.
    Solo accesible para usuarios con rol ADMIN.
    """

    model = Contact
    template_name = "panel/contacts/list.html"
    context_object_name = "contacts"

    def get_queryset(self):
        """
        Returns Contact records scoped to the authenticated user's company.
        ---
        Retorna los registros Contact acotados a la empresa del usuario autenticado.
        """
        return Contact.objects.filter(
            company=self.request.user.company_user.company
        ).select_related("company_user__user").order_by("name")

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user and own_presence to template context.
        ---
        Añade company, company_user y own_presence al contexto de la plantilla.
        """
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "contacts"
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django.utils.timezone import now
        from django.db.models import Q
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class ContactCreateView(AdminRoleRequiredMixin, CreateView):
    """
    Allows an ADMIN to create a new Contact for their company.
    Automatically assigns the company from the authenticated user's CompanyUser.
    Restricts the company_user field to users belonging to the same company.
    ---
    Permite a un ADMIN crear un nuevo Contact para su empresa.
    Asigna automáticamente la empresa desde el CompanyUser del usuario autenticado.
    Restringe el campo company_user a usuarios de la misma empresa.
    """

    model = Contact
    form_class = ContactForm
    template_name = "panel/contacts/form.html"

    def get_form(self, form_class=None):
        """
        Restricts the company_user queryset in the form to the authenticated user's company.
        ---
        Restringe el queryset de company_user del formulario a la empresa del usuario autenticado.
        """
        form = super().get_form(form_class)
        form.fields["company_user"].queryset = CompanyUser.objects.filter(
            company=self.request.user.company_user.company
        ).select_related("user")
        form.fields["company_user"].required = False
        return form

    def form_valid(self, form):
        """
        Assigns the company before saving the new Contact.
        ---
        Asigna la empresa antes de guardar el nuevo Contact.
        """
        form.instance.company = self.request.user.company_user.company
        return super().form_valid(form)

    def get_success_url(self):
        """
        Redirects to the contact list after a successful creation.
        ---
        Redirige a la lista de contactos tras una creación correcta.
        """
        from django.contrib import messages as django_messages
        django_messages.success(
            self.request,
            f"Contacto '{self.object.name}' creado correctamente."
        )
        return "/panel/contacts/"

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user, own_presence and action flag to template context.
        ---
        Añade company, company_user, own_presence y flag de acción al contexto de la plantilla.
        """
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "contacts"
        context["action"] = "Crear"
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django.utils.timezone import now
        from django.db.models import Q
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class ContactUpdateView(AdminRoleRequiredMixin, UpdateView):
    """
    Allows an ADMIN to update an existing Contact belonging to their company.
    Prevents editing contacts from other companies.
    Restricts the company_user field to users belonging to the same company.
    ---
    Permite a un ADMIN actualizar un Contact existente de su empresa.
    Impide editar contactos de otras empresas.
    Restringe el campo company_user a usuarios de la misma empresa.
    """

    model = Contact
    form_class = ContactForm
    template_name = "panel/contacts/form.html"

    def get_queryset(self):
        """
        Restricts the queryset to Contact records of the authenticated user's company.
        ---
        Restringe el queryset a los registros Contact de la empresa del usuario autenticado.
        """
        return Contact.objects.filter(
            company=self.request.user.company_user.company
        )

    def get_form(self, form_class=None):
        """
        Restricts the company_user queryset in the form to the authenticated user's company.
        ---
        Restringe el queryset de company_user del formulario a la empresa del usuario autenticado.
        """
        form = super().get_form(form_class)
        form.fields["company_user"].queryset = CompanyUser.objects.filter(
            company=self.request.user.company_user.company
        ).select_related("user")
        form.fields["company_user"].required = False
        return form

    def get_success_url(self):
        """
        Redirects to the contact list after a successful update.
        ---
        Redirige a la lista de contactos tras una actualización correcta.
        """
        from django.contrib import messages as django_messages
        django_messages.success(
            self.request,
            f"Contacto '{self.object.name}' actualizado correctamente."
        )
        return "/panel/contacts/"

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user, own_presence and action flag to template context.
        ---
        Añade company, company_user, own_presence y flag de acción al contexto de la plantilla.
        """
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "contacts"
        context["action"] = "Editar"
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django.utils.timezone import now
        from django.db.models import Q
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class CallFlowListView(AdminRoleRequiredMixin, ListView):
    """
    Lists all CallFlow records belonging to the authenticated user's company.
    Accessible only to users with the ADMIN role.
    ---
    Lista todos los registros CallFlow pertenecientes a la empresa del usuario autenticado.
    Solo accesible para usuarios con rol ADMIN.
    """

    model = CallFlow
    template_name = "panel/callflows/list.html"
    context_object_name = "call_flows"

    def get_queryset(self):
        """
        Returns CallFlow records scoped to the authenticated user's company.
        ---
        Retorna los registros CallFlow acotados a la empresa del usuario autenticado.
        """
        return CallFlow.objects.filter(
            company=self.request.user.company_user.company
        ).order_by("name")

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user and own_presence to template context.
        ---
        Añade company, company_user y own_presence al contexto de la plantilla.
        """
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "callflows"
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django.utils.timezone import now
        from django.db.models import Q
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class CallFlowCreateView(AdminRoleRequiredMixin, CreateView):
    """
    Allows an ADMIN to create a new CallFlow for their company.
    Automatically assigns the company from the authenticated user's CompanyUser.
    Restricts the notification_contact queryset to the company's own contacts.
    Updated 2026-04-16 (Step 37.C — Estrategia B): fallback_section queryset
    restricted to the company's own active Sections.
    ---
    Permite a un ADMIN crear un nuevo CallFlow para su empresa.
    Asigna automáticamente la empresa desde el CompanyUser del usuario autenticado.
    Restringe el queryset de notification_contact a los contactos de la empresa.
    Actualización 2026-04-16 (Paso 37.C — Estrategia B): queryset de fallback_section
    restringido a las Sections activas de la empresa.
    """

    model = CallFlow
    form_class = CallFlowForm
    template_name = "panel/callflows/form.html"

    def get_form(self, form_class=None):
        """
        Restricts notification_contact queryset to the authenticated user's company.
        Restricts fallback_section queryset to the company's own active Sections
        (Estrategia B — Step 37.C). Both fields are optional.
        ---
        Restringe el queryset de notification_contact a la empresa del usuario autenticado.
        Restringe el queryset de fallback_section a las Sections activas de la empresa
        (Estrategia B — Paso 37.C). Ambos campos son opcionales.
        """
        form = super().get_form(form_class)
        company = self.request.user.company_user.company
        form.fields["notification_contact"].queryset = Contact.objects.filter(
            company=company
        ).order_by("name")
        form.fields["notification_contact"].required = False
        form.fields["fallback_section"].queryset = Section.objects.filter(
            company=company,
            is_active=True,
        ).order_by("name")
        form.fields["fallback_section"].required = False
        return form

    def form_valid(self, form):
        """
        Assigns the company before saving the new CallFlow.
        ---
        Asigna la empresa antes de guardar el nuevo CallFlow.
        """
        form.instance.company = self.request.user.company_user.company
        return super().form_valid(form)

    def get_success_url(self):
        """
        Redirects to the callflow list after a successful creation.
        ---
        Redirige a la lista de flujos IVR tras una creación correcta.
        """
        from django.contrib import messages as django_messages
        django_messages.success(
            self.request,
            f"Flujo IVR '{self.object.name}' creado correctamente."
        )
        return "/panel/callflows/"

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user, own_presence and action flag to template context.
        ---
        Añade company, company_user, own_presence y flag de acción al contexto de la plantilla.
        """
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "callflows"
        context["action"] = "Crear"
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django.utils.timezone import now
        from django.db.models import Q
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class CallFlowUpdateView(AdminRoleRequiredMixin, UpdateView):
    """
    Allows an ADMIN to update an existing CallFlow belonging to their company.
    Prevents editing call flows from other companies.
    Updated 2026-04-16 (Step 37.C — Estrategia B): fallback_section queryset
    restricted to the company's own active Sections.
    ---
    Permite a un ADMIN actualizar un CallFlow existente de su empresa.
    Impide editar flujos IVR de otras empresas.
    Actualización 2026-04-16 (Paso 37.C — Estrategia B): queryset de fallback_section
    restringido a las Sections activas de la empresa.
    """

    model = CallFlow
    form_class = CallFlowForm
    template_name = "panel/callflows/form.html"

    def get_queryset(self):
        """
        Restricts the queryset to CallFlow records of the authenticated user's company.
        ---
        Restringe el queryset a los registros CallFlow de la empresa del usuario autenticado.
        """
        return CallFlow.objects.filter(
            company=self.request.user.company_user.company
        )

    def get_form(self, form_class=None):
        """
        Restricts notification_contact queryset to the authenticated user's company.
        Restricts fallback_section queryset to the company's own active Sections
        (Estrategia B — Step 37.C). Both fields are optional.
        ---
        Restringe el queryset de notification_contact a la empresa del usuario autenticado.
        Restringe el queryset de fallback_section a las Sections activas de la empresa
        (Estrategia B — Paso 37.C). Ambos campos son opcionales.
        """
        form = super().get_form(form_class)
        company = self.request.user.company_user.company
        form.fields["notification_contact"].queryset = Contact.objects.filter(
            company=company
        ).order_by("name")
        form.fields["notification_contact"].required = False
        form.fields["fallback_section"].queryset = Section.objects.filter(
            company=company,
            is_active=True,
        ).order_by("name")
        form.fields["fallback_section"].required = False
        return form

    def form_valid(self, form):
        """
        Saves a backup snapshot of the current values before applying the new ones.
        Backup fields store the state BEFORE this save so the ADMIN can restore.

        Uses a direct DB values() query to retrieve the pre-save state, bypassing
        Django's UpdateView object cache which already holds the POST values at this
        point in the request cycle and would cause the backup to store the new value
        instead of the old one.

        ---

        Guarda un snapshot de backup de los valores actuales antes de aplicar los nuevos.
        Los campos backup almacenan el estado ANTERIOR a este guardado para que el ADMIN
        pueda restaurar.

        Usa una query values() directa a BD para obtener el estado pre-guardado, evitando
        la caché de objeto de UpdateView que en este punto del ciclo de petición ya contiene
        los valores del POST y causaría que el backup almacene el valor nuevo en lugar del antiguo.
        """
        # Fetch pre-save values directly from DB — bypasses UpdateView object cache.
        # Obtener valores pre-guardado directamente de BD — evita la caché de UpdateView.
        pre_save = CallFlow.objects.filter(pk=form.instance.pk).values(
            "name",
            "system_instruction",
            "initial_greeting",
            "notification_contact_id",
        ).first()

        if pre_save:
            form.instance.backup_name                    = pre_save["name"]
            form.instance.backup_system_instruction      = pre_save["system_instruction"]
            form.instance.backup_initial_greeting        = pre_save["initial_greeting"]
            form.instance.backup_notification_contact_id = pre_save["notification_contact_id"]

        return super().form_valid(form)

    def get_success_url(self):
        """
        Redirects to the callflow list after a successful update.
        ---
        Redirige a la lista de flujos IVR tras una actualización correcta.
        """
        from django.contrib import messages as django_messages
        django_messages.success(
            self.request,
            f"Flujo IVR '{self.object.name}' actualizado correctamente. "
            "Puedes restaurar la versión anterior desde el formulario de edición."
        )
        return "/panel/callflows/"

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user, own_presence, action flag and has_backup to context.
        ---
        Añade company, company_user, own_presence, flag de acción y has_backup al contexto.
        """
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "callflows"
        context["action"] = "Editar"
        # has_backup is True if a restorable snapshot exists in backup fields.
        # has_backup es True si existe un snapshot restaurable en los campos de backup.
        obj = self.get_object()
        context["has_backup"] = bool(
            obj.backup_name
            or obj.backup_system_instruction
            or obj.backup_initial_greeting
        )
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django.utils.timezone import now
        from django.db.models import Q
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class PhoneNumberListView(AdminRoleRequiredMixin, ListView):
    """
    Lists all PhoneNumber records belonging to the authenticated user's company.
    Read-only view: Twilio number assignment is managed by the superuser.
    Accessible only to users with the ADMIN role.
    ---
    Lista todos los registros PhoneNumber pertenecientes a la empresa del usuario autenticado.
    Vista de solo lectura: la asignación de números Twilio la gestiona el superusuario.
    Solo accesible para usuarios con rol ADMIN.
    """

    model = PhoneNumber
    template_name = "panel/phonenumbers/list.html"
    context_object_name = "phone_numbers"

    def get_queryset(self):
        """
        Returns PhoneNumber records scoped to the authenticated user's company.
        ---
        Retorna los registros PhoneNumber acotados a la empresa del usuario autenticado.
        """
        return PhoneNumber.objects.filter(
            company=self.request.user.company_user.company
        ).select_related("call_flow").order_by("number")

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user and own_presence to template context.
        ---
        Añade company, company_user y own_presence al contexto de la plantilla.
        """
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "phonenumbers"
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django.utils.timezone import now
        from django.db.models import Q
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class CorporateVoiceProfileUpdateView(AdminRoleRequiredMixin, View):
    """
    Allows an ADMIN to view and update the CorporateVoiceProfile of their company.
    If no profile exists yet, it is created on first POST submission.
    Uses View instead of UpdateView to handle the get-or-create pattern cleanly.
    ---
    Permite a un ADMIN ver y actualizar el CorporateVoiceProfile de su empresa.
    Si no existe perfil todavía, se crea en el primer envío POST.
    Usa View en lugar de UpdateView para gestionar el patrón get-or-create limpiamente.
    """

    template_name = "panel/voiceprofile/detail.html"

    def _get_profile_and_context(self, request):
        """
        Retrieves or initialises the CorporateVoiceProfile for the company.
        Returns a dict with company, company_user, own_presence and profile.
        ---
        Obtiene o inicializa el CorporateVoiceProfile de la empresa.
        Retorna un dict con company, company_user, own_presence y profile.
        """
        from django.utils.timezone import now
        from django.db.models import Q

        company_user = request.user.company_user
        company = company_user.company

        profile, _ = CorporateVoiceProfile.objects.get_or_create(
            company=company,
            defaults={
                "tone_guidelines": "",
                "sample_responses": [],
                "forbidden_phrases": [],
                "is_active": True,
            }
        )

        own_presence = PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

        return {
            "company":      company,
            "company_user": company_user,
            "own_presence": own_presence,
            "active_nav":   "voiceprofile",
            "profile":      profile,
        }

    def get(self, request, *args, **kwargs):
        """
        Renders the voice profile form pre-populated with the current profile data.
        ---
        Renderiza el formulario del perfil de voz prerellenado con los datos actuales.
        """
        from django.shortcuts import render
        ctx = self._get_profile_and_context(request)
        ctx["form"] = CorporateVoiceProfileForm(instance=ctx["profile"])
        return render(request, self.template_name, ctx)

    def post(self, request, *args, **kwargs):
        """
        Updates the CorporateVoiceProfile with the submitted data.
        ---
        Actualiza el CorporateVoiceProfile con los datos enviados.
        """
        from django.shortcuts import render, redirect
        from django.contrib import messages as django_messages

        ctx = self._get_profile_and_context(request)
        form = CorporateVoiceProfileForm(request.POST, instance=ctx["profile"])

        if form.is_valid():
            profile = ctx["profile"]
            # Snapshot current (pre-save) values into backup fields before saving.
            # Capturar valores actuales (pre-guardado) en los campos de backup antes de guardar.
            instance = form.save(commit=False)
            instance.backup_voice_name        = profile.voice_name
            instance.backup_tone_guidelines   = profile.tone_guidelines
            instance.backup_sample_responses  = profile.sample_responses
            instance.backup_forbidden_phrases = profile.forbidden_phrases
            instance.save()
            django_messages.success(
                request,
                "Perfil de voz corporativa actualizado correctamente. "
                "Puedes restaurar la versión anterior desde este mismo formulario."
            )
            return redirect("panel:voiceprofile_detail")

        ctx["form"] = form
        return render(request, self.template_name, ctx)


class CallFlowRestoreView(AdminRoleRequiredMixin, View):
    """
    Restores a CallFlow to its previous backup snapshot with a single POST.
    Swaps active fields ↔ backup fields so the backup becomes the new backup
    (enabling a second restore to redo the change if needed).
    Restricted to CallFlow records belonging to the authenticated user's company.
    ---
    Restaura un CallFlow a su snapshot de backup anterior con un solo POST.
    Intercambia los campos activos ↔ backup para que el backup sea el nuevo backup
    (permitiendo una segunda restauración para rehacer el cambio si es necesario).
    Restringido a registros CallFlow de la empresa del usuario autenticado.
    """

    def post(self, request, pk, *args, **kwargs):
        """
        Performs the active ↔ backup field swap and redirects to the edit form.
        ---
        Realiza el intercambio activo ↔ backup y redirige al formulario de edición.
        """
        try:
            flow = CallFlow.objects.get(
                pk=pk,
                company=request.user.company_user.company
            )
        except CallFlow.DoesNotExist:
            django_messages.error(request, "Flujo IVR no encontrado.")
            return redirect("/panel/callflows/")

        if (
            not flow.backup_name
            and not flow.backup_system_instruction
            and not flow.backup_initial_greeting
        ):
            django_messages.warning(
                request,
                "No existe versión anterior para restaurar en este flujo IVR."
            )
            return redirect(f"/panel/callflows/{pk}/edit/")

        # Capture pre-swap values into local variables BEFORE the update call.
        # Python evaluates keyword arguments left-to-right — capturing into
        # locals guarantees the correct pre-swap state is written to DB.
        #
        # Capturar valores pre-swap en variables locales ANTES de la llamada
        # al update para garantizar que el estado pre-swap correcto se escribe en BD.
        active_name            = flow.name
        active_system          = flow.system_instruction
        active_greeting        = flow.initial_greeting
        active_notification    = flow.notification_contact_id
        backup_name            = flow.backup_name
        backup_system          = flow.backup_system_instruction
        backup_greeting        = flow.backup_initial_greeting
        backup_notification    = flow.backup_notification_contact_id

        CallFlow.objects.filter(pk=flow.pk).update(
            name                           = backup_name or active_name,
            backup_name                    = active_name,
            system_instruction             = backup_system,
            backup_system_instruction      = active_system,
            initial_greeting               = backup_greeting,
            backup_initial_greeting        = active_greeting,
            notification_contact_id        = backup_notification,
            backup_notification_contact_id = active_notification,
        )
        django_messages.success(
            request,
            f"Flujo IVR '{flow.name}' restaurado a la versión anterior correctamente."
        )
        return redirect(f"/panel/callflows/{pk}/edit/")


class VoiceProfileRestoreView(AdminRoleRequiredMixin, View):
    """
    Restores the CorporateVoiceProfile to its previous backup snapshot with a single POST.
    Swaps active fields ↔ backup fields to allow bidirectional restore.
    Restricted to the profile of the authenticated user's company.
    ---
    Restaura el CorporateVoiceProfile a su snapshot de backup anterior con un solo POST.
    Intercambia los campos activos ↔ backup para permitir restauración bidireccional.
    Restringido al perfil de la empresa del usuario autenticado.
    """

    def post(self, request, *args, **kwargs):
        """
        Performs the active ↔ backup field swap and redirects to the voice profile form.
        ---
        Realiza el intercambio activo ↔ backup y redirige al formulario del perfil de voz.
        """
        try:
            profile = CorporateVoiceProfile.objects.get(
                company=request.user.company_user.company
            )
        except CorporateVoiceProfile.DoesNotExist:
            django_messages.error(request, "Perfil de voz no encontrado.")
            return redirect("panel:voiceprofile_detail")

        if not profile.backup_tone_guidelines and not profile.backup_voice_name:
            django_messages.warning(
                request,
                "No existe versión anterior para restaurar en el perfil de voz."
            )
            return redirect("panel:voiceprofile_detail")

        # Swap active ↔ backup — bidirectional restore support.
        # Intercambiar activo ↔ backup — soporte de restauración bidireccional.
        (
            profile.voice_name,        profile.backup_voice_name,
        ) = (
            profile.backup_voice_name,  profile.voice_name,
        )
        (
            profile.tone_guidelines,       profile.backup_tone_guidelines,
        ) = (
            profile.backup_tone_guidelines, profile.tone_guidelines,
        )
        (
            profile.sample_responses,       profile.backup_sample_responses,
        ) = (
            profile.backup_sample_responses, profile.sample_responses,
        )
        (
            profile.forbidden_phrases,       profile.backup_forbidden_phrases,
        ) = (
            profile.backup_forbidden_phrases, profile.forbidden_phrases,
        )
        profile.save(update_fields=[
            "voice_name",
            "backup_voice_name",
            "tone_guidelines",
            "backup_tone_guidelines",
            "sample_responses",
            "backup_sample_responses",
            "forbidden_phrases",
            "backup_forbidden_phrases",
        ])
        django_messages.success(
            request,
            "Perfil de voz restaurado a la versión anterior correctamente."
        )
        return redirect("panel:voiceprofile_detail")


class BlockedCallerListView(AdminRoleRequiredMixin, ListView):
    """
    Lists all BlockedCaller records for the authenticated user's company.
    Shows active blocks (blocked_until > now) and expired history separately.
    Accessible only to users with the ADMIN role.
    ---
    Lista todos los registros BlockedCaller de la empresa del usuario autenticado.
    Muestra los bloqueos activos (blocked_until > now) e historial expirado por separado.
    Solo accesible para usuarios con rol ADMIN.
    """

    model = BlockedCaller
    template_name = "panel/blockedcallers/list.html"
    context_object_name = "blocked_callers"

    def get_queryset(self):
        """
        Returns all BlockedCaller records for the company, ordered by most recent first.
        ---
        Retorna todos los registros BlockedCaller de la empresa, ordenados por más reciente primero.
        """
        return BlockedCaller.objects.filter(
            company=self.request.user.company_user.company
        ).select_related("blocked_by").order_by("-blocked_at")

    def get_context_data(self, **kwargs):
        """
        Adds active/expired partition, company, company_user and own_presence to context.
        ---
        Añade la partición activos/expirados, company, company_user y own_presence al contexto.
        """
        context = super().get_context_data(**kwargs)
        company_user = self.request.user.company_user
        all_records = context["blocked_callers"]
        context["active_blocks"] = [b for b in all_records if b.is_active]
        context["expired_blocks"] = [b for b in all_records if not b.is_active]
        context["company"] = company_user.company
        context["company_user"] = company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "blockedcallers"
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class BlockedCallerCreateView(AdminRoleRequiredMixin, CreateView):
    """
    Allows an ADMIN to manually block a phone number for their company.
    Automatically assigns the company and blocked_by from the authenticated user.
    ---
    Permite a un ADMIN bloquear manualmente un número de teléfono para su empresa.
    Asigna automáticamente la empresa y blocked_by desde el usuario autenticado.
    """

    model = BlockedCaller
    form_class = BlockedCallerForm
    template_name = "panel/blockedcallers/form.html"

    def form_valid(self, form):
        """
        Assigns company and blocked_by before saving the new BlockedCaller.
        ---
        Asigna company y blocked_by antes de guardar el nuevo BlockedCaller.
        """
        from django.contrib import messages as django_messages
        form.instance.company = self.request.user.company_user.company
        form.instance.blocked_by = self.request.user
        response = super().form_valid(form)
        django_messages.success(
            self.request,
            f"Número {self.object.phone_number} bloqueado hasta {self.object.blocked_until:%d/%m/%Y %H:%M}."
        )
        return response

    def get_success_url(self):
        """
        Redirects to the blocked callers list after a successful creation.
        ---
        Redirige a la lista de bloqueados tras una creación correcta.
        """
        return "/panel/blockedcallers/"

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user, own_presence and action flag to template context.
        ---
        Añade company, company_user, own_presence y flag de acción al contexto de la plantilla.
        """
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "blockedcallers"
        context["action"] = "Bloquear número"
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class BlockedCallerDeleteView(AdminRoleRequiredMixin, DeleteView):
    """
    Allows an ADMIN to manually unblock a phone number before its expiry.
    Restricted to BlockedCaller records belonging to the authenticated user's company.
    Uses DELETE method via a confirmation form in the template.
    ---
    Permite a un ADMIN desbloquear manualmente un número antes de su vencimiento.
    Restringido a registros BlockedCaller de la empresa del usuario autenticado.
    Usa el método DELETE mediante un formulario de confirmación en la plantilla.
    """

    model = BlockedCaller
    template_name = "panel/blockedcallers/confirm_delete.html"

    def get_queryset(self):
        """
        Restricts deletion to BlockedCaller records of the authenticated user's company.
        ---
        Restringe la eliminación a registros BlockedCaller de la empresa del usuario autenticado.
        """
        return BlockedCaller.objects.filter(
            company=self.request.user.company_user.company
        )

    def get_success_url(self):
        """
        Redirects to the blocked callers list after successful deletion.
        ---
        Redirige a la lista de bloqueados tras la eliminación correcta.
        """
        from django.contrib import messages as django_messages
        django_messages.success(
            self.request,
            f"Número {self.object.phone_number} desbloqueado correctamente."
        )
        return "/panel/blockedcallers/"

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user and own_presence to template context.
        ---
        Añade company, company_user y own_presence al contexto de la plantilla.
        """
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "blockedcallers"
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class PanelLoginView(LoginView):
    """
    Login view for the panel application.
    Uses the custom PanelAuthenticationForm.
    Authenticated users with an active CompanyUser are redirected to the dashboard.
    Authenticated users without a CompanyUser (e.g. superusers) see the login form normally.
    ---
    Vista de login para la aplicación panel.
    Usa el PanelAuthenticationForm personalizado.
    Los usuarios autenticados con CompanyUser activo son redirigidos al dashboard.
    Los usuarios autenticados sin CompanyUser (p.ej. superusuarios) ven el formulario normalmente.
    """

    template_name = "panel/login.html"
    authentication_form = PanelAuthenticationForm
    next_page = "/panel/"

    def dispatch(self, request, *args, **kwargs):
        """
        Redirect authenticated CompanyUser accounts directly to the dashboard.
        Superusers and users without CompanyUser proceed to the login form normally.
        ---
        Redirige las cuentas CompanyUser autenticadas directamente al dashboard.
        Los superusuarios y usuarios sin CompanyUser acceden al formulario normalmente.
        """
        # Only redirect if authenticated AND has an active CompanyUser linked.
        # Solo redirigir si está autenticado Y tiene un CompanyUser activo vinculado.
        if request.user.is_authenticated:
            company_user = getattr(request.user, "company_user", None)
            if company_user is not None and company_user.is_active:
                from django.shortcuts import redirect
                return redirect(self.next_page)
        return super().dispatch(request, *args, **kwargs)


class PresenceStatusUpdateView(CompanyUserRequiredMixin, View):
    """
    View for displaying and updating the authenticated user's own presence status.
    GET:  Renders the presence status form pre-populated with the current active state.
    POST: Closes the current active PresenceStatus and creates a new one.
    ---
    Vista para mostrar y actualizar el estado de presencia del usuario autenticado.
    GET:  Renderiza el formulario de presencia prerellenado con el estado activo actual.
    POST: Cierra el PresenceStatus activo actual y crea uno nuevo.
    """

    template_name = "panel/presence/status.html"

    def _get_active_presence(self, company_user):
        """
        Returns the current active PresenceStatus for the given CompanyUser, or None.
        ---
        Retorna el PresenceStatus activo actual para el CompanyUser dado, o None.
        """
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

    def get(self, request, *args, **kwargs):
        """
        Renders the presence status page with the current active status and the form.
        ---
        Renderiza la página de estado de presencia con el estado activo actual y el formulario.
        """
        from django.shortcuts import render
        company_user = request.user.company_user
        active_presence = self._get_active_presence(company_user)
        form = PresenceStatusForm(instance=active_presence)

        return render(request, self.template_name, {
            "company":    company_user.company,
            "company_user": company_user,
            "own_presence": active_presence,
            "active_nav": "presence",
            "form":       form,
        })

    def post(self, request, *args, **kwargs):
        """
        Closes the current active PresenceStatus and creates a new one with
        the submitted status and optional ends_at.
        ---
        Cierra el PresenceStatus activo actual y crea uno nuevo con el estado
        enviado y el ends_at opcional.
        """
        from django.shortcuts import render
        from django.contrib import messages as django_messages

        company_user = request.user.company_user
        form = PresenceStatusForm(request.POST)

        if form.is_valid():
            # Close all currently open presence statuses for this user.
            # Cerrar todos los estados de presencia abiertos actualmente para este usuario.
            PresenceStatus.objects.filter(
                company_user=company_user,
                starts_at__lte=now(),
            ).filter(
                Q(ends_at__isnull=True) | Q(ends_at__gt=now())
            ).update(ends_at=now())

            # Create the new presence status.
            # Crear el nuevo estado de presencia.
            new_status = form.save(commit=False)
            new_status.company_user = company_user
            new_status.save()

            django_messages.success(
                request,
                f"Estado de presencia actualizado a: {new_status.get_status_display()}"
            )
            return redirect("panel:presence_status")

        # Re-render form with validation errors.
        # Rerenderizar el formulario con errores de validación.
        active_presence = self._get_active_presence(company_user)
        return render(request, self.template_name, {
            "company":    company_user.company,
            "company_user": company_user,
            "own_presence": active_presence,
            "active_nav": "presence",
            "form":       form,
        })


class PanelLogoutView(LogoutView):
    """
    Logout view for the panel application.
    Redirects to the panel login page after session termination.

    Django 5.x restricts LogoutView to POST-only by default (CSRF protection).
    The panel sidebar uses a plain <a> link (GET request) to trigger logout.
    The get() override handles this case by delegating to post(), which
    executes Django's standard session termination and redirects cleanly.
    ---
    Vista de logout para la aplicación panel.
    Redirige a la página de login del panel tras la terminación de sesión.

    Django 5.x restringe LogoutView a POST exclusivamente por defecto (protección CSRF).
    El sidebar del panel usa un enlace <a> simple (petición GET) para disparar el logout.
    El override de get() gestiona este caso delegando en post(), que ejecuta la
    terminación de sesión estándar de Django y redirige correctamente.
    """

    http_method_names = ['get', 'post', 'head', 'options']
    next_page = "/panel/login/"

    def get(self, request, *args, **kwargs):
        """
        Handles GET logout requests from the panel sidebar link.
        Delegates to post() to execute standard Django session termination.
        ---
        Gestiona las peticiones GET de logout desde el enlace del sidebar del panel.
        Delega en post() para ejecutar la terminación de sesión estándar de Django.
        """
        return self.post(request, *args, **kwargs)


class PanelDashboardView(CompanyUserRequiredMixin, TemplateView):
    """
    Main dashboard view for authenticated CompanyUser accounts.
    Provides a summary of the company's active sections, total contacts,
    and the current presence status of the authenticated user.
    ---
    Vista principal del dashboard para cuentas CompanyUser autenticadas.
    Proporciona un resumen de las secciones activas de la empresa, el total
    de contactos y el estado de presencia actual del usuario autenticado.
    """

    template_name = "panel/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        """
        Redirect WORKSHOP users to the operator dashboard immediately.
        ADMIN and OPERATOR users proceed to the standard dashboard.
        ---
        Redirige a los usuarios WORKSHOP al dashboard de operario inmediatamente.
        Los usuarios ADMIN y OPERATOR continúan al dashboard estándar.
        """
        # Delegate authentication and CompanyUser checks to parent first.
        # Delegar las comprobaciones de autenticación y CompanyUser al padre primero.
        response = super().dispatch(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return response

        company_user = getattr(request.user, "company_user", None)
        if company_user and company_user.role == CompanyUser.ROLE_WORKSHOP:
            return redirect("/panel/operator/")

        return response

    def get_context_data(self, **kwargs):
        """
        Build dashboard context with company summary and own presence status.
        ---
        Construye el contexto del dashboard con el resumen de empresa y el
        estado de presencia propio.
        """
        context = super().get_context_data(**kwargs)

        # CompanyUserRequiredMixin guarantees company_user exists at this point.
        # CompanyUserRequiredMixin garantiza que company_user existe en este punto.
        company_user = self.request.user.company_user
        company = company_user.company

        # Retrieve active sections count for the company.
        # Obtener el recuento de secciones activas de la empresa.
        active_sections = Section.objects.filter(
            company=company,
            is_active=True,
        )

        # Retrieve total contacts count for the company.
        # Obtener el recuento total de contactos de la empresa.
        total_contacts = Contact.objects.filter(company=company).count()

        # Retrieve current active presence status for the authenticated user.
        # Obtener el estado de presencia activo actual del usuario autenticado.
        from django.utils.timezone import now
        from django.db.models import Q

        own_presence = PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

        context["company"] = company
        context["company_user"] = company_user
        context["active_sections"] = active_sections
        context["active_sections_count"] = active_sections.count()
        context["total_contacts"] = total_contacts
        context["own_presence"] = own_presence
        context["active_nav"] = "dashboard"

        return context


class PanelPasswordChangeView(CompanyUserRequiredMixin, View):
    """
    Allows any authenticated CompanyUser to change their own password.
    When must_change_password=True this view is mandatory — the mixin
    blocks all other panel URLs until the password is updated.
    On success, must_change_password is cleared and the session auth hash
    is refreshed so the user stays logged in.
    ---
    Permite a cualquier CompanyUser autenticado cambiar su propia contraseña.
    Cuando must_change_password=True esta vista es obligatoria — el mixin
    bloquea todas las demás URLs del panel hasta que se actualice la contraseña.
    Al guardar, must_change_password se limpia y el hash de sesión se refresca
    para que el usuario permanezca autenticado.
    """

    template_name = "panel/password/change.html"

    def _get_own_presence(self, company_user):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

    def _build_form(self, request, data=None):
        """
        Returns the appropriate password form depending on whether the change
        is forced (must_change_password=True) or voluntary.

        Forced change  → PanelSetPasswordForm: does not require old_password.
                         The newly created user does not know the system-assigned
                         initial password ('1234') and must not be asked for it.
        Voluntary change → PanelPasswordChangeForm: requires old_password as
                           an additional security gate.
        ---
        Retorna el formulario de contraseña adecuado según si el cambio es
        forzado (must_change_password=True) o voluntario.

        Cambio forzado   → PanelSetPasswordForm: no requiere old_password.
                           El usuario recién creado desconoce la contraseña
                           inicial asignada por el sistema ('1234') y no debe
                           ser preguntado por ella.
        Cambio voluntario → PanelPasswordChangeForm: requiere old_password como
                            barrera de seguridad adicional.
        """
        cu = request.user.company_user
        if cu.must_change_password:
            # Forced flow: only new_password1 + new_password2 required.
            # Flujo forzado: solo new_password1 + new_password2 requeridos.
            return PanelSetPasswordForm(user=request.user, data=data)
        # Voluntary flow: old_password + new_password1 + new_password2.
        # Flujo voluntario: old_password + new_password1 + new_password2.
        return PanelPasswordChangeForm(user=request.user, data=data)

    def _get_context(self, request, form=None):
        """
        Builds template context including is_forced flag for UI messaging.
        When is_forced=True the template hides the old_password block, since
        PanelSetPasswordForm does not expose that field.
        ---
        Construye el contexto de plantilla incluyendo el flag is_forced para la UI.
        Cuando is_forced=True el template oculta el bloque old_password, ya que
        PanelSetPasswordForm no expone ese campo.
        """
        cu = request.user.company_user
        return {
            "company":      cu.company,
            "company_user": cu,
            "own_presence": self._get_own_presence(cu),
            "active_nav":   "",
            "form":         form or self._build_form(request),
            "is_forced":    cu.must_change_password,
        }

    def get(self, request, *args, **kwargs):
        """
        Renders the password change form (forced or voluntary depending on context).
        ---
        Renderiza el formulario de cambio de contraseña (forzado o voluntario
        según el contexto).
        """
        return render(request, self.template_name, self._get_context(request))

    def post(self, request, *args, **kwargs):
        """
        Validates and saves the new password using the appropriate form.
        On success clears must_change_password (if forced), updates the session
        auth hash so the user stays logged in, and redirects to the dashboard.
        ---
        Valida y guarda la nueva contraseña usando el formulario adecuado.
        En caso de éxito limpia must_change_password (si es forzado), actualiza
        el hash de sesión para que el usuario permanezca autenticado y redirige
        al dashboard.
        """
        form = self._build_form(request, data=request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)
            cu = request.user.company_user
            if cu.must_change_password:
                cu.must_change_password = False
                cu.save(update_fields=["must_change_password"])
            django_messages.success(request, "Contraseña actualizada correctamente.")
            return redirect("/panel/")
        return render(request, self.template_name, self._get_context(request, form))


# ---------------------------------------------------------------------------
# WHATSAPP TEMPLATE LIST VIEW — Read-only list of Meta-approved templates.
# Vista de listado de plantillas WhatsApp — Solo lectura. Requiere rol ADMIN.
# Paso 24 — Hito 4 (2026-04-20)
# ---------------------------------------------------------------------------

class WhatsAppTemplateListView(AdminRoleRequiredMixin, ListView):
    """
    Displays a read-only list of active WhatsAppTemplate records scoped to
    the authenticated user's company. Accessible only to users with the
    ADMIN role. No create, update or delete actions are exposed — templates
    are managed exclusively via the Twilio Content Template Builder and
    seeded through the seed_whatsapp_templates management command.
    ---
    Muestra un listado de solo lectura de los registros WhatsAppTemplate
    activos acotados a la empresa del usuario autenticado. Solo accesible
    para usuarios con rol ADMIN. No se exponen acciones de creación, edición
    ni borrado — las plantillas se gestionan exclusivamente a través del
    Content Template Builder de Twilio y se registran mediante el comando
    de gestión seed_whatsapp_templates.
    """

    model = WhatsAppTemplate
    template_name = "panel/whatsapp/template_list.html"
    context_object_name = "templates"

    def get_queryset(self):
        """
        Returns active WhatsAppTemplate records scoped to the authenticated
        user's company, ordered alphabetically by name.
        ---
        Retorna los registros WhatsAppTemplate activos acotados a la empresa
        del usuario autenticado, ordenados alfabéticamente por nombre.
        """
        return WhatsAppTemplate.objects.filter(
            company=self.request.user.company_user.company,
            is_active=True,
        ).order_by("name")

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user and own_presence to the template context,
        following the same pattern as all other panel ListViews.
        ---
        Añade company, company_user y own_presence al contexto de la plantilla,
        siguiendo el mismo patrón que el resto de ListViews del panel.
        """
        context = super().get_context_data(**kwargs)
        context["company"]      = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"]   = "whatsapp_templates"
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django.utils.timezone import now
        from django.db.models import Q
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

# ---------------------------------------------------------------------------
# WHATSAPP ACTIVE SESSION LIST VIEW — Active WhatsApp sessions for the company.
# Vista de sesiones WhatsApp activas de la empresa. Requiere rol ADMIN.
# Paso 1 — Hito 5 (2026-04-20)
# ---------------------------------------------------------------------------

class WhatsAppActiveSessionListView(AdminRoleRequiredMixin, ListView):
    """
    Displays a list of active WhatsAppSession records scoped to the
    authenticated user's company, ordered by most recently updated.
    A session is considered active when its status field equals 'active'.
    Accessible only to users with the ADMIN role.
    Each row shows: origin number, session start, last inbound message
    excerpt, and a link to the full session history.
    ---
    Muestra un listado de los registros WhatsAppSession activos acotados
    a la empresa del usuario autenticado, ordenados por actualizacion
    mas reciente. Una sesion se considera activa cuando su campo status
    es igual a 'active'. Solo accesible para usuarios con rol ADMIN.
    Cada fila muestra: numero de origen, inicio de sesion, extracto del
    ultimo mensaje entrante y enlace al historial completo.
    """

    model = WhatsAppSession
    template_name = "panel/whatsapp/active_session_list.html"
    context_object_name = "active_sessions"

    def get_queryset(self):
        """
        Returns active WhatsAppSession records scoped to the authenticated
        user's company, with last inbound message prefetched for excerpt display.
        ---
        Retorna los registros WhatsAppSession activos acotados a la empresa
        del usuario autenticado, con el ultimo mensaje entrante precargado
        para mostrar el extracto.
        """
        from whatsapp.models import WhatsAppMessage
        return (
            WhatsAppSession.objects.filter(
                company=self.request.user.company_user.company,
                is_active=True,
            )
            .prefetch_related(
                Prefetch(
                    "messages",
                    queryset=WhatsAppMessage.objects.filter(
                        direction="IN"
                    ).order_by("-timestamp")[:1],
                    to_attr="last_inbound",
                )
            )
            .order_by("-last_message_at")
        )

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user and own_presence to the template context.
        ---
        Anade company, company_user y own_presence al contexto de la plantilla.
        """
        context = super().get_context_data(**kwargs)
        context["company"]      = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"]   = "whatsapp_sessions"
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


# ===========================================================================
# DATA CAPTURE SET VIEWS — Gestión de conjuntos de captura de datos IVR.
# Paso 8-pre — Hito 5 (2026-04-21)
# ===========================================================================

class DataCaptureSetListView(AdminRoleRequiredMixin, ListView):
    """
    Lists all DataCaptureSet records belonging to the authenticated user's company.
    Accessible only to users with the ADMIN role.
    ---
    Lista todos los registros DataCaptureSet pertenecientes a la empresa del usuario autenticado.
    Solo accesible para usuarios con rol ADMIN.
    """

    model = DataCaptureSet
    template_name = "panel/datacapturesets/list.html"
    context_object_name = "capture_sets"

    def get_queryset(self):
        """
        Returns DataCaptureSet records scoped to the authenticated user's company,
        ordered alphabetically by name.
        ---
        Retorna los registros DataCaptureSet acotados a la empresa del usuario autenticado,
        ordenados alfabéticamente por nombre.
        """
        return DataCaptureSet.objects.filter(
            company=self.request.user.company_user.company
        ).order_by("name")

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user and own_presence to template context.
        ---
        Añade company, company_user y own_presence al contexto de la plantilla.
        """
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "datacapturesets"
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class DataCaptureSetCreateView(AdminRoleRequiredMixin, CreateView):
    """
    Allows an ADMIN to create a new DataCaptureSet for their company.
    Automatically assigns the company from the authenticated user's CompanyUser.
    The 'fields' JSONField is populated by the JS dynamic row builder in the
    template, which serialises the field definitions to JSON before submit.
    ---
    Permite a un ADMIN crear un nuevo DataCaptureSet para su empresa.
    Asigna automáticamente la empresa desde el CompanyUser del usuario autenticado.
    El JSONField 'fields' es rellenado por el constructor de filas JS dinámico del
    template, que serializa las definiciones de campos a JSON antes del submit.
    """

    model = DataCaptureSet
    form_class = DataCaptureSetForm
    template_name = "panel/datacapturesets/form.html"

    def form_valid(self, form):
        """
        Assigns the company before saving the new DataCaptureSet.
        Deserialises the 'fields_json' hidden input into the model's JSONField.
        ---
        Asigna la empresa antes de guardar el nuevo DataCaptureSet.
        Deserializa el campo oculto 'fields_json' en el JSONField del modelo.
        """
        import json
        form.instance.company = self.request.user.company_user.company
        raw_json = self.request.POST.get("fields_json", "[]")
        try:
            form.instance.fields = json.loads(raw_json)
        except (ValueError, TypeError):
            form.instance.fields = []
        return super().form_valid(form)

    def get_success_url(self):
        """
        Redirects to the DataCaptureSet list after a successful creation.
        ---
        Redirige a la lista de conjuntos de captura tras una creación correcta.
        """
        django_messages.success(
            self.request,
            f"Conjunto de captura '{self.object.name}' creado correctamente."
        )
        return "/panel/datacapturesets/"

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user, own_presence and action flag to template context.
        Adds existing_fields_json for pre-population on edit (empty list on create).
        ---
        Añade company, company_user, own_presence y flag de acción al contexto de la plantilla.
        Añade existing_fields_json para prerellenar en edición (lista vacía en creación).
        """
        import json
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "datacapturesets"
        context["action"] = "Crear"
        context["existing_fields_json"] = json.dumps([])
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class DataCaptureSetUpdateView(AdminRoleRequiredMixin, UpdateView):
    """
    Allows an ADMIN to update an existing DataCaptureSet belonging to their company.
    Prevents editing DataCaptureSets from other companies.
    The 'fields' JSONField is updated by the JS dynamic row builder in the template.
    ---
    Permite a un ADMIN actualizar un DataCaptureSet existente de su empresa.
    Impide editar conjuntos de captura de otras empresas.
    El JSONField 'fields' se actualiza por el constructor de filas JS dinámico del template.
    """

    model = DataCaptureSet
    form_class = DataCaptureSetForm
    template_name = "panel/datacapturesets/form.html"

    def get_queryset(self):
        """
        Restricts the queryset to DataCaptureSet records of the authenticated user's company.
        ---
        Restringe el queryset a los registros DataCaptureSet de la empresa del usuario autenticado.
        """
        return DataCaptureSet.objects.filter(
            company=self.request.user.company_user.company
        )

    def form_valid(self, form):
        """
        Deserialises the 'fields_json' hidden input into the model's JSONField before saving.
        ---
        Deserializa el campo oculto 'fields_json' en el JSONField del modelo antes de guardar.
        """
        import json
        raw_json = self.request.POST.get("fields_json", "[]")
        try:
            form.instance.fields = json.loads(raw_json)
        except (ValueError, TypeError):
            form.instance.fields = []
        return super().form_valid(form)

    def get_success_url(self):
        """
        Redirects to the DataCaptureSet list after a successful update.
        ---
        Redirige a la lista de conjuntos de captura tras una actualización correcta.
        """
        django_messages.success(
            self.request,
            f"Conjunto de captura '{self.object.name}' actualizado correctamente."
        )
        return "/panel/datacapturesets/"

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user, own_presence and action flag to template context.
        Serialises the existing fields JSONField for pre-population of the JS row builder.
        ---
        Añade company, company_user, own_presence y flag de acción al contexto de la plantilla.
        Serializa el JSONField fields existente para prerellenar el constructor de filas JS.
        """
        import json
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = self._get_own_presence()
        context["active_nav"] = "datacapturesets"
        context["action"] = "Guardar"
        context["existing_fields_json"] = json.dumps(self.object.fields or [])
        return context

    def _get_own_presence(self):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        company_user = self.request.user.company_user
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()


class WorkOrderListView(SupervisorAccessMixin, View):
    """
    Lists WorkOrder records belonging to the authenticated user's company,
    split into four querysets for the tabbed UI introduced in Hito 8 / Bloque H:
      wo_queue    — PENDING or PROCESSING (polling tab).
      wo_error    — ERROR.
      wo_pending  — DONE, not yet reviewed (pending supervisor sign-off).
      wo_reviewed — DONE and reviewed.

    Accessible to SUPERVISOR and ADMIN roles (SupervisorAccessMixin).
    ---
    Lista los registros WorkOrder de la empresa del usuario autenticado,
    divididos en cuatro querysets para la UI de pestañas introducida en
    el Hito 8 / Bloque H:
      wo_queue    — PENDING o PROCESSING (pestaña con polling).
      wo_error    — ERROR.
      wo_pending  — DONE sin revisión (pendiente de validación del Supervisor).
      wo_reviewed — DONE y revisados.

    Accesible para los roles SUPERVISOR y ADMIN (SupervisorAccessMixin).
    """

    template_name = "panel/work_orders/list.html"

    def _get_own_presence(self, company_user):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django.db.models import Q
        from django.utils.timezone import now
        from ivr_config.models import PresenceStatus
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

    def get(self, request):
        """
        Renders the tabbed work order list with four filtered querysets.
        The active tab defaults to "Pendiente revisión" when there are pending
        work orders; otherwise defaults to "En cola".
        ---
        Renderiza la lista de partes con pestañas y cuatro querysets filtrados.
        La pestaña activa por defecto es "Pendiente revisión" si hay partes
        pendientes; en caso contrario, "En cola".
        """
        company_user = request.user.company_user
        company      = company_user.company

        # Four querysets for the tabbed UI — Hito 8 / Bloque H.
        # Cuatro querysets para la UI de pestañas — Hito 8 / Bloque H.
        wo_queue = (
            WorkOrder.objects
            .filter(
                company=company,
                source=WorkOrder.Source.PDF_UPLOAD,
                status__in=[
                    WorkOrder.Status.PENDING,
                    WorkOrder.Status.PROCESSING,
                ],
            )
            .order_by("-upload_date")
        )
        wo_error = (
            WorkOrder.objects
            .filter(
                company=company,
                source=WorkOrder.Source.PDF_UPLOAD,
                status=WorkOrder.Status.ERROR,
            )
            .order_by("-upload_date")
        )
        wo_pending = (
            WorkOrder.objects
            .filter(
                company=company,
                source=WorkOrder.Source.PDF_UPLOAD,
                status=WorkOrder.Status.DONE,
                reviewed=False,
            )
            .order_by("-upload_date")
        )
        wo_reviewed = (
            WorkOrder.objects
            .filter(
                company=company,
                source=WorkOrder.Source.PDF_UPLOAD,
                status=WorkOrder.Status.DONE,
                reviewed=True,
            )
            .select_related("reviewed_by__user")
            .order_by("-upload_date")
        )

        # Default active tab: "pending" if there are unreviewed DONE orders,
        # otherwise "queue".
        # Pestaña activa por defecto: "pending" si hay DONE sin revisar,
        # en caso contrario "queue".
        default_tab = "pending" if wo_pending.exists() else "queue"

        return render(request, self.template_name, {
            "company":      company,
            "company_user": company_user,
            "own_presence": self._get_own_presence(company_user),
            "active_nav":   "work_orders",
            "wo_queue":     wo_queue,
            "wo_error":     wo_error,
            "wo_pending":   wo_pending,
            "wo_reviewed":  wo_reviewed,
            "default_tab":  default_tab,
        })


class WorkOrderUploadView(SupervisorAccessMixin, View):
    """
    Handles PDF upload for work order processing.
    On POST: validates the file, runs a duplicate detection check before
    creating the WorkOrder, enqueues the Celery processing task immediately
    via process_work_order_pdf.delay_on_commit() and redirects to the list.

    Duplicate detection (Hito 8, Paso 5, Bloque E):
      Before creating a new WorkOrder the view extracts the worker name and
      work period from the uploaded PDF filename and checks for an existing
      WorkOrder for the same company with the same worker name and an
      overlapping period. If a duplicate is found and the POST does not
      include confirm_overwrite=1, the upload form is re-rendered with the
      duplicate_wo context variable so the template can show a warning modal.
      If the user confirms overwrite, the duplicate WorkOrder (and all its
      cascade-deleted children) is deleted before the new one is created.

    Accessible to SUPERVISOR and ADMIN roles (SupervisorAccessMixin).
    ---
    Gestiona la carga de PDF para el procesamiento de partes de trabajo.
    En POST: valida el archivo, ejecuta una comprobación de duplicado antes
    de crear el WorkOrder, encola la tarea Celery inmediatamente mediante
    process_work_order_pdf.delay_on_commit() y redirige a la lista.

    Detección de duplicado (Hito 8, Paso 5, Bloque E):
      Antes de crear un nuevo WorkOrder la vista extrae el nombre del operario
      y el periodo de trabajo del nombre del PDF cargado y comprueba si existe
      un WorkOrder de la misma empresa con el mismo operario y periodo solapado.
      Si se detecta un duplicado y el POST no incluye confirm_overwrite=1, el
      formulario de carga se vuelve a renderizar con la variable de contexto
      duplicate_wo para que la plantilla muestre un modal de advertencia.
      Si el usuario confirma la sobrescritura, el WorkOrder duplicado (y todos
      sus hijos eliminados en cascada) se elimina antes de crear el nuevo.

    Accesible para los roles SUPERVISOR y ADMIN (SupervisorAccessMixin).
    """

    template_name = "panel/work_orders/upload.html"

    def _get_own_presence(self, company_user):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django.db.models import Q
        from django.utils.timezone import now
        from ivr_config.models import PresenceStatus
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

    def get(self, request):
        """
        Renders the PDF upload form.
        ---
        Renderiza el formulario de carga de PDF.
        """
        company_user = request.user.company_user
        return render(request, self.template_name, {
            "company":      company_user.company,
            "company_user": company_user,
            "own_presence":  self._get_own_presence(company_user),
            "active_nav":    "work_orders",
        })

    def post(self, request):
        """
        Processes the uploaded PDF: validates the file, computes its SHA-256
        hash, runs a two-level duplicate detection check, optionally deletes
        the existing duplicate WorkOrder on confirmed overwrite, creates a new
        WorkOrder (storing the hash) and enqueues the Celery processing task.

        Duplicate detection — two levels (Hito 8 / Bloque I):
          LEVEL 1 — Exact hash match:
            SHA-256 of the incoming file is compared against source_pdf_hash
            for all WorkOrders of the same company. A hash match means the
            exact same file has been uploaded before, regardless of filename.
          LEVEL 2 — Worker + period overlap (only if no hash match):
            The incoming PDF filename is used to derive the worker name and,
            when possible, the work period. Existing WorkOrderEntry records for
            the same company + worker_name + overlapping work_date range are
            queried. A match here means a different file covering the same
            data has already been processed.

          duplicate_reason carries "exact" or "content" so the template can
          show a differentiated warning message in the modal.

          On confirmed overwrite the duplicate WorkOrder (and all its cascade-
          deleted children) is removed before the new one is created.
        ---
        Procesa el PDF cargado: valida el archivo, calcula su hash SHA-256,
        ejecuta la detección de duplicado en dos niveles, elimina opcionalmente
        el WorkOrder duplicado si el usuario confirma la sobrescritura, crea
        un nuevo WorkOrder (guardando el hash) y encola la tarea Celery.

        Detección de duplicado — dos niveles (Hito 8 / Bloque I):
          NIVEL 1 — Hash exacto:
            El SHA-256 del fichero entrante se compara contra source_pdf_hash
            de todos los WorkOrders de la misma empresa. Un match de hash
            significa que se ha subido exactamente el mismo fichero antes,
            con independencia del nombre.
          NIVEL 2 — Operario + solapamiento de periodo (solo si no hay hash match):
            El nombre del PDF se usa para derivar el nombre del operario y,
            cuando es posible, el periodo de trabajo. Se consultan los registros
            WorkOrderEntry de la misma empresa + worker_name + rango work_date
            solapado. Un match aquí significa que un fichero diferente pero con
            los mismos datos ya ha sido procesado.

          duplicate_reason transporta "exact" o "content" para que la plantilla
          muestre un mensaje diferenciado en el modal.

          Al confirmar la sobrescritura el WorkOrder duplicado (y todos sus hijos
          eliminados en cascada) se elimina antes de crear el nuevo.
        """
        import hashlib

        from django.contrib import messages as django_messages
        from work_order_processor.services import _worker_name_from_pdf_path
        from work_order_processor.tasks import _extract_period_from_pdf_name
        from work_order_processor.models import WorkOrderEntry

        company_user = request.user.company_user
        company      = company_user.company
        pdf_file     = request.FILES.get("source_pdf")

        # ------------------------------------------------------------------
        # Step 1 — File presence and extension validation.
        # Paso 1 — Validación de presencia y extensión del archivo.
        # ------------------------------------------------------------------
        if not pdf_file:
            django_messages.error(request, "Debes seleccionar un archivo PDF.")
            return render(request, self.template_name, {
                "company":      company,
                "company_user": company_user,
                "own_presence": self._get_own_presence(company_user),
                "active_nav":   "work_orders",
            })

        if not pdf_file.name.lower().endswith(".pdf"):
            django_messages.error(request, "El archivo debe tener extensión .pdf.")
            return render(request, self.template_name, {
                "company":      company,
                "company_user": company_user,
                "own_presence": self._get_own_presence(company_user),
                "active_nav":   "work_orders",
            })

        # ------------------------------------------------------------------
        # Step 2 — SHA-256 hash computation (Bloque I).
        # Paso 2 — Cálculo del hash SHA-256 (Bloque I).
        #
        # The file pointer is reset to 0 after reading so that Django's
        # storage backend can still save the file in Step 4.
        # El puntero del fichero se resetea a 0 tras la lectura para que el
        # backend de almacenamiento de Django pueda guardar el fichero en el
        # Paso 4.
        # ------------------------------------------------------------------
        pdf_file.seek(0)
        incoming_hash = hashlib.sha256(pdf_file.read()).hexdigest()
        pdf_file.seek(0)

        # ------------------------------------------------------------------
        # Step 3 — Two-level duplicate detection (Bloque I).
        # Paso 3 — Detección de duplicado en dos niveles (Bloque I).
        #
        # Level 1: exact file hash match across WorkOrders of the same company.
        # Level 2: worker_name + work_date overlap via WorkOrderEntry records,
        #          only evaluated when Level 1 produces no match.
        #
        # Nivel 1: match exacto de hash entre WorkOrders de la misma empresa.
        # Nivel 2: solapamiento worker_name + work_date via WorkOrderEntry,
        #          evaluado únicamente cuando el Nivel 1 no produce coincidencia.
        # ------------------------------------------------------------------
        incoming_name   = pdf_file.name
        incoming_worker = _worker_name_from_pdf_path(incoming_name)
        date_from, date_to = _extract_period_from_pdf_name(incoming_name)

        duplicate_wo     = None
        duplicate_reason = None

        # -- Level 1: exact SHA-256 hash match. --
        # -- Nivel 1: match exacto de hash SHA-256. --
        hash_duplicate = (
            WorkOrder.objects
            .filter(company=company, source_pdf_hash=incoming_hash)
            .exclude(source_pdf_hash="")
            .first()
        )
        if hash_duplicate:
            duplicate_wo     = hash_duplicate
            duplicate_reason = "exact"

        # -- Level 2: worker_name + period overlap (only if Level 1 missed). --
        # -- Nivel 2: solapamiento operario + periodo (solo si Nivel 1 no coincidió). --
        if not duplicate_wo and incoming_worker:
            entry_qs = WorkOrderEntry.objects.filter(
                work_order__company=company,
                worker_name=incoming_worker,
            ).select_related("work_order")

            if date_from and date_to:
                # Tighter check: entries whose work_date falls within the
                # incoming period [date_from, date_to] (inclusive).
                # Comprobación ajustada: entradas cuya work_date cae dentro
                # del periodo entrante [date_from, date_to] (inclusive).
                entry_qs = entry_qs.filter(
                    work_date__gte=date_from,
                    work_date__lte=date_to,
                )
            # else: period unknown — any entry for this worker is a match.
            # else: periodo desconocido — cualquier entrada del operario es match.

            existing_entry = entry_qs.first()
            if existing_entry:
                duplicate_wo     = existing_entry.work_order
                duplicate_reason = "content"

        # -- Level 3: concrete work_date overlap within the extracted period. --
        # -- Nivel 3: solapamiento de work_date concretas dentro del periodo extraído. --
        # Only evaluated when Levels 1 and 2 produced no match, incoming_worker
        # is known and date_from / date_to were successfully parsed from the filename.
        # Solo se evalúa cuando los Niveles 1 y 2 no produjeron coincidencia, se conoce
        # incoming_worker y date_from / date_to se parsearon correctamente del nombre.
        if not duplicate_wo and incoming_worker and date_from and date_to:
            conflicting_entries = (
                WorkOrderEntry.objects
                .filter(
                    work_order__company=company,
                    worker_name=incoming_worker,
                    work_date__gte=date_from,
                    work_date__lte=date_to,
                )
                .exclude(work_order__source_pdf_hash=incoming_hash)
                .exclude(work_order__source_pdf_hash="")
                .select_related("work_order")
                .order_by("work_date")
            )
            if conflicting_entries.exists():
                # Build deduplicated list of concrete conflict dates for the modal.
                # Construir lista deduplicada de fechas concretas conflictivas para el modal.
                seen_dates   = set()
                duplicate_dates = []
                for entry in conflicting_entries:
                    if entry.work_date:
                        date_key = entry.work_date.strftime("%d/%m/%y")
                        if date_key not in seen_dates:
                            seen_dates.add(date_key)
                            duplicate_dates.append(date_key)

                first_entry      = conflicting_entries.first()
                duplicate_wo     = first_entry.work_order
                duplicate_reason = "duplicate_entries"

        # If a duplicate was found and overwrite not yet confirmed, re-render
        # the upload form so the template shows the differentiated modal.
        # Si se detectó un duplicado y no se ha confirmado sobrescritura,
        # volver a renderizar el formulario con el contexto del modal diferenciado.
        if duplicate_wo and not request.POST.get("confirm_overwrite"):
            ctx = {
                "company":          company,
                "company_user":     company_user,
                "own_presence":     self._get_own_presence(company_user),
                "active_nav":       "work_orders",
                "duplicate_wo":     duplicate_wo,
                "duplicate_reason": duplicate_reason,
                "pdf_file_name":    incoming_name,
            }
            # Pass duplicate_dates only when reason is duplicate_entries.
            # Pasar duplicate_dates solo cuando el motivo es duplicate_entries.
            if duplicate_reason == "duplicate_entries":
                ctx["duplicate_dates"] = duplicate_dates
            return render(request, self.template_name, ctx)

        # On confirmed overwrite: delete the duplicate and all cascade children.
        # Al confirmar sobrescritura: eliminar el duplicado y sus hijos en cascada.
        if duplicate_wo and request.POST.get("confirm_overwrite"):
            dup_pk = duplicate_wo.pk
            duplicate_wo.delete()
            django_messages.warning(
                request,
                f"El parte duplicado #{dup_pk} y todos sus datos han sido "
                f"eliminados. Procesando el nuevo PDF."
            )

        # ------------------------------------------------------------------
        # Step 4 — Create WorkOrder, store hash, enqueue Celery task.
        # Paso 4 — Crear WorkOrder, guardar hash, encolar tarea Celery.
        #
        # The creation is wrapped in an atomic block with select_for_update
        # to close the race-condition window that allowed two concurrent
        # POSTs of the same file to bypass Level 1 and create duplicate
        # WorkOrders. select_for_update acquires a row-level lock on any
        # existing WorkOrder with the same hash before the INSERT, so a
        # second concurrent request will block until the first commits.
        # If the lock reveals an existing record the second request aborts
        # the creation and redirects to the list with an informational message.
        #
        # La creación se envuelve en un bloque atómico con select_for_update
        # para cerrar la ventana de race condition que permitía que dos POSTs
        # concurrentes del mismo fichero eludieran el Nivel 1 y crearan
        # WorkOrders duplicados. select_for_update adquiere un bloqueo a
        # nivel de fila sobre cualquier WorkOrder existente con el mismo hash
        # antes del INSERT, de modo que una segunda petición concurrente
        # queda bloqueada hasta que la primera hace commit. Si el bloqueo
        # revela un registro existente, la segunda petición aborta la
        # creación y redirige a la lista con un mensaje informativo.
        # ------------------------------------------------------------------
        from django.db import transaction

        with transaction.atomic():
            # Re-check for hash duplicate inside the lock to eliminate the
            # race-condition window between the pre-check (Level 1) and the
            # INSERT. select_for_update serialises concurrent requests on the
            # same hash.
            #
            # Recomprobar duplicado de hash dentro del bloqueo para eliminar
            # la ventana de race condition entre la pre-comprobación (Nivel 1)
            # y el INSERT. select_for_update serializa las peticiones
            # concurrentes sobre el mismo hash.
            race_duplicate = (
                WorkOrder.objects
                .filter(company=company, source_pdf_hash=incoming_hash)
                .exclude(source_pdf_hash="")
                .select_for_update()
                .first()
            )
            if race_duplicate:
                django_messages.info(
                    request,
                    f"El fichero ya había sido registrado como Parte "
                    f"#{race_duplicate.pk}. No se ha creado un duplicado."
                )
                return redirect("panel:work_order_list")

            work_order = WorkOrder.objects.create(
                company         = company,
                uploaded_by     = company_user,
                source_pdf      = pdf_file,
                source_pdf_hash = incoming_hash,
            )

        process_work_order_pdf.delay_on_commit(work_order.pk)

        django_messages.success(
            request,
            f"PDF cargado correctamente (Parte #{work_order.pk}). "
            f"El procesamiento ha sido encolado y comenzará en instantes."
        )
        return redirect("panel:work_order_list")


class WorkOrderEditView(AdminRoleRequiredMixin, View):
    """
    Displays and processes inline edits for all WorkOrderEntryLine records
    belonging to a given WorkOrder. Lines are grouped by their parent
    WorkOrderEntry (page / date) for readability.

    GET  — Renders the editable table grouped by page.
    POST — Two actions dispatched via hidden input `action`:
      "save_line"      : Saves a single WorkOrderEntryLine identified by `line_pk`.
                         Recomputes delta_hours from hc/hf and re-resolves
                         machine_asset from the updated machine_norm.
      "regenerate"     : Re-enqueues the Excel generation task for this WorkOrder
                         (status reset to PENDING) and redirects to the list view.

    Access is restricted to the authenticated company (multicompany guard).
    Restricted to ADMIN role.

    ---

    Muestra y procesa ediciones inline para todos los registros WorkOrderEntryLine
    de un WorkOrder dado. Las líneas se agrupan por su WorkOrderEntry padre
    (página / fecha) para facilitar la lectura.

    GET  — Renderiza la tabla editable agrupada por página.
    POST — Dos acciones despachadas mediante el input oculto `action`:
      "save_line"      : Guarda un único WorkOrderEntryLine identificado por `line_pk`.
                         Recalcula delta_hours desde hc/hf y re-resuelve machine_asset
                         desde el machine_norm actualizado.
      "regenerate"     : Re-encola la tarea de generación de Excel para este WorkOrder
                         (estado reseteado a PENDING) y redirige a la vista de lista.

    El acceso está restringido a la empresa autenticada (guardia multiempresa).
    Restringido al rol ADMIN.
    """

    template_name = "panel/work_orders/edit.html"

    def _get_own_presence(self, company_user):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

    def _get_work_order(self, pk, company):
        """
        Retrieves a WorkOrder scoped to the given company.
        Raises WorkOrder.DoesNotExist if not found or belongs to another company.
        ---
        Recupera un WorkOrder acotado a la empresa dada.
        Lanza WorkOrder.DoesNotExist si no se encuentra o pertenece a otra empresa.
        """
        return WorkOrder.objects.get(pk=pk, company=company)

    def _build_groups(self, work_order):
        """
        Returns a list of dicts grouping WorkOrderEntryLine records by their
        parent WorkOrderEntry, ordered by page number.
        Each dict contains:
          - entry  : WorkOrderEntry instance.
          - lines  : list of WorkOrderEntryLine instances for that entry.

        ---

        Devuelve una lista de dicts que agrupan los registros WorkOrderEntryLine
        por su WorkOrderEntry padre, ordenados por número de página.
        Cada dict contiene:
          - entry  : instancia de WorkOrderEntry.
          - lines  : lista de instancias WorkOrderEntryLine de esa entrada.
        """
        entries = (
            WorkOrderEntry.objects
            .filter(work_order=work_order)
            .prefetch_related("lines__machine_asset")
            .order_by("page_number")
        )
        groups = []
        for entry in entries:
            lines = list(entry.lines.order_by("line_number"))

            # Compute the total worked hours for this entry (day) by summing
            # delta_hours across all its lines. None values are skipped.
            # Used by _entry_group_fragment.html to render the day-total badge.
            #
            # Calcular el total de horas trabajadas en esta entrada (día) sumando
            # delta_hours de todas sus líneas. Los valores None se omiten.
            # Usado por _entry_group_fragment.html para el badge de total de jornada.
            day_total_raw = sum(
                (l.delta_hours for l in lines if l.delta_hours is not None),
                0,
            )
            day_total = round(day_total_raw, 2) if any(
                l.delta_hours is not None for l in lines
            ) else None

            # Determine the CSS modifier class for the day-total badge based on
            # the total hours worked. Four levels defined:
            #   < 8h   → day-total-short   (blue  — incomplete shift)
            #   8-12h  → day-total-normal  (green — normal / moderate overtime)
            #   12-16h → day-total-warning (amber — excessive overtime, review)
            #   > 16h  → day-total-danger  (red   — impossible shift, likely data error)
            #
            # Determinar la clase CSS modificadora del badge de total de jornada según
            # las horas totales trabajadas. Cuatro niveles definidos:
            #   < 8h   → day-total-short   (azul  — jornada incompleta)
            #   8-12h  → day-total-normal  (verde — jornada normal / horas extras moderadas)
            #   12-16h → day-total-warning (ámbar — exceso de extras, revisar)
            #   > 16h  → day-total-danger  (rojo  — jornada imposible, probable error de datos)
            if day_total is None:
                day_css = ""
            elif day_total < 8:
                day_css = "day-total-short"
            elif day_total <= 12:
                day_css = "day-total-normal"
            elif day_total <= 16:
                day_css = "day-total-warning"
            else:
                day_css = "day-total-danger"

            groups.append({
                "entry":     entry,
                "lines":     lines,
                "day_total": day_total,
                "day_css":   day_css,
            })
        return groups

    def get(self, request, pk):
        """
        Renders the inline edit table for the given WorkOrder.
        ---
        Renderiza la tabla de edición inline para el WorkOrder dado.
        """
        from work_order_processor.models import WorkOrderEntry
        company_user = request.user.company_user
        company      = company_user.company

        try:
            work_order = self._get_work_order(pk, company)
        except WorkOrder.DoesNotExist:
            django_messages.error(request, "Parte de trabajo no encontrado.")
            return redirect("panel:work_order_list")

        groups = self._build_groups(work_order)

        # Resolve back URL from optional ?from GET parameter.
        # "taller" — comes from WorkOrderAdminHistoryView (operator parts).
        # Default — returns to the PDF pipeline list (WorkOrderListView).
        #
        # Resolver URL de retorno desde el parámetro GET opcional ?from.
        # "taller" — proviene de WorkOrderAdminHistoryView (partes de operarios).
        # Por defecto — vuelve a la lista del pipeline PDF (WorkOrderListView).
        from_param = request.GET.get("from", "")
        if from_param == "taller":
            from django.urls import reverse
            back_url = reverse("panel:work_order_admin_history") + "?tab=pending"
        else:
            from django.urls import reverse
            back_url = reverse("panel:work_order_list")

        return render(request, self.template_name, {
            "company":      company,
            "company_user": company_user,
            "own_presence": self._get_own_presence(company_user),
            "active_nav":   "work_orders",
            "work_order":   work_order,
            "groups":       groups,
            "back_url":     back_url,
        })

    def post(self, request, pk):
        """
        Dispatches POST actions: save_line or regenerate.
        ---
        Despacha las acciones POST: save_line o regenerate.
        """
        from work_order_processor.models import WorkOrderEntry, WorkOrderEntryLine
        from work_order_processor.services import (
            _compute_delta_hours,
            _normalise_machine_code,
            _resolve_machine_asset,
        )
        from datetime import time as dt_time
        import json

        company_user = request.user.company_user
        company      = company_user.company

        try:
            work_order = self._get_work_order(pk, company)
        except WorkOrder.DoesNotExist:
            django_messages.error(request, "Parte de trabajo no encontrado.")
            return redirect("panel:work_order_list")

        action = request.POST.get("action", "")

        # ------------------------------------------------------------------
        # Action: regenerate Excel
        # Acción: regenerar Excel
        # ------------------------------------------------------------------
        if action == "regenerate":
            work_order.status    = WorkOrder.Status.PENDING
            work_order.excel_file = None
            work_order.error_log  = ""
            work_order.save(update_fields=["status", "excel_file", "error_log"])
            from work_order_processor.services import generate_work_order_excel
            from work_order_processor.tasks import process_work_order_pdf
            generate_work_order_excel(work_order.pk)
            django_messages.success(
                request,
                f"Excel regenerado correctamente para el Parte #{work_order.pk}."
            )
            return redirect("panel:work_order_list")

        # ------------------------------------------------------------------
        # Action: save_line — save a single WorkOrderEntryLine
        # Acción: save_line — guardar un único WorkOrderEntryLine
        # ------------------------------------------------------------------
        if action == "save_line":
            line_pk = request.POST.get("line_pk")
            try:
                line = WorkOrderEntryLine.objects.select_related(
                    "entry__work_order"
                ).get(pk=line_pk, entry__work_order=work_order)
            except WorkOrderEntryLine.DoesNotExist:
                django_messages.error(request, "Línea no encontrada.")
                return redirect("panel:work_order_edit", pk=pk)

            # Parse and update machine_norm + machine_asset.
            # Parsear y actualizar machine_norm + machine_asset.
            raw_norm = request.POST.get("machine_norm", "").strip()
            norm     = _normalise_machine_code(raw_norm) if raw_norm else raw_norm
            asset    = _resolve_machine_asset(norm, company=company) if norm else None

            # Parse hc / hf.
            # Parsear hc / hf.
            def _parse_time_str(val):
                """Parses HH:MM string into time, returns None on failure.
                --- Parsea cadena HH:MM a time, devuelve None si falla."""
                if not val:
                    return None
                try:
                    parts = val.strip().split(":")
                    return dt_time(int(parts[0]), int(parts[1]))
                except (ValueError, IndexError):
                    return None

            hc    = _parse_time_str(request.POST.get("hc", ""))
            hf    = _parse_time_str(request.POST.get("hf", ""))
            delta = _compute_delta_hours(hc, hf)

            # Parse flags from comma-separated string.
            # Parsear flags desde cadena separada por comas.
            flags_raw = request.POST.get("flags", "").strip()
            flags     = [f.strip() for f in flags_raw.split(",") if f.strip()]                         if flags_raw else []

            # Persist changes.
            # Persistir cambios.
            line.machine_norm       = norm
            line.machine_asset      = asset
            line.fault_description  = request.POST.get("fault_description", "").strip()
            line.repair_notes       = request.POST.get("repair_notes", "").strip()
            line.hc                 = hc
            line.hf                 = hf
            line.or_val             = request.POST.get("or_val", "").strip()
            line.delta_hours        = delta
            line.flags              = flags
            line.save(update_fields=[
                "machine_norm", "machine_asset", "fault_description",
                "repair_notes", "hc", "hf", "or_val", "delta_hours", "flags",
            ])

            django_messages.success(
                request,
                f"Bloque {line.line_number} de la página "
                f"{line.entry.page_number} guardado correctamente."
            )
            return redirect("panel:work_order_edit", pk=pk)

        # Unknown action fallback.
        # Fallback para acción desconocida.
        django_messages.warning(request, "Acción no reconocida.")
        return redirect("panel:work_order_edit", pk=pk)



class WorkOrderStatusFragmentView(AdminRoleRequiredMixin, View):
    """
    Returns the HTML status fragment for a single WorkOrder, used by HTMX polling.

    GET /panel/work-orders/<pk>/status/
        Renders only the _status_fragment.html partial for the WorkOrder identified
        by pk and scoped to the authenticated user's company. If the status is
        PENDING or PROCESSING the partial includes HTMX polling attributes so the
        browser continues polling every 4 seconds. When the status reaches DONE or
        ERROR the returned fragment contains no HTMX attributes and polling stops
        automatically.

    Restricted to the ADMIN role (AdminRoleRequiredMixin).

    ---

    Devuelve el fragmento HTML de estado de un WorkOrder, consumido por el polling HTMX.

    GET /panel/work-orders/<pk>/status/
        Renderiza únicamente el parcial _status_fragment.html para el WorkOrder
        identificado por pk, acotado a la empresa del usuario autenticado. Si el
        estado es PENDING o PROCESSING el parcial incluye atributos HTMX de polling
        para que el navegador siga consultando cada 4 segundos. Cuando el estado
        alcanza DONE o ERROR el fragmento devuelto no contiene atributos HTMX y el
        polling se detiene automáticamente.

    Restringido al rol ADMIN (AdminRoleRequiredMixin).
    """

    def get(self, request, pk):
        """
        Returns the rendered _status_fragment.html partial for the requested WorkOrder.
        Raises HTTP 404 if the WorkOrder does not exist or belongs to another company.
        ---
        Devuelve el parcial _status_fragment.html renderizado para el WorkOrder solicitado.
        Lanza HTTP 404 si el WorkOrder no existe o pertenece a otra empresa.
        """
        from django.shortcuts import get_object_or_404

        wo = get_object_or_404(
            WorkOrder,
            pk=pk,
            company=request.user.company_user.company,
        )
        return render(
            request,
            "panel/work_orders/_status_fragment.html",
            {"wo": wo},
        )


class WorkOrderLineSaveView(AdminRoleRequiredMixin, View):
    """
    HTMX endpoint that saves a single WorkOrderEntryLine and returns the updated
    <tr> row as an HTML fragment consumed by the inline editor.

    POST /panel/work-orders/<wo_pk>/lines/<line_pk>/save/
         Expected POST fields (all optional — missing fields are treated as empty):
           machine_norm        : str  — normalised machine code.
           fault_description  : str  — fault description.
           repair_notes          : str  — repair description.
           hc                  : str  — start time  HH:MM.
           hf                  : str  — end time    HH:MM.
           or_val              : str  — repair order reference.
           flags               : str  — comma-separated flag list.
         Server recomputes delta_hours from hc/hf and re-resolves machine_asset
         from the updated machine_norm. Returns the rendered _line_row.html partial
         (a single <tr> element) with HTTP 200.
         Returns HTTP 404 if the WorkOrder or line do not exist or belong to another
         company. Returns HTTP 400 on an unexpected processing error.

    Restricted to the ADMIN role (AdminRoleRequiredMixin).

    ---

    Endpoint HTMX que guarda un único WorkOrderEntryLine y devuelve la fila <tr>
    actualizada como fragmento HTML consumido por el editor inline.

    POST /panel/work-orders/<wo_pk>/lines/<line_pk>/save/
         Campos POST esperados (todos opcionales — los ausentes se tratan como vacíos):
           machine_norm        : str  — código de máquina normalizado.
           fault_description  : str  — descripción de la avería.
           repair_notes          : str  — descripción de la reparación.
           hc                  : str  — hora de comienzo HH:MM.
           hf                  : str  — hora de fin      HH:MM.
           or_val              : str  — referencia de orden de reparación.
           flags               : str  — lista de flags separada por comas.
         El servidor recalcula delta_hours desde hc/hf y re-resuelve machine_asset
         desde el machine_norm actualizado. Devuelve el parcial _line_row.html
         renderizado (un único elemento <tr>) con HTTP 200.
         Devuelve HTTP 404 si el WorkOrder o la línea no existen o pertenecen a
         otra empresa. Devuelve HTTP 400 ante un error de procesamiento inesperado.

    Restringido al rol ADMIN (AdminRoleRequiredMixin).
    """

    def post(self, request, wo_pk, line_pk):
        """
        Saves the WorkOrderEntryLine identified by line_pk, recomputes derived
        fields and returns the updated <tr> row as an HTMX fragment.
        ---
        Guarda el WorkOrderEntryLine identificado por line_pk, recalcula los campos
        derivados y devuelve la fila <tr> actualizada como fragmento HTMX.
        """
        from django.shortcuts import get_object_or_404
        from work_order_processor.models import WorkOrderEntryLine
        from work_order_processor.services import (
            _compute_delta_hours,
            _normalise_machine_code,
            _resolve_machine_asset,
        )
        from datetime import time as dt_time

        # ------------------------------------------------------------------
        # Multicompany guard — retrieve WorkOrder scoped to the company.
        # Guardia multiempresa — recuperar WorkOrder acotado a la empresa.
        # ------------------------------------------------------------------
        company = request.user.company_user.company
        wo = get_object_or_404(WorkOrder, pk=wo_pk, company=company)

        # ------------------------------------------------------------------
        # Retrieve the line, ensuring it belongs to the WorkOrder.
        # Recuperar la línea, asegurando que pertenece al WorkOrder.
        # ------------------------------------------------------------------
        line = get_object_or_404(
            WorkOrderEntryLine.objects.select_related(
                "entry__work_order",
                "machine_asset",
            ),
            pk=line_pk,
            entry__work_order=wo,
        )

        # ------------------------------------------------------------------
        # Parse machine_norm and re-resolve machine_asset.
        # Parsear machine_norm y re-resolver machine_asset.
        # ------------------------------------------------------------------
        raw_norm = request.POST.get("machine_norm", "").strip()
        norm     = _normalise_machine_code(raw_norm) if raw_norm else raw_norm
        asset    = _resolve_machine_asset(norm, company=company) if norm else None

        # ------------------------------------------------------------------
        # Parse hc / hf and recompute delta_hours.
        # Parsear hc / hf y recalcular delta_hours.
        # ------------------------------------------------------------------
        def _parse_time_str(val):
            """Parses HH:MM string into time object, returns None on failure.
            --- Parsea cadena HH:MM a objeto time, devuelve None si falla."""
            if not val:
                return None
            try:
                parts = val.strip().split(":")
                return dt_time(int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                return None

        hc    = _parse_time_str(request.POST.get("hc", ""))
        hf    = _parse_time_str(request.POST.get("hf", ""))
        delta = _compute_delta_hours(hc, hf)

        # ------------------------------------------------------------------
        # Parse flags from comma-separated string.
        # Parsear flags desde cadena separada por comas.
        # ------------------------------------------------------------------
        flags_raw = request.POST.get("flags", "").strip()
        flags     = [f.strip() for f in flags_raw.split(",") if f.strip()]                     if flags_raw else []

        # ------------------------------------------------------------------
        # Persist all changes in a single save call.
        # Persistir todos los cambios en una única llamada save.
        # ------------------------------------------------------------------
        line.machine_norm       = norm
        line.machine_asset      = asset
        line.fault_description = request.POST.get("fault_description", "").strip()
        line.repair_notes         = request.POST.get("repair_notes", "").strip()
        line.hc                 = hc
        line.hf                 = hf
        line.or_val             = request.POST.get("or_val", "").strip()
        line.delta_hours        = delta
        line.flags              = flags
        line.save(update_fields=[
            "machine_norm", "machine_asset", "fault_description",
            "repair_notes", "hc", "hf", "or_val", "delta_hours", "flags",
        ])

        # ------------------------------------------------------------------
        # Return the updated row fragment for HTMX to swap into the DOM.
        # Devolver el fragmento de fila actualizado para que HTMX lo inserte en el DOM.
        # ------------------------------------------------------------------
        return render(
            request,
            "panel/work_orders/_line_row.html",
            {
                "line":       line,
                "wo_pk":      wo.pk,
                "entry":      line.entry,
            },
        )


class WorkOrderLineInsertView(AdminRoleRequiredMixin, View):
    """
    Creates a new empty WorkOrderEntryLine after a given line within the same
    WorkOrderEntry group and returns the new row as an HTMX fragment.

    POST /panel/work-orders/<wo_pk>/lines/insert/
         Expected POST fields:
           after_line_pk : int — pk of the line after which to insert.
           entry_pk      : int — pk of the WorkOrderEntry group.
         Creates a new WorkOrderEntryLine with line_number = after_line.line_number + 1,
         shifting the line_number of all subsequent lines in the same entry up by 1.
         Returns the rendered _line_row.html partial for the new line with HTTP 200.
         Returns HTTP 404 if the WorkOrder, entry or reference line do not belong
         to the authenticated company.

    Restricted to the ADMIN role (AdminRoleRequiredMixin).

    ---

    Crea un nuevo WorkOrderEntryLine vacío tras una línea dada dentro del mismo
    grupo WorkOrderEntry y devuelve la nueva fila como fragmento HTMX.

    POST /panel/work-orders/<wo_pk>/lines/insert/
         Campos POST esperados:
           after_line_pk : int — pk de la línea tras la que insertar.
           entry_pk      : int — pk del grupo WorkOrderEntry.
         Crea un nuevo WorkOrderEntryLine con line_number = after_line.line_number + 1,
         desplazando el line_number de todas las líneas posteriores del mismo entry
         en +1. Devuelve el parcial _line_row.html renderizado para la nueva línea
         con HTTP 200. Devuelve HTTP 404 si el WorkOrder, entry o línea de referencia
         no pertenecen a la empresa autenticada.

    Restringido al rol ADMIN (AdminRoleRequiredMixin).
    """

    def post(self, request, wo_pk):
        """
        Inserts a new empty WorkOrderEntryLine after the specified reference line
        and returns the rendered _line_row.html fragment for the new row.
        ---
        Inserta un nuevo WorkOrderEntryLine vacío tras la línea de referencia
        especificada y devuelve el fragmento _line_row.html renderizado para la fila.
        """
        from django.shortcuts import get_object_or_404
        from django.http import HttpResponseBadRequest

        company = request.user.company_user.company

        # Retrieve and scope WorkOrder.
        # Recuperar y acotar WorkOrder.
        wo = get_object_or_404(WorkOrder, pk=wo_pk, company=company)

        # Validate required POST parameters.
        # Validar parámetros POST obligatorios.
        try:
            after_line_pk = int(request.POST.get("after_line_pk", ""))
            entry_pk      = int(request.POST.get("entry_pk", ""))
        except (TypeError, ValueError):
            return HttpResponseBadRequest("# [INSERT] Parámetros after_line_pk / entry_pk inválidos.")

        # Retrieve the reference line and its entry, scoped to this WorkOrder.
        # Recuperar la línea de referencia y su entry, acotados a este WorkOrder.
        after_line = get_object_or_404(
            WorkOrderEntryLine,
            pk=after_line_pk,
            entry__work_order=wo,
            entry__pk=entry_pk,
        )
        entry = after_line.entry

        # Shift + create must be atomic to prevent unique constraint violation
        # on (entry_id, line_number) when two lines share the same number
        # during the gap between UPDATE and INSERT.
        # Shift + create deben ser atómicos para evitar violación de restricción
        # única en (entry_id, line_number) cuando dos líneas comparten el mismo
        # número durante el intervalo entre UPDATE e INSERT.
        from django.db import transaction
        with transaction.atomic():
            # Shift all lines with line_number > after_line.line_number up by 1.
            # Desplazar todas las líneas con line_number > after_line.line_number en +1.
            WorkOrderEntryLine.objects.filter(
                entry=entry,
                line_number__gt=after_line.line_number,
            ).update(line_number=django_models.F("line_number") + 1)

            # Create the new empty line at the freed position.
            # Crear la nueva línea vacía en la posición liberada.
            new_line = WorkOrderEntryLine.objects.create(
                entry=entry,
                line_number=after_line.line_number + 1,
                machine_norm="",
                machine_raw="",
                fault_description="",
                repair_notes="",
                hc=None,
                hf=None,
                or_val="",
                delta_hours=None,
                flags=[],
                machine_asset=None,
            )

        return render(
            request,
            "panel/work_orders/_line_row.html",
            {
                "line":  new_line,
                "wo_pk": wo.pk,
                "entry": entry,
            },
        )


class WorkOrderLineReorderView(AdminRoleRequiredMixin, View):
    """
    Accepts a new ordering for WorkOrderEntryLine records within a single
    WorkOrderEntry group and persists the updated line_number values.

    POST /panel/work-orders/<wo_pk>/lines/reorder/
         Expected POST fields:
           entry_pk        : int         — pk of the WorkOrderEntry group.
           line_pks[]      : list[int]   — ordered list of WorkOrderEntryLine pks
                                           in the desired new order.
         Updates line_number for each line to match the position in line_pks[].
         Returns HTTP 200 with JSON {"ok": true} on success.
         Returns HTTP 400 on invalid parameters.
         Returns HTTP 404 if the WorkOrder or entry do not belong to the company.

    Restricted to the ADMIN role (AdminRoleRequiredMixin).

    ---

    Acepta un nuevo orden para los registros WorkOrderEntryLine dentro de un único
    grupo WorkOrderEntry y persiste los valores line_number actualizados.

    POST /panel/work-orders/<wo_pk>/lines/reorder/
         Campos POST esperados:
           entry_pk        : int         — pk del grupo WorkOrderEntry.
           line_pks[]      : list[int]   — lista ordenada de pks de WorkOrderEntryLine
                                           en el nuevo orden deseado.
         Actualiza line_number de cada línea para que coincida con su posición en
         line_pks[]. Devuelve HTTP 200 con JSON {"ok": true} en caso de éxito.
         Devuelve HTTP 400 ante parámetros inválidos. Devuelve HTTP 404 si el
         WorkOrder o entry no pertenecen a la empresa.

    Restringido al rol ADMIN (AdminRoleRequiredMixin).
    """

    def post(self, request, wo_pk):
        """
        Persists the new line_number ordering for the lines of a WorkOrderEntry.
        ---
        Persiste el nuevo orden de line_number para las líneas de un WorkOrderEntry.
        """
        from django.shortcuts import get_object_or_404
        from django.http import JsonResponse, HttpResponseBadRequest

        company = request.user.company_user.company
        wo      = get_object_or_404(WorkOrder, pk=wo_pk, company=company)

        # Validate entry_pk.
        # Validar entry_pk.
        try:
            entry_pk = int(request.POST.get("entry_pk", ""))
        except (TypeError, ValueError):
            return HttpResponseBadRequest("# [REORDER] Parámetro entry_pk inválido.")

        entry = get_object_or_404(WorkOrderEntry, pk=entry_pk, work_order=wo)

        # Retrieve ordered list of line pks from POST (getlist for multi-value).
        # Recuperar la lista ordenada de pks de línea del POST (getlist para multi-valor).
        try:
            line_pks = [int(pk) for pk in request.POST.getlist("line_pks[]")]
        except (TypeError, ValueError):
            return HttpResponseBadRequest("# [REORDER] Parámetro line_pks[] inválido.")

        if not line_pks:
            return HttpResponseBadRequest("# [REORDER] Lista line_pks[] vacía.")

        # Fetch all lines of the entry as a dict for O(1) lookup.
        # Obtener todas las líneas del entry como dict para búsqueda O(1).
        lines_map = {
            line.pk: line
            for line in WorkOrderEntryLine.objects.filter(entry=entry)
        }

        # Assign new line_number values according to the received order.
        # Asignar nuevos valores de line_number según el orden recibido.
        bulk_update = []
        for position, pk in enumerate(line_pks, start=1):
            line = lines_map.get(pk)
            if line is None:
                continue
            line.line_number = position
            bulk_update.append(line)

        WorkOrderEntryLine.objects.bulk_update(bulk_update, ["line_number"])

        return JsonResponse({"ok": True})


class WorkOrderLineRestoreView(AdminRoleRequiredMixin, View):
    """
    Restores a single WorkOrderEntryLine to its original Gemini-extracted
    values by looking up the corresponding block in the parent WorkOrderEntry's
    raw_gemini_response using the line's line_number as the index.

    POST /panel/work-orders/<wo_pk>/lines/<line_pk>/restore/
         Locates the bloque at raw_gemini_response["entradas"][line_number - 1],
         overwrites only the fields of the target line (machine_raw, machine_norm,
         machine_asset, fault_description, repair_notes, hc, hf, or_val,
         delta_hours, flags) and returns the rendered _line_row.html partial
         for that single row with HTTP 200.
         Returns HTTP 404 if the WorkOrder or line do not belong to the company.
         Returns HTTP 400 if no raw_gemini_response is stored or the block index
         is out of range.

    Restricted to the ADMIN role (AdminRoleRequiredMixin).

    ---

    Restaura un único WorkOrderEntryLine a sus valores originales extraídos por
    Gemini localizando el bloque correspondiente en el raw_gemini_response del
    WorkOrderEntry padre usando el line_number de la línea como índice.

    POST /panel/work-orders/<wo_pk>/lines/<line_pk>/restore/
         Localiza el bloque en raw_gemini_response["entradas"][line_number - 1],
         sobreescribe únicamente los campos de la línea objetivo (machine_raw,
         machine_norm, machine_asset, fault_description, repair_notes, hc, hf,
         or_val, delta_hours, flags) y devuelve el parcial _line_row.html
         renderizado para esa única fila con HTTP 200.
         Devuelve HTTP 404 si el WorkOrder o la línea no pertenecen a la empresa.
         Devuelve HTTP 400 si no hay raw_gemini_response almacenado o el índice
         de bloque está fuera de rango.

    Restringido al rol ADMIN (AdminRoleRequiredMixin).
    """

    def post(self, request, wo_pk, line_pk):
        """
        Restores the single WorkOrderEntryLine identified by line_pk from its
        corresponding block in raw_gemini_response and returns the updated row
        as an HTMX fragment.
        ---
        Restaura el único WorkOrderEntryLine identificado por line_pk desde su
        bloque correspondiente en raw_gemini_response y devuelve la fila
        actualizada como fragmento HTMX.
        """
        from django.shortcuts import get_object_or_404
        from django.http import HttpResponseBadRequest
        from work_order_processor.services import (
            _normalise_machine_code,
            _resolve_machine_asset,
            _compute_delta_hours,
            _parse_time,
        )

        company = request.user.company_user.company
        wo      = get_object_or_404(WorkOrder, pk=wo_pk, company=company)

        # Retrieve the line and its parent entry.
        # Recuperar la línea y su entry padre.
        line  = get_object_or_404(
            WorkOrderEntryLine.objects.select_related("entry", "machine_asset"),
            pk=line_pk,
            entry__work_order=wo,
        )
        entry = line.entry

        # Guard: raw_gemini_response must exist for Gemini-sourced work orders.
        # For digital work orders (Via A/B/C confirm) raw_gemini_response is None —
        # in that case restore re-resolves machine_asset from the stored machine_norm
        # and recomputes delta_hours from the stored hc/hf, preserving all other fields.
        #
        # Guardia: raw_gemini_response debe existir para partes con origen Gemini.
        # Para partes digitales (Vía A/B/C confirm) raw_gemini_response es None —
        # en ese caso el restore re-resuelve machine_asset desde machine_norm almacenado
        # y recalcula delta_hours desde hc/hf almacenados, preservando el resto.
        raw = entry.raw_gemini_response

        if not raw or not isinstance(raw, dict):
            # Digital work order path — re-resolve asset and recompute hours only.
            # Ruta de parte digital — re-resolver activo y recalcular horas únicamente.
            machine_norm  = _normalise_machine_code(line.machine_raw or "")
            machine_asset = _resolve_machine_asset(machine_norm, company=company) if machine_norm else None
            delta         = _compute_delta_hours(line.hc, line.hf)

            line.machine_norm  = machine_norm
            line.machine_asset = machine_asset
            line.delta_hours   = delta
            line.save(update_fields=["machine_norm", "machine_asset", "delta_hours"])

            return render(
                request,
                "panel/work_orders/_line_row.html",
                {
                    "line":  line,
                    "wo_pk": wo.pk,
                    "entry": entry,
                },
            )

        # Gemini-sourced path — restore from raw_gemini_response block.
        # Ruta con origen Gemini — restaurar desde bloque raw_gemini_response.
        entradas    = raw.get("entradas") or []
        block_index = line.line_number - 1   # line_number is 1-based.

        if block_index < 0 or block_index >= len(entradas):
            return HttpResponseBadRequest(
                f"# [RESTORE] Índice de bloque {block_index} fuera de rango "
                f"(entradas disponibles: {len(entradas)})."
            )

        bloque = entradas[block_index]

        # Re-parse the original block values and overwrite only this line.
        # Re-parsear los valores del bloque original y sobreescribir solo esta línea.
        machine_raw   = (bloque.get("machine_raw") or "").strip()
        machine_norm  = _normalise_machine_code(machine_raw)
        machine_asset = _resolve_machine_asset(machine_norm, company=company)
        hc            = _parse_time(bloque.get("hc"))
        hf            = _parse_time(bloque.get("hf"))
        delta         = _compute_delta_hours(hc, hf)
        flags         = bloque.get("flags") or []
        if not isinstance(flags, list):
            flags = []

        line.machine_raw        = machine_raw
        line.machine_norm       = machine_norm
        line.machine_asset      = machine_asset
        line.fault_description = (bloque.get("fault_description") or "")
        line.repair_notes         = (bloque.get("repair_notes") or "")
        line.hc                 = hc
        line.hf                 = hf
        line.or_val             = (bloque.get("or_val") or "")
        line.delta_hours        = delta
        line.flags              = flags
        line.save(update_fields=[
            "machine_raw", "machine_norm", "machine_asset",
            "fault_description", "repair_notes", "hc", "hf",
            "or_val", "delta_hours", "flags",
        ])

        return render(
            request,
            "panel/work_orders/_line_row.html",
            {
                "line":  line,
                "wo_pk": wo.pk,
                "entry": entry,
            },
        )


class WorkOrderLineDeleteView(AdminRoleRequiredMixin, View):
    """
    Deletes a single WorkOrderEntryLine identified by line_pk, scoped to the
    authenticated company. Returns an empty HTTP 200 response so that HTMX
    removes the <tr> row from the DOM via hx-swap="outerHTML" with an empty
    response body.

    POST /panel/work-orders/<wo_pk>/lines/<line_pk>/delete/
         Returns HTTP 404 if the WorkOrder or line do not exist or belong to
         another company. Restricted to ADMIN role.

    ---

    Elimina un único WorkOrderEntryLine identificado por line_pk, acotado a la
    empresa autenticada. Devuelve una respuesta HTTP 200 vacía para que HTMX
    elimine la fila <tr> del DOM via hx-swap="outerHTML" con cuerpo vacío.

    POST /panel/work-orders/<wo_pk>/lines/<line_pk>/delete/
         Devuelve HTTP 404 si el WorkOrder o la línea no existen o pertenecen a
         otra empresa. Restringido al rol ADMIN.
    """

    def post(self, request, wo_pk, line_pk):
        """
        Deletes the WorkOrderEntryLine identified by line_pk and returns an
        empty response for HTMX to remove the row from the DOM.
        ---
        Elimina el WorkOrderEntryLine identificado por line_pk y devuelve una
        respuesta vacía para que HTMX elimine la fila del DOM.
        """
        from django.shortcuts import get_object_or_404
        from django.http import HttpResponse

        company = request.user.company_user.company
        wo      = get_object_or_404(WorkOrder, pk=wo_pk, company=company)
        line    = get_object_or_404(
            WorkOrderEntryLine,
            pk=line_pk,
            entry__work_order=wo,
        )
        line.delete()
        # Return empty body — HTMX replaces the <tr> with nothing (outerHTML swap).
        # Devolver cuerpo vacío — HTMX reemplaza el <tr> con nada (swap outerHTML).
        return HttpResponse("")


class WorkOrderDeleteView(AdminRoleRequiredMixin, View):
    """
    Deletes a WorkOrder and all its cascade-deleted children (WorkOrderEntry,
    WorkOrderEntryLine, source PDF file, Excel file) scoped to the authenticated
    company. Redirects to the work order list on success.

    POST /panel/work-orders/<pk>/delete/
         Returns HTTP 404 if the WorkOrder does not exist or belongs to another
         company. Restricted to ADMIN role.

    ---

    Elimina un WorkOrder y todos sus hijos eliminados en cascada (WorkOrderEntry,
    WorkOrderEntryLine, PDF original, archivo Excel) acotado a la empresa
    autenticada. Redirige a la lista de partes tras el éxito.

    POST /panel/work-orders/<pk>/delete/
         Devuelve HTTP 404 si el WorkOrder no existe o pertenece a otra empresa.
         Restringido al rol ADMIN.
    """

    def post(self, request, pk):
        """
        Deletes the WorkOrder identified by pk, scoped to the authenticated company.
        ---
        Elimina el WorkOrder identificado por pk, acotado a la empresa autenticada.
        """
        from django.shortcuts import get_object_or_404

        company = request.user.company_user.company
        wo      = get_object_or_404(WorkOrder, pk=pk, company=company)
        wo_pk   = wo.pk
        wo.delete()
        django_messages.success(
            request,
            f"Parte #{wo_pk} eliminado correctamente."
        )
        return redirect("panel:work_order_list")


class WorkOrderMarkReviewedView(SupervisorAccessMixin, View):
    """
    Toggles the reviewed flag on a WorkOrder identified by pk, scoped to the
    authenticated company. Returns an HTML fragment (_review_badge_fragment.html)
    for HTMX to swap inline in list.html.

    POST /panel/work-orders/<pk>/review/
         If reviewed is currently False:
           Sets reviewed=True, reviewed_by=request.user.company_user,
           reviewed_at=now().
         If reviewed is currently True:
           Sets reviewed=False, reviewed_by=None, reviewed_at=None.
         Returns the rendered _review_badge_fragment.html partial with HTTP 200.
         Returns HTTP 404 if the WorkOrder does not exist or belongs to another
         company.

    Accessible to SUPERVISOR and ADMIN roles (SupervisorAccessMixin).

    ---

    Alterna el flag reviewed de un WorkOrder identificado por pk, acotado a la
    empresa autenticada. Devuelve un fragmento HTML (_review_badge_fragment.html)
    para que HTMX lo intercambie inline en list.html.

    POST /panel/work-orders/<pk>/review/
         Si reviewed es actualmente False:
           Establece reviewed=True, reviewed_by=request.user.company_user,
           reviewed_at=now().
         Si reviewed es actualmente True:
           Establece reviewed=False, reviewed_by=None, reviewed_at=None.
         Devuelve el parcial _review_badge_fragment.html renderizado con HTTP 200.
         Devuelve HTTP 404 si el WorkOrder no existe o pertenece a otra empresa.

    Accesible para los roles SUPERVISOR y ADMIN (SupervisorAccessMixin).
    """

    def post(self, request, pk):
        """
        Toggles reviewed on the WorkOrder identified by pk and returns the
        rendered review badge fragment for HTMX inline swap.
        ---
        Alterna reviewed en el WorkOrder identificado por pk y devuelve el
        fragmento del badge de revisión para el intercambio inline de HTMX.
        """
        from django.shortcuts import get_object_or_404
        from django.utils.timezone import now as tz_now

        company      = request.user.company_user.company
        company_user = request.user.company_user

        wo = get_object_or_404(WorkOrder, pk=pk, company=company)

        if wo.reviewed:
            # Unmark: clear all review fields.
            # Desmarcar: limpiar todos los campos de revisión.
            wo.reviewed     = False
            wo.reviewed_by  = None
            wo.reviewed_at  = None
            wo.save(update_fields=["reviewed", "reviewed_by", "reviewed_at"])
        else:
            # Mark: set reviewer and timestamp.
            # Marcar: establecer revisor y timestamp.
            wo.reviewed    = True
            wo.reviewed_by = company_user
            wo.reviewed_at = tz_now()
            wo.save(update_fields=["reviewed", "reviewed_by", "reviewed_at"])

        return render(
            request,
            "panel/work_orders/_review_badge_fragment.html",
            {"wo": wo},
        )


class WorkOrderExportView(SupervisorAccessMixin, View):
    """
    Generates and returns a multi-sheet Excel file concatenating the individual
    Excel reports of a selection of WorkOrder records identified by their pks.

    POST /panel/work-orders/export/
         Expected POST fields:
           pks         : list[int] (repeating field "pks") — primary keys of the
                         WorkOrder records to include. Only DONE records belonging
                         to the authenticated company are exported.
           export_mode : str — "single_sheet" or "multi_sheet" (Hito 8 / Bloque H).
                         single_sheet: one sheet with all entries ordered by
                           worker_name then date_key; an opaque header row marks
                           each new worker block.
                         multi_sheet: one sheet per worker with individual header.
         Returns HTTP 400 if no valid pks are provided.
         Returns HTTP 404 if the authenticated user has no CompanyUser profile.

    Accessible to SUPERVISOR and ADMIN roles (SupervisorAccessMixin).

    ---

    Genera y devuelve un archivo Excel multi-hoja que concatena los informes
    individuales de una selección de registros WorkOrder identificados por sus pks.

    POST /panel/work-orders/export/
         Campos POST esperados:
           pks         : list[int] (campo repetido "pks") — claves primarias de
                         los WorkOrder a incluir. Solo se exportan DONE de la empresa.
           export_mode : str — "single_sheet" o "multi_sheet" (Hito 8 / Bloque H).
                         single_sheet: una sola hoja con todas las entradas ordenadas
                           por operario y fecha; una fila cabecera separadora por
                           cada nuevo operario.
                         multi_sheet: una hoja por operario con su membrete.
         Devuelve HTTP 400 si no se proporcionan pks válidos.
         Devuelve HTTP 404 si el usuario no tiene perfil CompanyUser.

    Accesible para los roles SUPERVISOR y ADMIN (SupervisorAccessMixin).
    """

    def post(self, request):
        """
        Builds the export Excel file from the selected WorkOrder pks.
        Supports two export modes controlled by the POST field export_mode:

          single_sheet — One flat sheet with all WorkOrderEntryLine records
            from all selected WorkOrders, grouped first by worker_name then
            by work_date. A dark-blue separator row bearing the worker name
            is inserted before the first block of each new worker. All data
            is read directly from the DB — no Excel regeneration is triggered.

          multi_sheet  — One sheet per distinct worker_name. Each sheet is
            built by copying the first sheet of the individual Excel stored
            in WorkOrder.excel_file (regenerated on-the-fly if missing).
            Sheet title is truncated to 31 characters (Excel limit).

        Both modes return an HttpResponse with Content-Disposition attachment.
        Returns HTTP 400 on invalid or missing pks or on unknown export_mode.

        ---

        Construye el Excel de exportación a partir de los pks de WorkOrder
        seleccionados. Soporta dos modos controlados por el campo POST
        export_mode:

          single_sheet — Una hoja plana con todos los WorkOrderEntryLine de
            todos los WorkOrders seleccionados, agrupados por worker_name y
            después por work_date. Una fila separadora azul oscuro con el
            nombre del operario se inserta antes del primer bloque de cada
            nuevo operario. Los datos se leen directamente de la BD — no se
            regenera ningún Excel individual.

          multi_sheet  — Una hoja por worker_name distinto. Cada hoja se
            construye copiando la primera hoja del Excel individual almacenado
            en WorkOrder.excel_file (regenerado al vuelo si falta).
            El título de hoja se trunca a 31 caracteres (límite de Excel).

        Ambos modos devuelven HttpResponse con Content-Disposition attachment.
        Devuelve HTTP 400 ante pks inválidos/ausentes o export_mode desconocido.
        """
        import io
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
        from django.http import HttpResponse, HttpResponseBadRequest
        from django.utils.timezone import now as tz_now
        from work_order_processor.models import WorkOrderEntry, WorkOrderEntryLine
        from work_order_processor.services import (
            generate_work_order_excel as _gen_excel,
            _worker_name_from_pdf_path,
        )

        company     = request.user.company_user.company
        export_mode = request.POST.get("export_mode", "single_sheet").strip()

        # ------------------------------------------------------------------
        # Validate export_mode.
        # Validar export_mode.
        # ------------------------------------------------------------------
        if export_mode not in ("single_sheet", "multi_sheet"):
            return HttpResponseBadRequest(
                f"# [EXPORT] Modo de exportación desconocido: {export_mode!r}."
            )

        # ------------------------------------------------------------------
        # Collect and validate requested pks.
        # Recopilar y validar los pks solicitados.
        # ------------------------------------------------------------------
        raw_pks = request.POST.getlist("pks")
        try:
            pk_list = [int(pk) for pk in raw_pks if pk]
        except (ValueError, TypeError):
            return HttpResponseBadRequest("# [EXPORT] Parámetros pks inválidos.")

        if not pk_list:
            return HttpResponseBadRequest(
                "# [EXPORT] No se han seleccionado partes para exportar."
            )

        # Retrieve DONE + reviewed WorkOrders scoped to the company.
        # Directriz de negocio (Alejandro): solo se pueden exportar partes
        # que hayan sido revisados previamente por un Supervisor o Admin.
        # Retrieve DONE + reviewed WorkOrders scoped to the company.
        # Business rule (Alejandro): only WorkOrders that have been reviewed
        # by a Supervisor or Admin may be exported to Excel.
        work_orders = list(
            WorkOrder.objects
            .filter(
                pk__in=pk_list,
                company=company,
                status=WorkOrder.Status.DONE,
                reviewed=True,
            )
            .order_by("pk")
        )

        if not work_orders:
            return HttpResponseBadRequest(
                "# [EXPORT] Ninguno de los partes seleccionados está revisado y en estado DONE. "
                "Solo se pueden exportar partes marcados como revisados."
            )

        # ------------------------------------------------------------------
        # Helper — copy one openpyxl sheet into a destination workbook.
        # Auxiliar — copiar una hoja openpyxl en un libro destino.
        # ------------------------------------------------------------------
        def _copy_sheet(src_sheet, dest_wb, title):
            """
            Copies src_sheet (cells, styles, column widths, row heights) into
            a new sheet named title in dest_wb.
            ---
            Copia src_sheet (celdas, estilos, anchos de columna, alturas de
            fila) en una nueva hoja llamada title en dest_wb.
            """
            dest_sheet = dest_wb.create_sheet(title=title[:31])
            for row in src_sheet.iter_rows():
                for cell in row:
                    dest_cell = dest_sheet.cell(
                        row=cell.row, column=cell.column, value=cell.value
                    )
                    if cell.has_style:
                        dest_cell.font          = cell.font.copy()
                        dest_cell.fill          = cell.fill.copy()
                        dest_cell.alignment     = cell.alignment.copy()
                        dest_cell.border        = cell.border.copy()
                        dest_cell.number_format = cell.number_format
            for col_letter, col_dim in src_sheet.column_dimensions.items():
                dest_sheet.column_dimensions[col_letter].width = col_dim.width
            for row_num, row_dim in src_sheet.row_dimensions.items():
                dest_sheet.row_dimensions[row_num].height = row_dim.height
            return dest_sheet

        # ------------------------------------------------------------------
        # Helper — derive worker name from WorkOrder.
        # Auxiliar — derivar nombre del operario desde WorkOrder.
        # ------------------------------------------------------------------
        def _get_worker_name(wo):
            """
            Returns the worker name from the PDF filename, or a fallback label.
            ---
            Devuelve el nombre del operario del nombre del PDF, o etiqueta de
            reserva.
            """
            if wo.source_pdf:
                return _worker_name_from_pdf_path(wo.source_pdf.name)
            return f"Operario #{wo.pk}"

        # ==================================================================
        # MODE: single_sheet
        # Reads WorkOrderEntryLine records directly from the DB.
        # Groups by worker_name (asc) then work_date (asc).
        # Inserts a dark-blue separator row before each new worker block.
        # ==================================================================
        # MODO: single_sheet
        # Lee WorkOrderEntryLine directamente de la BD.
        # Agrupa por worker_name (asc) y work_date (asc).
        # Inserta fila separadora azul oscuro antes de cada nuevo operario.
        # ==================================================================
        if export_mode == "single_sheet":

            # Collect all EntryLine records for the selected WorkOrders,
            # enriched with worker_name derived from the parent WorkOrder.
            # Recopilar todos los EntryLine de los WorkOrders seleccionados,
            # enriquecidos con worker_name derivado del WorkOrder padre.
            wo_map = {wo.pk: wo for wo in work_orders}

            lines_qs = (
                WorkOrderEntryLine.objects
                .filter(entry__work_order__in=work_orders)
                .select_related(
                    "entry",
                    "entry__work_order",
                    "machine_asset",
                )
                .order_by(
                    "entry__work_order__pk",
                    "entry__work_date",
                    "entry__page_number",
                    "line_number",
                )
            )

            # Build a list of dicts enriched with worker_name and date_key
            # for grouping. Sort by (worker_name, date_key, page, line).
            # Construir lista de dicts con worker_name y date_key para
            # agrupación. Ordenar por (worker_name, date_key, página, línea).
            enriched = []
            for line in lines_qs:
                entry       = line.entry
                wo          = entry.work_order
                worker_name = _get_worker_name(wo)
                date_key    = entry.work_date or ""
                enriched.append({
                    "worker_name": worker_name,
                    "date_key":    date_key,
                    "line":        line,
                    "entry":       entry,
                })

            # Sort: primary = worker_name, secondary = date_key.
            # Ordenar: primario = worker_name, secundario = date_key.
            enriched.sort(key=lambda r: (
                r["worker_name"],
                r["date_key"] if r["date_key"] else "",
            ))

            # ------------------------------------------------------------------
            # Build the single flat sheet.
            # Construir la hoja plana única.
            # ------------------------------------------------------------------
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "EXPORTACION"

            # Colour constants for the separator row.
            # Constantes de color para la fila separadora.
            _SEP_BG = "1F4E79"   # Azul oscuro (igual que cabecera Excel individual)
            _SEP_FG = "FFFFFF"   # Blanco

            def _make_sep_fill():
                return PatternFill(
                    fill_type="solid",
                    start_color=_SEP_BG,
                    end_color=_SEP_BG,
                )

            # Column headers / Cabeceras de columna
            headers = [
                "OPERARIO", "FECHA", "BLOQUE", "MÁQUINA (NORM)",
                "MÁQUINA (RAW)", "ACTIVO RESUELTO", "DESCRIPCIÓN AVERÍA",
                "REPARACIÓN", "H.C.", "H.F.", "Δ HORAS", "O.R.", "FLAGS",
            ]
            NUM_COLS = len(headers)

            for col_idx, hdr in enumerate(headers, start=1):
                cell            = ws.cell(row=1, column=col_idx, value=hdr)
                cell.font       = Font(bold=True, color=_SEP_FG)
                cell.fill       = _make_sep_fill()
                cell.alignment  = Alignment(horizontal="center", vertical="center")
            ws.row_dimensions[1].height = 20

            current_worker = None
            data_row       = 2   # Next available data row / Próxima fila disponible.

            for rec in enriched:
                worker_name = rec["worker_name"]
                line        = rec["line"]
                entry       = rec["entry"]

                # Insert separator row when worker changes.
                # Insertar fila separadora cuando cambia el operario.
                if worker_name != current_worker:
                    ws.merge_cells(
                        start_row=data_row, start_column=1,
                        end_row=data_row,   end_column=NUM_COLS,
                    )
                    sep_cell            = ws.cell(row=data_row, column=1,
                                                  value=worker_name)
                    sep_cell.font       = Font(bold=True, color=_SEP_FG, size=11)
                    sep_cell.fill       = _make_sep_fill()
                    sep_cell.alignment  = Alignment(horizontal="left",
                                                    vertical="center")
                    ws.row_dimensions[data_row].height = 22
                    data_row      += 1
                    current_worker = worker_name

                # Write data row / Escribir fila de datos.
                date_display  = (
                    entry.work_date.strftime("%d/%m/%Y")
                    if entry.work_date else ""
                )
                asset_code    = (
                    line.machine_asset.code if line.machine_asset else ""
                )
                hc_display    = (
                    line.hc.strftime("%H:%M") if line.hc else ""
                )
                hf_display    = (
                    line.hf.strftime("%H:%M") if line.hf else ""
                )
                delta_display = (
                    str(line.delta_hours) if line.delta_hours is not None else ""
                )
                flags_display = ", ".join(line.flags) if line.flags else ""

                row_values = [
                    worker_name,
                    date_display,
                    line.line_number,
                    line.machine_norm,
                    line.machine_raw,
                    asset_code,
                    line.fault_description,
                    line.repair_notes,
                    hc_display,
                    hf_display,
                    delta_display,
                    line.or_val,
                    flags_display,
                ]
                for col_idx, val in enumerate(row_values, start=1):
                    cell           = ws.cell(row=data_row, column=col_idx, value=val)
                    cell.alignment = Alignment(vertical="center", wrap_text=False)
                ws.row_dimensions[data_row].height = 16
                data_row += 1

            # Auto-width for all columns (capped at 60).
            # Ancho automático para todas las columnas (máximo 60).
            for col_idx, hdr in enumerate(headers, start=1):
                col_letter = openpyxl.utils.get_column_letter(col_idx)
                ws.column_dimensions[col_letter].width = min(
                    max(len(hdr) + 2, 12), 60
                )

            if ws.max_row < 2:
                return HttpResponseBadRequest(
                    "# [EXPORT] No hay líneas de datos en los partes seleccionados."
                )

        # ==================================================================
        # MODE: multi_sheet
        # Groups WorkOrders by worker_name. One sheet per worker.
        # Each sheet is copied from the individual Excel (regenerated if needed).
        # ==================================================================
        # MODO: multi_sheet
        # Agrupa WorkOrders por worker_name. Una hoja por operario.
        # Cada hoja se copia del Excel individual (regenerado si es necesario).
        # ==================================================================
        else:
            # Group WorkOrders by worker_name preserving insertion order.
            # Agrupar WorkOrders por worker_name preservando el orden de inserción.
            from collections import OrderedDict
            groups: dict[str, list] = OrderedDict()
            for wo in work_orders:
                worker_name = _get_worker_name(wo)
                groups.setdefault(worker_name, []).append(wo)

            wb = openpyxl.Workbook()
            wb.remove(wb.active)   # Remove default empty sheet / Eliminar hoja vacía.

            for worker_name, wo_list in groups.items():
                # Use the first WorkOrder of this worker as the sheet source.
                # Use additional ones if the first fails.
                # Usar el primer WorkOrder del operario como fuente de hoja.
                # Usar los siguientes si el primero falla.
                sheet_built = False
                for wo in wo_list:
                    try:
                        # Ensure excel_file exists; regenerate if missing.
                        # Garantizar que excel_file existe; regenerar si falta.
                        if not wo.excel_file:
                            _gen_excel(wo.pk)
                            wo.refresh_from_db(fields=["excel_file"])
                        if not wo.excel_file:
                            continue
                        with wo.excel_file.open("rb") as f:
                            buf = io.BytesIO(f.read())
                        src_wb    = openpyxl.load_workbook(buf)
                        src_sheet = src_wb.worksheets[0]
                        # Sheet title: worker name truncated to 28 chars + pk suffix.
                        # Título de hoja: nombre truncado a 28 chars + sufijo pk.
                        sheet_title = (
                            (worker_name[:28] + f"#{wo.pk}")
                            if worker_name else f"Parte#{wo.pk}"
                        )
                        _copy_sheet(src_sheet, wb, sheet_title)
                        sheet_built = True
                        break
                    except Exception:
                        continue

                if not sheet_built:
                    # If all attempts failed, insert a placeholder sheet.
                    # Si todos los intentos fallaron, insertar hoja de marcador.
                    placeholder = wb.create_sheet(
                        title=(worker_name[:28] if worker_name else "Sin datos")[:31]
                    )
                    placeholder.cell(row=1, column=1,
                                     value="No se pudo generar el Excel para este operario.")

            if not wb.worksheets:
                return HttpResponseBadRequest(
                    "# [EXPORT] No se pudo generar ninguna hoja para los partes seleccionados."
                )

        # ------------------------------------------------------------------
        # Serialise and return as a file download response.
        # Serializar y devolver como respuesta de descarga de archivo.
        # ------------------------------------------------------------------
        output   = io.BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"EXPORTACION_{tz_now().strftime('%d-%m-%y')}.xlsx"
        response = HttpResponse(
            output.read(),
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class WorkOrderDuplicateSearchView(SupervisorAccessMixin, View):
    """
    HTMX endpoint that detects duplicate WorkOrders for the authenticated
    company by querying WorkOrderEntry records sharing identical
    (worker_name, work_date) tuples across distinct WorkOrders.
    Returns a rendered _duplicates_fragment.html partial with the grouped
    results, or an informational fragment when no duplicates are found.

    POST /panel/work-orders/duplicates/search/
         Returns HTTP 200 with the rendered fragment in all cases.
         Returns HTTP 404 if the authenticated user has no CompanyUser profile.

    Accessible to SUPERVISOR and ADMIN roles (SupervisorAccessMixin).

    ---

    Endpoint HTMX que detecta WorkOrders duplicados para la empresa autenticada
    consultando registros WorkOrderEntry que comparten tuplas (worker_name,
    work_date) idénticas entre distintos WorkOrders. Devuelve el parcial
    _duplicates_fragment.html renderizado con los resultados agrupados, o un
    fragmento informativo cuando no se detectan duplicados.

    POST /panel/work-orders/duplicates/search/
         Devuelve HTTP 200 con el fragmento renderizado en todos los casos.
         Devuelve HTTP 404 si el usuario autenticado no tiene perfil CompanyUser.

    Accesible para los roles SUPERVISOR y ADMIN (SupervisorAccessMixin).
    """

    def post(self, request):
        """
        Executes the duplicate detection query scoped to the authenticated
        company and returns the rendered _duplicates_fragment.html partial.

        Detection logic mirrors detect_duplicate_entries management command:
          1. Query (company, worker_name, work_date) groups where more than one
             distinct WorkOrder contributes WorkOrderEntry records.
          2. For each group, fetch all implicated WorkOrders ordered by pk.
          3. Identify keeper (highest pk) and candidates for deletion (lower pks).

        ---

        Ejecuta la consulta de detección de duplicados acotada a la empresa
        autenticada y devuelve el parcial _duplicates_fragment.html renderizado.

        La lógica de detección es equivalente al comando de gestión
        detect_duplicate_entries:
          1. Consultar grupos (empresa, operario, fecha) donde más de un
             WorkOrder distinto aporta registros WorkOrderEntry.
          2. Por cada grupo, obtener todos los WorkOrders implicados ordenados
             por pk.
          3. Identificar el conservado (pk más alto) y los candidatos a
             eliminación (pks inferiores).
        """
        from django.db.models import Count
        from work_order_processor.models import WorkOrderEntry

        company = request.user.company_user.company

        # ------------------------------------------------------------------
        # Step 1 — Query duplicate (company, worker_name, work_date) groups.
        # Paso 1 — Consultar los grupos (empresa, operario, fecha) duplicados.
        # ------------------------------------------------------------------
        raw_groups = list(
            WorkOrderEntry.objects
            .filter(work_order__company=company)
            .values("worker_name", "work_date")
            .annotate(wo_count=Count("work_order_id", distinct=True))
            .filter(wo_count__gt=1)
            .order_by("worker_name", "work_date")
        )

        if not raw_groups:
            # No duplicates found — render informational fragment.
            # Sin duplicados — renderizar fragmento informativo.
            return render(
                request,
                "panel/work_orders/_duplicates_fragment.html",
                {"duplicate_groups": [], "no_duplicates": True},
            )

        # ------------------------------------------------------------------
        # Step 2 — Enrich each group with the implicated WorkOrder records.
        # Paso 2 — Enriquecer cada grupo con los registros WorkOrder implicados.
        # ------------------------------------------------------------------
        enriched_groups = []

        for raw in raw_groups:
            worker_name = raw["worker_name"] or ""
            work_date   = raw["work_date"]

            # Fetch all WorkOrders sharing this (company, worker, date) pair.
            # Obtener todos los WorkOrders que comparten este par (empresa, operario, fecha).
            implicated = list(
                WorkOrder.objects
                .filter(
                    company=company,
                    entries__worker_name=worker_name,
                    entries__work_date=work_date,
                )
                .select_related("uploaded_by__user")
                .distinct()
                .order_by("pk")
            )

            if len(implicated) < 2:
                # Guard against race conditions between aggregation and fetch.
                # Proteger contra condiciones de carrera entre agregación y fetch.
                continue

            enriched_groups.append({
                "worker_name": worker_name,
                "work_date":   work_date,
                "work_orders": implicated,
                "keeper":      implicated[-1],    # highest pk — preserved
                "to_delete":   implicated[:-1],   # lower pks — deletion candidates
            })

        return render(
            request,
            "panel/work_orders/_duplicates_fragment.html",
            {
                "duplicate_groups": enriched_groups,
                "no_duplicates":    False,
                "company_user":     request.user.company_user,
            },
        )


class WorkOrderDuplicateDeleteView(AdminRoleRequiredMixin, View):
    """
    HTMX endpoint that deletes a single WorkOrder identified by pk, scoped
    to the authenticated company. Intended for use in the duplicates panel:
    the caller is responsible for ensuring the pk belongs to a duplicate
    group (not the keeper). Returns an empty HTTP 200 response so that HTMX
    removes the corresponding row from the DOM via hx-swap="outerHTML".

    POST /panel/work-orders/duplicates/<pk>/delete/
         Returns HTTP 404 if the WorkOrder does not exist or belongs to
         another company.

    Restricted to the ADMIN role (AdminRoleRequiredMixin).

    ---

    Endpoint HTMX que elimina un único WorkOrder identificado por pk, acotado
    a la empresa autenticada. Diseñado para su uso en el panel de duplicados:
    el llamador es responsable de garantizar que el pk pertenece a un grupo
    duplicado (no al conservado). Devuelve una respuesta HTTP 200 vacía para
    que HTMX elimine la fila correspondiente del DOM via hx-swap="outerHTML".

    POST /panel/work-orders/duplicates/<pk>/delete/
         Devuelve HTTP 404 si el WorkOrder no existe o pertenece a otra empresa.

    Restringido al rol ADMIN (AdminRoleRequiredMixin).
    """

    def post(self, request, pk):
        """
        Deletes the WorkOrder identified by pk, cascade-removing all its
        children (WorkOrderEntry, WorkOrderEntryLine, source PDF, Excel file).
        Returns an empty response body for HTMX outerHTML swap.

        ---

        Elimina el WorkOrder identificado por pk, eliminando en cascada todos
        sus hijos (WorkOrderEntry, WorkOrderEntryLine, PDF original, Excel).
        Devuelve cuerpo vacío para el swap outerHTML de HTMX.
        """
        from django.shortcuts import get_object_or_404
        from django.http import HttpResponse

        company = request.user.company_user.company
        wo      = get_object_or_404(WorkOrder, pk=pk, company=company)
        wo.delete()

        # Return empty body — HTMX replaces the target element with nothing.
        # Devolver cuerpo vacío — HTMX reemplaza el elemento objetivo con nada.
        return HttpResponse("")


class AnalyticsView(AdminRoleRequiredMixin, View):
    """
    Renders the analytics dashboard for the authenticated user's company.
    Serves the template shell only — all data is fetched client-side via
    the AnalyticsDataView JSON endpoint (/panel/analytics/data/).

    ---

    Renderiza el panel de analítica para la empresa del usuario autenticado.
    Sirve únicamente el shell del template — todos los datos se obtienen
    en el cliente mediante el endpoint JSON AnalyticsDataView
    (/panel/analytics/data/).
    """

    template_name = "panel/analytics.html"

    def _get_own_presence(self, company_user):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

    def get(self, request):
        """
        Renders the analytics page. No chart data is computed here —
        the JS layer fetches it from /panel/analytics/data/.
        ---
        Renderiza la página de analítica. No se calculan datos de gráfico
        aquí — la capa JS los obtiene de /panel/analytics/data/.
        """
        company_user = request.user.company_user
        company      = company_user.company

        return render(request, self.template_name, {
            "company":      company,
            "company_user": company_user,
            "own_presence": self._get_own_presence(company_user),
            "active_nav":   "analytics",
        })


class AnalyticsDataView(AdminRoleRequiredMixin, View):
    """
    JSON endpoint that returns all WorkOrderEntryLine records for the
    authenticated user's company, enriched with machine asset metadata,
    work date and WorkOrder reference. The client-side chart builder
    consumes this payload to filter, aggregate and render Plotly charts
    without further server round-trips.

    Response schema:
    {
        "lines": [
            {
                "id":          int,
                "work_date":   "YYYY-MM-DD" | null,
                "work_order":  int,
                "pdf_name":    str,
                "code":      str,
                "brand_model": str,
                "delta_hours": float | null,
                "weekday":     int | null   // 0=Mon … 4=Fri
            },
            ...
        ],
        "work_orders": [
            {"id": int, "label": str},
            ...
        ],
        "assets": [
            {"code": str, "brand_model": str},
            ...
        ]
    }

    ---

    Endpoint JSON que devuelve todos los registros WorkOrderEntryLine de la
    empresa del usuario autenticado, enriquecidos con metadatos del activo,
    fecha de trabajo y referencia al WorkOrder. El constructor de gráficos
    client-side consume este payload para filtrar, agregar y renderizar
    gráficos Plotly sin más round-trips al servidor.

    Esquema de respuesta:
    {
        "lines": [
            {
                "id":           int,
                "work_date":    "YYYY-MM-DD" | null,
                "work_order":   int,
                "pdf_name":     str,
                "code":       str,
                "brand_model": str,
                "delta_hours":  float | null,
                "weekday":      int | null   // 0=Lun … 4=Vie
            },
            ...
        ],
        "work_orders": [
            {"id": int, "label": str},
            ...
        ],
        "assets": [
            {"code": str, "brand_model": str},
            ...
        ]
    }
    """

    # Weekday names in Spanish for chart labels.
    # Nombres de día de semana en castellano para etiquetas de gráfico.
    _WEEKDAY_LABELS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]

    def get(self, request):
        """
        Queries and serialises all WorkOrderEntryLine records for the company.
        Returns HTTP 200 with a JSON payload or HTTP 403 if the user has no
        associated CompanyUser profile.

        ---

        Consulta y serializa todos los registros WorkOrderEntryLine de la empresa.
        Devuelve HTTP 200 con payload JSON o HTTP 403 si el usuario no tiene
        perfil CompanyUser asociado.
        """
        import json as _json
        from django.http import JsonResponse

        try:
            company = request.user.company_user.company
        except AttributeError:
            return JsonResponse({"error": "Sin perfil de empresa asociado."}, status=403)

        # ------------------------------------------------------------------
        # Query all entry lines with resolved asset and work date.
        # Consultar todas las líneas de entrada con activo y fecha resueltos.
        # ------------------------------------------------------------------
        qs = (
            WorkOrderEntryLine.objects
            .filter(
                entry__work_order__company=company,
                machine_asset__isnull=False,
                entry__work_date__isnull=False,
            )
            .select_related(
                "machine_asset",
                "entry",
                "entry__work_order",
            )
            .order_by("entry__work_date", "machine_asset__code")
        )

        lines = []
        for line in qs:
            work_date  = line.entry.work_date
            delta      = float(line.delta_hours) if line.delta_hours is not None else None
            pdf_name   = line.entry.work_order.source_pdf.name.split("/")[-1]
            # Strip Django random suffix from filename for readability.
            # Eliminar sufijo aleatorio de Django del nombre de fichero para legibilidad.
            import re as _re
            pdf_label  = _re.sub(r'_[A-Za-z0-9]{7}(\.[^.]+)$', r'', pdf_name)

            lines.append({
                "id":          line.pk,
                "work_date":   work_date.isoformat() if work_date else None,
                "work_order":  line.entry.work_order_id,
                "pdf_name":    pdf_label,
                "code":      line.machine_asset.code,
                "brand_model": line.machine_asset.brand_model,
                "delta_hours": delta,
                "weekday":     work_date.weekday() if work_date else None,
            })

        # ------------------------------------------------------------------
        # Build auxiliary lists for filter controls.
        # Construir listas auxiliares para los controles de filtro.
        # ------------------------------------------------------------------
        # Distinct WorkOrders with a human-readable label.
        # WorkOrders distintos con etiqueta legible.
        wo_qs = (
            WorkOrder.objects
            .filter(company=company, status=WorkOrder.Status.DONE)
            .order_by("id")
        )
        work_orders = []
        for wo in wo_qs:
            raw      = wo.source_pdf.name.split("/")[-1]
            label    = _re.sub(r'_[A-Za-z0-9]{7}(\.[^.]+)$', r'', raw)
            work_orders.append({"id": wo.pk, "label": label})

        # Distinct assets present in the data, sorted by codigo.
        # Activos distintos presentes en los datos, ordenados por codigo.
        seen_assets: dict[str, str] = {}
        for line in lines:
            c = line["code"]
            if c not in seen_assets:
                seen_assets[c] = line["brand_model"]
        assets = [
            {"code": c, "brand_model": m}
            for c, m in sorted(seen_assets.items())
        ]

        return JsonResponse({
            "lines":       lines,
            "work_orders": work_orders,
            "assets":      assets,
        })


class AnalyticsProfileListCreateView(AdminRoleRequiredMixin, View):
    """
    JSON endpoint for listing and creating/updating AnalyticsProfile records
    belonging to the authenticated CompanyUser.

    GET  /panel/analytics/profiles/
         Returns a JSON array of all profiles for the current user, ordered
         by name. Each item exposes: id, nombre, config.

    POST /panel/analytics/profiles/
         Body (JSON): {"nombre": str, "config": {...}}
         Creates a new profile or updates an existing one with the same name
         (upsert semantics — unique_together enforced at model level).
         Returns the saved profile as JSON with HTTP 200.
         Returns HTTP 400 on missing or invalid payload.
    ---
    Endpoint JSON para listar y crear/actualizar registros AnalyticsProfile
    del CompanyUser autenticado.

    GET  /panel/analytics/profiles/
         Devuelve un array JSON con todos los perfiles del usuario actual,
         ordenados por nombre. Cada elemento expone: id, nombre, config.

    POST /panel/analytics/profiles/
         Cuerpo (JSON): {"nombre": str, "config": {...}}
         Crea un perfil nuevo o actualiza uno existente con el mismo nombre
         (semántica upsert — unicidad aplicada a nivel de modelo).
         Devuelve el perfil guardado como JSON con HTTP 200.
         Devuelve HTTP 400 si el payload está ausente o es inválido.
    """

    def get(self, request):
        """
        Returns the list of AnalyticsProfile records for the current CompanyUser.
        ---
        Devuelve la lista de registros AnalyticsProfile del CompanyUser actual.
        """
        import json as _json
        from django.http import JsonResponse

        try:
            company_user = request.user.company_user
        except AttributeError:
            return JsonResponse({"error": "Sin perfil de empresa asociado."}, status=403)

        profiles = (
            AnalyticsProfile.objects
            .filter(company_user=company_user)
            .order_by("nombre")
            .values("id", "nombre", "config")
        )
        return JsonResponse({"profiles": list(profiles)})

    def post(self, request):
        """
        Creates or updates an AnalyticsProfile for the current CompanyUser.
        Uses update_or_create so that saving an existing name overwrites its
        config rather than raising a uniqueness error.
        ---
        Crea o actualiza un AnalyticsProfile para el CompanyUser actual.
        Usa update_or_create para que guardar un nombre existente sobreescriba
        su config en lugar de lanzar un error de unicidad.
        """
        import json as _json
        from django.http import JsonResponse

        try:
            company_user = request.user.company_user
        except AttributeError:
            return JsonResponse({"error": "Sin perfil de empresa asociado."}, status=403)

        # Parse JSON body / Parsear cuerpo JSON.
        try:
            payload = _json.loads(request.body)
        except (ValueError, TypeError):
            return JsonResponse({"error": "Cuerpo JSON inválido."}, status=400)

        nombre = payload.get("nombre", "").strip()
        config = payload.get("config")

        if not nombre:
            return JsonResponse({"error": "El campo 'nombre' es obligatorio."}, status=400)
        if not isinstance(config, dict):
            return JsonResponse({"error": "El campo 'config' debe ser un objeto JSON."}, status=400)

        # Upsert: create or overwrite existing profile with the same name.
        # Upsert: crear o sobreescribir el perfil existente con el mismo nombre.
        profile, _ = AnalyticsProfile.objects.update_or_create(
            company_user=company_user,
            nombre=nombre,
            defaults={"config": config},
        )

        return JsonResponse({
            "id":     profile.pk,
            "nombre": profile.nombre,
            "config": profile.config,
        })


class WorkshopAssetAutocompleteView(WorkshopRequiredMixin, View):
    """
    JSON endpoint returning MachineAsset records for the authenticated
    CompanyUser's company. Supports incremental search via the optional
    'q' GET parameter (matches against codigo and brand_model).
    Used by the operator work-order entry form (Hito 7 / Paso 5).

    GET /panel/operator/assets/?q=<query>
        Returns a JSON array of {codigo, brand_model} objects, max 20 results.
        If 'q' is absent or blank, returns the first 20 active assets ordered
        by codigo.
    ---
    Endpoint JSON que devuelve registros MachineAsset de la empresa del
    CompanyUser autenticado. Admite búsqueda incremental mediante el parámetro
    GET opcional 'q' (busca en codigo y brand_model).
    Usado por el formulario de entrada de partes del operario (Hito 7 / Paso 5).

    GET /panel/operator/assets/?q=<query>
        Devuelve un array JSON de objetos {codigo, brand_model}, máx. 20 resultados.
        Si 'q' está ausente o vacío, devuelve los primeros 20 activos ordenados
        por codigo.
    """

    def get(self, request, *args, **kwargs):
        """
        Returns a filtered list of active MachineAsset records as JSON.
        ---
        Devuelve una lista filtrada de registros MachineAsset activos como JSON.
        """
        from django.http import JsonResponse
        from fleet.models import MachineAsset

        try:
            company = request.user.company_user.company
        except AttributeError:
            return JsonResponse({"error": "Sin perfil de empresa."}, status=403)

        q = request.GET.get("q", "").strip()
        qs = MachineAsset.objects.filter(company=company, is_active=True)

        if q:
            # Case-insensitive search on code and brand_model.
            # Búsqueda sin distinción de mayúsculas en code y brand_model.
            qs = qs.filter(
                django_models.Q(code__icontains=q) |
                django_models.Q(brand_model__icontains=q)
            )

        assets = list(
            qs.order_by("code")
            .values("code", "brand_model")[:20]
        )
        return JsonResponse({"assets": assets})


class WorkOrderEntryUploadView(WorkshopRequiredMixin, View):
    """
    Handles the operator Upload path (Via C) for new work orders.
    Accepts a photo or PDF file, rasterises it and sends it to Gemini Vision
    via extract_work_order_page_full() which returns both work blocks (front)
    and spare-part lines (back). The extracted data is stored in the session
    and the user is redirected to WorkOrderEntryConfirmView for full validation
    before any database write occurs.

    GET  /panel/operator/upload/
         Renders the upload form (upload_entry.html).
    POST /panel/operator/upload/
         Processes the uploaded file, stores extraction result in session,
         redirects to /panel/operator/confirm/.
    ---
    Gestiona la vía Upload (Vía C) del operario para partes nuevos.
    Acepta una foto o PDF, lo rasteriza y lo envía a Gemini Vision mediante
    extract_work_order_page_full() que devuelve tanto los bloques de trabajo
    (cara delantera) como las líneas de repuesto (cara trasera). Los datos
    extraídos se almacenan en la sesión y el usuario es redirigido a
    WorkOrderEntryConfirmView para validación completa antes de escribir en BD.

    GET  /panel/operator/upload/
         Renderiza el formulario de subida (upload_entry.html).
    POST /panel/operator/upload/
         Procesa el archivo subido, almacena el resultado de extracción en
         sesión, redirige a /panel/operator/confirm/.
    """

    template_name = "panel/operator/upload_entry.html"

    def _get_context(self, request, error=None):
        """
        Builds base template context for the upload view.
        ---
        Construye el contexto base para la vista de subida.
        """
        cu = request.user.company_user
        return {
            "company":      cu.company,
            "company_user": cu,
            "active_nav":   "operator_dashboard",
            "error":        error,
        }

    def get(self, request, *args, **kwargs):
        """
        Renders the upload form.
        ---
        Renderiza el formulario de subida.
        """
        return render(request, self.template_name, self._get_context(request))

    def post(self, request, *args, **kwargs):
        """
        Processes the uploaded file through Gemini Vision (full prompt).
        Stores the structured extraction result in the session and redirects
        to the confirmation view. On Gemini failure (confidence=FAILED) the
        form is re-rendered with a descriptive error message.
        ---
        Procesa el archivo subido mediante Gemini Vision (prompt completo).
        Almacena el resultado de extracción estructurado en la sesión y redirige
        a la vista de confirmación. En caso de fallo de Gemini (confidence=FAILED)
        se re-renderiza el formulario con un mensaje de error descriptivo.
        """
        import io
        from pdf2image import convert_from_bytes
        from PIL import Image
        from work_order_processor.services import extract_work_order_page_full

        uploaded_file = request.FILES.get("work_order_file")
        if not uploaded_file:
            return render(
                request, self.template_name,
                self._get_context(request, error="Debes seleccionar un archivo.")
            )

        file_bytes = uploaded_file.read()
        content_type = uploaded_file.content_type or ""

        try:
            # Rasterise: PDF → PNG bytes / PNG/JPEG → pass through as PNG bytes.
            # Rasterizar: PDF → bytes PNG / PNG/JPEG → pasar como bytes PNG.
            if "pdf" in content_type or uploaded_file.name.lower().endswith(".pdf"):
                # Convert first page of PDF to PNG at 200 DPI.
                # Convertir la primera página del PDF a PNG a 200 DPI.
                pages = convert_from_bytes(file_bytes, dpi=200, first_page=1, last_page=1)
                if not pages:
                    raise ValueError("# No se pudieron extraer páginas del PDF.")
                buf = io.BytesIO()
                pages[0].save(buf, format="PNG")
                image_bytes = buf.getvalue()
            else:
                # Image input: re-encode as PNG for Gemini.
                # Entrada imagen: recodificar como PNG para Gemini.
                img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                image_bytes = buf.getvalue()

        except Exception as exc:
            logger.error(
                "# [Upload] Error al rasterizar archivo: %s", exc, exc_info=True
            )
            return render(
                request, self.template_name,
                self._get_context(
                    request,
                    error=(
                        "No se pudo procesar el archivo. "
                        "Asegúrate de que es una imagen o PDF válido."
                    ),
                )
            )

        # Call Gemini Vision with the full (front+back) prompt.
        # Llamar a Gemini Vision con el prompt completo (delantera + trasera).
        extraction = extract_work_order_page_full(image_bytes)

        if extraction.get("extraction_confidence") == "FAILED":
            return render(
                request, self.template_name,
                self._get_context(
                    request,
                    error=(
                        "Gemini no pudo extraer datos del archivo. "
                        "Comprueba que la imagen sea legible y corresponda "
                        "a un parte de trabajo."
                    ),
                )
            )

        # Store extraction result in session for the confirmation view.
        # Almacenar resultado de extracción en sesión para la vista de confirmación.
        request.session["operator_upload_extraction"] = extraction
        request.session.modified = True

        logger.info(
            "# [Upload] Extracción completada. Confianza: %s | "
            "Entradas: %d | Repuestos: %d. Redirigiendo a confirmación.",
            extraction.get("extraction_confidence"),
            len(extraction.get("entradas", [])),
            len(extraction.get("repuestos", [])),
        )

        return redirect("/panel/operator/confirm/")


# ---------------------------------------------------------------------------
# Module-level helpers shared by WorkOrderEntryFormView (and WorkOrderEntrySTTView
# via delegation). Centralise POST parsing and two-pass asset resolution so
# that no view duplicates this logic.
#
# Helpers de módulo compartidos por WorkOrderEntryFormView (y WorkOrderEntrySTTView
# mediante delegación). Centralizan el parseo del POST y la resolución de activos
# en dos pasadas para que ninguna vista duplique esta lógica.
# ---------------------------------------------------------------------------

def _parse_entry_lines_from_post(POST, company):
    """
    Parses and resolves work-block entry lines submitted via POST.

    Resolution strategy for machine_asset (two-pass):
      Pass 1 — direct iexact on machine_raw: covers autocomplete selections
               where the field contains the exact asset.code string.
      Pass 2 — iexact on _normalise_machine_code(machine_raw): covers OCR
               and handwritten input where normalisation is required.

    Returns a list of dicts ready to feed the integrity gate and the
    atomic persistence block.
    ---
    Parsea y resuelve las líneas de entrada de bloque de trabajo enviadas
    por POST.

    Estrategia de resolución para machine_asset (dos pasadas):
      Pasada 1 — iexact directo sobre machine_raw: cubre selecciones del
                 autocompletado donde el campo contiene el asset.code exacto.
      Pasada 2 — iexact sobre _normalise_machine_code(machine_raw): cubre
                 entrada OCR y manuscrita donde se requiere normalización.

    Devuelve una lista de dicts lista para la barrera de integridad y el
    bloque de persistencia atómica.
    """
    import json as _json
    from datetime import time as _dt_time
    from fleet.models import MachineAsset
    from work_order_processor.services import (
        _normalise_machine_code,
        _compute_delta_hours,
    )

    num_entradas     = int(POST.get("num_entradas", "1") or "1")
    entry_lines_data = []

    for i in range(1, num_entradas + 1):
        pfx         = f"entrada_{i}_"
        machine_raw = POST.get(f"{pfx}machine_raw", "").strip()
        desc_averia = POST.get(f"{pfx}fault_description", "").strip()
        repair_notes  = POST.get(f"{pfx}repair_notes", "").strip()
        hc_str      = POST.get(f"{pfx}hc", "").strip()
        hf_str      = POST.get(f"{pfx}hf", "").strip()
        or_val      = POST.get(f"{pfx}or_val", "").strip()
        flags_raw   = POST.get(f"{pfx}flags", "[]")

        def _parse_t(s):
            """
            Parses HH:MM string into time object, returns None on failure.
            ---
            Parsea cadena HH:MM a objeto time, devuelve None en fallo.
            """
            if not s:
                return None
            try:
                parts = s.split(":")
                return _dt_time(int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                return None

        hc = _parse_t(hc_str)
        hf = _parse_t(hf_str)

        machine_norm  = _normalise_machine_code(machine_raw)
        machine_asset = None

        if machine_raw:
            # Pass 1 — direct iexact on raw (autocomplete writes exact codigo).
            # Pasada 1 — iexact directo sobre raw (autocompletado escribe codigo exacto).
            try:
                machine_asset = MachineAsset.objects.get(
                    code__iexact=machine_raw, company=company
                )
            except (MachineAsset.DoesNotExist, MachineAsset.MultipleObjectsReturned):
                machine_asset = MachineAsset.objects.filter(
                    code__iexact=machine_raw, company=company
                ).first()

        if machine_asset is None and machine_norm:
            # Pass 2 — normalised code (OCR / handwritten input).
            # Pasada 2 — código normalizado (entrada OCR / manuscrita).
            try:
                machine_asset = MachineAsset.objects.get(
                    code__iexact=machine_norm, company=company
                )
            except (MachineAsset.DoesNotExist, MachineAsset.MultipleObjectsReturned):
                machine_asset = MachineAsset.objects.filter(
                    code__iexact=machine_norm, company=company
                ).first()

        delta_hours = _compute_delta_hours(hc, hf)

        try:
            flags = _json.loads(flags_raw) if flags_raw else []
        except (ValueError, TypeError):
            flags = []

        # ------------------------------------------------------------------
        # Meter readings — odometer, engine hours, crane hours.
        # Lecturas de contadores — odómetro, horómetro motor, horómetro grúa.
        # ------------------------------------------------------------------
        from decimal import Decimal, InvalidOperation as _InvalidOp

        def _parse_decimal(raw_val):
            """
            Converts a POST string to Decimal or returns None on failure.
            ---
            Convierte una cadena POST a Decimal o devuelve None en caso de fallo.
            """
            v = (raw_val or "").strip().replace(",", ".")
            if not v:
                return None
            try:
                return Decimal(v)
            except _InvalidOp:
                return None

        odometer_reading     = _parse_decimal(POST.get(f"entrada_{i}_odometer_reading", ""))
        engine_hours_reading = _parse_decimal(POST.get(f"entrada_{i}_engine_hours_reading", ""))
        crane_hours_reading  = _parse_decimal(POST.get(f"entrada_{i}_crane_hours_reading", ""))

        entry_lines_data.append({
            "line_number":           i,
            "machine_raw":           machine_raw,
            "machine_norm":          machine_norm or "",
            "machine_asset":         machine_asset,
            "fault_description":     desc_averia,
            "repair_notes":          repair_notes,
            "hc":                    hc,
            "hf":                    hf,
            "or_val":                or_val,
            "delta_hours":           delta_hours,
            "flags":                 flags,
            "odometer_reading":      odometer_reading,
            "engine_hours_reading":  engine_hours_reading,
            "crane_hours_reading":   crane_hours_reading,
        })

    return entry_lines_data


def _parse_spare_parts_from_post(POST, company, entry_lines_data=None):
    """
    Parses and resolves spare-part lines submitted via POST.

    The select field for each spare part now delivers vehiculo_raw directly
    (the CdG value chosen by the operator from the unique list of machine_raw
    values in the current work blocks, or a free-text value when "Otro" is
    selected). Resolution against MachineAsset is attempted in two passes for
    every repuesto regardless of origin. If no match is found, vehicle_asset
    is None and cg_incident is set to True so the persistence layer can set
    WorkOrder.has_cg_incident = True.

    entry_lines_data is accepted for backwards compatibility but is no longer
    used to populate vehiculo_raw — the POST value is authoritative.

    Returns a list of dicts ready to feed the integrity gate and the
    atomic persistence block.
    ---
    Parsea y resuelve las líneas de repuesto enviadas por POST.

    El select de cada repuesto ahora entrega vehiculo_raw directamente
    (el valor CdG elegido por el operario de la lista única de machine_raw
    de los bloques de trabajo actuales, o un valor de texto libre cuando se
    selecciona "Otro"). La resolución contra MachineAsset se intenta en dos
    pasadas para cada repuesto independientemente del origen. Si no hay
    coincidencia, vehicle_asset es None y cg_incident se activa para que la
    capa de persistencia pueda establecer WorkOrder.has_cg_incident = True.

    entry_lines_data se acepta por compatibilidad hacia atrás pero ya no se
    usa para poblar vehiculo_raw — el valor del POST es autoritativo.

    Devuelve una lista de dicts lista para la barrera de integridad y el
    bloque de persistencia atómica.
    """
    from decimal import Decimal, InvalidOperation
    from fleet.models import MachineAsset as _MachineAsset
    from work_order_processor.services import _normalise_machine_code as _norm_code

    num_repuestos    = int(POST.get("num_repuestos", "0") or "0")
    spare_parts_data = []

    for r in range(1, num_repuestos + 1):
        pfx          = f"repuesto_{r}_"
        referencia   = POST.get(f"{pfx}referencia", "").strip()
        material     = POST.get(f"{pfx}material", "").strip()
        unidades_str = POST.get(f"{pfx}unidades", "").strip()
        origen       = POST.get(f"{pfx}origen", "WAREHOUSE").strip()
        proveedor    = POST.get(f"{pfx}proveedor", "").strip()
        # vehiculo_raw is delivered by the CdG select.
        # When "__otro__" is selected, the free-text field cdg_free carries
        # the actual value typed by the operator.
        # vehiculo_raw lo entrega el select de CdG.
        # Cuando se selecciona "__otro__", el campo libre cdg_free contiene
        # el valor real introducido por el operario.
        _cdg_raw = POST.get(f"{pfx}vehiculo_raw", "").strip()
        if _cdg_raw == "__otro__":
            vehiculo_raw = POST.get(f"{pfx}cdg_free", "").strip()
        else:
            vehiculo_raw = _cdg_raw

        quantity = None
        if unidades_str:
            try:
                quantity = Decimal(unidades_str.replace(",", "."))
            except InvalidOperation:
                quantity = None

        if origen not in ("SUPPLIER", "WAREHOUSE"):
            origen = "WAREHOUSE"

        # ------------------------------------------------------------------
        # Resolve vehicle_asset via two-pass lookup against MachineAsset.
        # If no match is found, flag as CdG incident for supervisor review.
        #
        # Resolver vehicle_asset mediante búsqueda en dos pasadas contra
        # MachineAsset. Si no hay coincidencia, marcar como incidencia de
        # CdG para revisión por SUPERVISOR.
        # ------------------------------------------------------------------
        veh_asset   = None
        cg_incident = False

        if vehiculo_raw and company is not None:
            # Pass 1 — direct iexact on vehiculo_raw.
            # Pasada 1 — iexact directo sobre vehiculo_raw.
            try:
                veh_asset = _MachineAsset.objects.get(
                    code__iexact=vehiculo_raw, company=company
                )
            except (_MachineAsset.DoesNotExist, _MachineAsset.MultipleObjectsReturned):
                veh_asset = _MachineAsset.objects.filter(
                    code__iexact=vehiculo_raw, company=company
                ).first()

            if veh_asset is None:
                # Pass 2 — normalised code.
                # Pasada 2 — código normalizado.
                norm = _norm_code(vehiculo_raw)
                if norm:
                    try:
                        veh_asset = _MachineAsset.objects.get(
                            code__iexact=norm, company=company
                        )
                    except (_MachineAsset.DoesNotExist, _MachineAsset.MultipleObjectsReturned):
                        veh_asset = _MachineAsset.objects.filter(
                            code__iexact=norm, company=company
                        ).first()

        if veh_asset is None and vehiculo_raw:
            # vehiculo_raw provided but not resolved — flag for supervisor.
            # vehiculo_raw proporcionado pero sin resolver — marcar para supervisor.
            cg_incident = True

        spare_parts_data.append({
            "line_number":   r,
            "referencia":    referencia,
            "vehiculo_raw":  vehiculo_raw,
            "vehicle_asset": veh_asset,
            "material":      material,
            "quantity":      quantity,
            "source":        origen,
            "supplier":      proveedor if origen == "SUPPLIER" else "",
            "flags":         [],
            "cg_incident":   cg_incident,
        })

    return spare_parts_data


class WorkOrderEntryConfirmView(WorkshopRequiredMixin, View):
    """
    Confirmation and persistence view for the operator Upload path (Via C).
    Reads the extraction result stored in the session by WorkOrderEntryUploadView,
    renders a fully editable confirmation form and, on POST, atomically persists
    the validated data to the database:
      WorkOrder (status=DONE, source_pdf blank) +
      WorkOrderEntry (page 1, confidence from Gemini) +
      N × WorkOrderEntryLine +
      M × SparePartLine per entry line.
    After persistence, generate_work_order_excel() is called synchronously.

    GET  /panel/operator/confirm/
         Renders the confirmation form pre-filled from session data.
         Redirects to the upload view if no session data is found.
    POST /panel/operator/confirm/
         Validates, persists and redirects to the work-order list on success.
    ---
    Vista de confirmación y persistencia para la vía Upload del operario (Vía C).
    Lee el resultado de extracción almacenado en sesión por WorkOrderEntryUploadView,
    renderiza un formulario de confirmación completamente editable y, en POST,
    persiste atómicamente los datos validados en la base de datos:
      WorkOrder (status=DONE, source_pdf en blanco) +
      WorkOrderEntry (página 1, confianza de Gemini) +
      N × WorkOrderEntryLine +
      M × SparePartLine por línea de entrada.
    Tras la persistencia, generate_work_order_excel() se llama de forma síncrona.

    GET  /panel/operator/confirm/
         Renderiza el formulario de confirmación pre-rellenado con datos de sesión.
         Redirige a la vista de subida si no hay datos de sesión.
    POST /panel/operator/confirm/
         Valida, persiste y redirige a la lista de partes en caso de éxito.
    """

    template_name = "panel/operator/confirm_entry.html"

    def _get_company_user(self, request):
        """
        Returns the CompanyUser for the authenticated request user.
        ---
        Devuelve el CompanyUser del usuario autenticado en la solicitud.
        """
        return request.user.company_user

    def _get_context_base(self, request):
        """
        Returns the base template context with company and navigation data.
        ---
        Devuelve el contexto base con empresa y datos de navegación.
        """
        cu = self._get_company_user(request)
        return {
            "company":      cu.company,
            "company_user": cu,
            "active_nav":   "operator_dashboard",
        }

    def _resolve_machine(self, company, raw_code):
        """
        Attempts to resolve a raw machine code string to a MachineAsset
        belonging to the given company, applying the same D4 normalisation
        used by the historical pipeline (_normalise_machine_code).
        Returns the MachineAsset instance or None if no match is found.
        ---
        Intenta resolver un código de máquina bruto a un MachineAsset
        perteneciente a la empresa dada, aplicando la misma normalización D4
        usada por el pipeline histórico (_normalise_machine_code).
        Devuelve la instancia MachineAsset o None si no hay coincidencia.
        """
        from work_order_processor.services import _normalise_machine_code
        from fleet.models import MachineAsset

        if not raw_code:
            return None
        norm = _normalise_machine_code(raw_code)
        if not norm:
            return None
        try:
            return MachineAsset.objects.get(code__iexact=norm, company=company)
        except MachineAsset.DoesNotExist:
            return None
        except MachineAsset.MultipleObjectsReturned:
            return MachineAsset.objects.filter(
                code__iexact=norm, company=company
            ).first()

    def get(self, request, *args, **kwargs):
        """
        Renders the confirmation form using extraction data from the session.
        Redirects to the upload view if the session contains no extraction data.
        ---
        Renderiza el formulario de confirmación usando los datos de extracción
        de la sesión. Redirige a la vista de subida si la sesión no contiene
        datos de extracción.
        """
        from fleet.models import MachineAsset

        extraction = request.session.get("operator_upload_extraction")
        if not extraction:
            logger.warning(
                "# [Confirm] No hay datos de extracción en sesión. "
                "Redirigiendo a la vista de subida."
            )
            return redirect("/panel/operator/upload/")

        cu      = self._get_company_user(request)
        company = cu.company

        # Build enriched entry list for template rendering.
        # Construir lista de entradas enriquecida para el renderizado del template.
        entradas_enriched = []
        for idx, entrada in enumerate(extraction.get("entradas", []), start=1):
            raw_code     = entrada.get("machine_raw") or ""
            machine_asset = self._resolve_machine(company, raw_code)
            entradas_enriched.append({
                "idx":            idx,
                "machine_raw":    raw_code,
                "machine_asset":  machine_asset,
                "fault_description": entrada.get("fault_description") or "",
                "repair_notes":     entrada.get("repair_notes") or "",
                "hc":             entrada.get("hc") or "",
                "hf":             entrada.get("hf") or "",
                "or_val":         entrada.get("or_val") or "",
                "flags":          entrada.get("flags") or [],
            })

        # Build spare-part list for template rendering.
        # Construir lista de repuestos para el renderizado del template.
        repuestos_enriched = []
        for ridx, rep in enumerate(extraction.get("repuestos", []), start=1):
            veh_raw      = rep.get("vehiculo_raw") or ""
            vehicle_asset = self._resolve_machine(company, veh_raw)
            repuestos_enriched.append({
                "ridx":          ridx,
                "referencia":    rep.get("referencia") or "",
                "vehiculo_raw":  veh_raw,
                "vehicle_asset": vehicle_asset,
                "material":      rep.get("material") or "",
                "unidades":      rep.get("unidades"),
                "origen":        rep.get("origen") or "WAREHOUSE",
                "proveedor":     rep.get("proveedor") or "",
                "flags":         rep.get("flags") or [],
            })

        # Active assets for the autocomplete selector.
        # Activos disponibles para el selector de autocompletado.
        assets = list(
            MachineAsset.objects.filter(company=company, is_active=True)
            .order_by("code")
            .values("code", "brand_model")
        )

        _min_date_get = _get_min_allowed_date(cu)
        context = self._get_context_base(request)
        context.update({
            "extraction":          extraction,
            "fecha":               extraction.get("fecha") or "",
            "uncertain_date":      extraction.get("uncertain_date", False),
            "confidence":          extraction.get("extraction_confidence", ""),
            "entradas_enriched":   entradas_enriched,
            "repuestos_enriched":  repuestos_enriched,
            "assets":              assets,
            "num_entradas":        len(entradas_enriched),
            "num_repuestos":       len(repuestos_enriched),
            "min_date":            _min_date_get.isoformat() if _min_date_get else "",
        })
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        """
        Validates the confirmed form data and atomically persists:
          WorkOrder → WorkOrderEntry → WorkOrderEntryLine(s) → SparePartLine(s).
        Generates the Excel report synchronously after persistence.
        Clears the session extraction data on success.
        On validation failure, re-renders the confirmation form with error context.
        ---
        Valida los datos del formulario confirmado y persiste atómicamente:
          WorkOrder → WorkOrderEntry → WorkOrderEntryLine(s) → SparePartLine(s).
        Genera el informe Excel de forma síncrona tras la persistencia.
        Elimina los datos de extracción de la sesión en caso de éxito.
        En caso de fallo de validación, re-renderiza el formulario con contexto
        de error.
        """
        import json as _json
        from datetime import date, time as dt_time
        from decimal import Decimal, InvalidOperation
        from django.db import transaction
        from django.utils import timezone
        from fleet.models import MachineAsset
        from work_order_processor.models import (
            WorkOrder, WorkOrderEntry, WorkOrderEntryLine, SparePartLine,
        )
        from work_order_processor.services import (
            generate_work_order_excel,
            _normalise_machine_code,
            _compute_delta_hours,
        )

        cu      = self._get_company_user(request)
        company = cu.company
        POST    = request.POST

        # ------------------------------------------------------------------
        # Gate 0 — One work order per operator per date (merge flow).
        # Gate 0 — Un parte por operario por fecha (flujo de merge).
        #
        # Before any INSERT, check whether the operator already has an
        # unreviewed digital or generated work order for the submitted date.
        # If so, serialise the incoming lines into the session and redirect
        # to WorkOrderEntryMergeView for conflict resolution.
        #
        # Antes de cualquier INSERT, comprueba si el operario ya tiene un
        # parte digital o generado sin revisar para la fecha enviada. Si es
        # asi, serializa las lineas entrantes en la sesion y redirige a
        # WorkOrderEntryMergeView para resolver el conflicto.
        # ------------------------------------------------------------------
        _gate0_fecha_str = POST.get("fecha", "").strip()
        _gate0_work_date = None
        if _gate0_fecha_str:
            from datetime import datetime as _dt0
            for _fmt0 in ("%d/%m/%Y", "%Y-%m-%d"):
                try:
                    _gate0_work_date = _dt0.strptime(_gate0_fecha_str, _fmt0).date()
                    break
                except ValueError:
                    continue

        if _gate0_work_date is not None:
            # Min-date gate — reject dates on or before the last reviewed entry.
            # Barrera de fecha minima — rechazar fechas sobre o anteriores al
            # ultimo parte revisado del operario.
            _min_date_c = _get_min_allowed_date(cu)
            if _min_date_c is not None and _gate0_work_date < _min_date_c:
                from datetime import timedelta as _td_c
                _last_rev_c = _min_date_c - _td_c(days=1)
                context = self._get_context_base(request)
                context.update({
                    "error": (
                        f"No puedes introducir un parte con fecha "
                        f"{_gate0_work_date.strftime('%d/%m/%Y')}. "
                        f"El ultimo parte revisado es del "
                        f"{_last_rev_c.strftime('%d/%m/%Y')} y ya ha sido auditado. "
                        f"La fecha minima permitida es "
                        f"{_min_date_c.strftime('%d/%m/%Y')}."
                    ),
                    "fecha":              _gate0_fecha_str,
                    "uncertain_date":     False,
                    "confidence":         "",
                    "entradas_enriched":  [],
                    "repuestos_enriched": [],
                    "num_entradas":       0,
                    "num_repuestos":      0,
                    "min_date":           _min_date_c.isoformat(),
                })
                return render(request, self.template_name, context)

            from django.urls import reverse as _rev0
            _existing_entry0 = WorkOrderEntry.objects.filter(
                work_order__company=company,
                work_order__uploaded_by=cu,
                work_order__source__in=[
                    WorkOrder.Source.DIGITAL,
                    WorkOrder.Source.GENERATED,
                ],
                work_order__reviewed=False,
                work_date=_gate0_work_date,
            ).select_related("work_order").first()

            if _existing_entry0 is not None:
                # Unreviewed duplicate — serialise and redirect to merge view.
                # Duplicado sin revisar — serializar y redirigir a merge view.
                _gate0_lines = _parse_entry_lines_from_post(POST, company)
                _gate0_spare = _parse_spare_parts_from_post(
                    POST, company, entry_lines_data=_gate0_lines
                )
                request.session["pending_merge_lines"] = _serialize_pending_lines(
                    _gate0_lines, _gate0_spare, _gate0_work_date
                )
                return redirect(
                    _rev0(
                        "panel:operator_merge",
                        kwargs={"entry_pk": _existing_entry0.pk},
                    )
                )

        # ------------------------------------------------------------------
        # Parse and validate the work date.
        # Parsear y validar la fecha del parte.
        # ------------------------------------------------------------------
        fecha_str = POST.get("fecha", "").strip()
        work_date = None
        if fecha_str:
            for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                try:
                    from datetime import datetime
                    work_date = datetime.strptime(fecha_str, fmt).date()
                    break
                except ValueError:
                    continue

        # ------------------------------------------------------------------
        # Parse and resolve entry lines and spare parts from POST.
        # Parsear y resolver líneas de entrada y repuestos desde POST.
        # Delegated to module-level helpers (DRY). Resolution uses two-pass
        # strategy: raw iexact first (autocomplete), then normalised code
        # (OCR / handwritten).
        # Delegado a helpers de módulo (DRY). Resolución en dos pasadas:
        # iexact sobre raw primero (autocompletado), luego normalizado.
        # ------------------------------------------------------------------
        entry_lines_data = _parse_entry_lines_from_post(POST, company)
        spare_parts_data = _parse_spare_parts_from_post(
            POST, company, entry_lines_data=entry_lines_data
        )


        # ------------------------------------------------------------------
        # Integrity validation (sine qua non gate).
        # Validación de integridad (barrera sine qua non).
        #
        # Every submitted work order must be 100 % complete before it can
        # be persisted. The following checks are performed in order:
        #   1. Work date must be present and parseable.
        #   2. Every work block must have: a non-empty raw machine code that
        #      resolves to a known MachineAsset, both H.C. and H.F. present
        #      and yielding a positive delta_hours, and a non-empty fault
        #      description.
        #   3. Every spare-part line must have: a non-empty material
        #      description and a parseable positive quantity.
        #
        # Any failure re-renders the confirmation form with a detailed error
        # message pinpointing the offending field and block. No data is lost:
        # the form is reconstructed from the already-parsed POST data.
        #
        # Cada parte enviado debe estar completo al 100 % antes de poder
        # persistirse. Se realizan las siguientes comprobaciones en orden:
        #   1. La fecha del parte debe estar presente y ser parseable.
        #   2. Cada bloque de trabajo debe tener: código de máquina no vacío
        #      que resuelva a un MachineAsset conocido, H.C. y H.F. presentes
        #      generando un delta_hours positivo, y descripción de avería no vacía.
        #   3. Cada línea de repuesto debe tener: descripción de material no
        #      vacía y cantidad parseable y positiva.
        #
        # Cualquier fallo re-renderiza el formulario con un mensaje de error
        # detallado indicando el campo y bloque afectados. No se pierde ningún
        # dato: el formulario se reconstruye desde los datos POST ya parseados.
        # ------------------------------------------------------------------
        integrity_errors = []

        # Gate 1 — Work date / Fecha del parte.
        if not work_date:
            integrity_errors.append(
                "La fecha del parte es obligatoria y debe tener formato DD/MM/AAAA."
            )

        # Gate 2 — Work blocks / Bloques de trabajo.
        if not entry_lines_data:
            integrity_errors.append(
                "El parte debe contener al menos un bloque de trabajo."
            )

        for ld in entry_lines_data:
            blk = f"Bloque {ld['line_number']}"
            if not ld["machine_raw"]:
                integrity_errors.append(
                    f"{blk}: el código de máquina es obligatorio."
                )
            elif ld["machine_asset"] is None:
                integrity_errors.append(
                    f"{blk}: el código '{ld['machine_raw']}' no se ha podido "
                    f"identificar en el catálogo de flota. "
                    f"Corrígelo antes de guardar."
                )
            if not ld["hc"]:
                integrity_errors.append(
                    f"{blk}: la hora de inicio (H.C.) es obligatoria."
                )
            if not ld["hf"]:
                integrity_errors.append(
                    f"{blk}: la hora de fin (H.F.) es obligatoria."
                )
            if ld["hc"] and ld["hf"] and ld["delta_hours"] is not None:
                if ld["delta_hours"] <= 0:
                    integrity_errors.append(
                        f"{blk}: la H.F. debe ser posterior a la H.C. "
                        f"(Δ horas calculado: {ld['delta_hours']})."
                    )
            if not ld["fault_description"]:
                integrity_errors.append(
                    f"{blk}: la descripción de la avería es obligatoria."
                )

        # Gate 2b — Meter readings: mandatory counter fields per asset flags.
        # If first_repair=True zeros are allowed (baseline setup).
        # If first_repair=False zeros are blocked — reading must be provided.
        # Gate 2b — Contadores: obligatorios segun flags del activo.
        # Si first_repair=True se permiten ceros (primera toma de datos).
        # Si first_repair=False los ceros se bloquean — debe aportarse lectura.
        for ld in entry_lines_data:
            if ld["machine_asset"] is not None:
                asset = ld["machine_asset"]
                blk   = f"Bloque {ld['line_number']}"
                if asset.has_odometer:
                    reading = ld.get("odometer_reading")
                    if reading is None:
                        integrity_errors.append(
                            f"{blk}: lectura de km (odómetro) obligatoria para {asset.code}."
                        )
                    elif reading == 0 and not asset.first_repair:
                        integrity_errors.append(
                            f"{blk}: la lectura de km no puede ser cero para {asset.code} "
                            f"(ya tiene partes anteriores registrados)."
                        )
                if asset.has_engine_hours:
                    reading = ld.get("engine_hours_reading")
                    if reading is None:
                        integrity_errors.append(
                            f"{blk}: lectura de horómetro motor obligatoria para {asset.code}."
                        )
                    elif reading == 0 and not asset.first_repair:
                        integrity_errors.append(
                            f"{blk}: la lectura de horómetro motor no puede ser cero "
                            f"para {asset.code} (ya tiene partes anteriores registrados)."
                        )
                if asset.has_crane_hours:
                    reading = ld.get("crane_hours_reading")
                    if reading is None:
                        integrity_errors.append(
                            f"{blk}: lectura de horómetro grúa obligatoria para {asset.code}."
                        )
                    elif reading == 0 and not asset.first_repair:
                        integrity_errors.append(
                            f"{blk}: la lectura de horómetro grúa no puede ser cero "
                            f"para {asset.code} (ya tiene partes anteriores registrados)."
                        )

        # Gate 3 — Spare-part lines / Líneas de repuesto.
        for spd in spare_parts_data:
            rep = f"Repuesto {spd['line_number']}"
            if not spd["material"]:
                integrity_errors.append(
                    f"{rep}: la descripción del material es obligatoria."
                )
            if spd["quantity"] is None or spd["quantity"] <= 0:
                integrity_errors.append(
                    f"{rep}: las unidades deben ser un número positivo."
                )

        if integrity_errors:
            # Re-build enriched context from already-parsed POST data so the
            # operator does not lose any corrections already entered.
            # Reconstruir contexto enriquecido desde los datos POST ya parseados
            # para que el operario no pierda las correcciones introducidas.
            entradas_enriched_post = [
                {
                    "idx":               ld["line_number"],
                    "machine_raw":       ld["machine_raw"],
                    "machine_asset":     ld["machine_asset"],
                    "fault_description": ld["fault_description"],
                    "repair_notes":        ld["repair_notes"],
                    "hc":    ld["hc"].strftime("%H:%M") if ld["hc"] else "",
                    "hf":    ld["hf"].strftime("%H:%M") if ld["hf"] else "",
                    "or_val":            ld["or_val"],
                    "flags":             ld["flags"],
                }
                for ld in entry_lines_data
            ]
            spare_enriched_post = [
                {
                    "ridx":       spd["line_number"],
                    "referencia": spd["referencia"],
                    "vehiculo_raw": spd["vehiculo_raw"],
                    "vehicle_asset": spd["vehicle_asset"],
                    "material":   spd["material"],
                    "unidades":   str(spd["quantity"]) if spd["quantity"] is not None else "",
                    "origen":     spd["source"],
                    "proveedor":  spd["supplier"],
                    "flags":      spd["flags"],
                }
                for spd in spare_parts_data
            ]
            context = self._get_context_base(request)
            context.update({
                "error":               " | ".join(integrity_errors),
                "fecha":               fecha_str,
                "uncertain_date":      False,
                "confidence":          POST.get("confidence", ""),
                "entradas_enriched":   entradas_enriched_post,
                "repuestos_enriched":  spare_enriched_post,
                "num_entradas":        len(entry_lines_data),
                "num_repuestos":       len(spare_parts_data),
            })
            return render(request, self.template_name, context)

        # ------------------------------------------------------------------
        # Save confirmation gate — form must have been confirmed via modal.
        # Gate de confirmacion — el formulario debe haber pasado por modal.
        # ------------------------------------------------------------------
        if not POST.get("save_confirmed"):
            entradas_enriched_post = [
                {
                    "idx":               ld["line_number"],
                    "machine_raw":       ld["machine_raw"],
                    "machine_asset":     ld["machine_asset"],
                    "fault_description": ld["fault_description"],
                    "repair_notes":      ld["repair_notes"],
                    "hc":    ld["hc"].strftime("%H:%M") if ld["hc"] else "",
                    "hf":    ld["hf"].strftime("%H:%M") if ld["hf"] else "",
                    "or_val":            ld["or_val"],
                    "flags":             ld["flags"],
                }
                for ld in entry_lines_data
            ]
            spare_enriched_post = [
                {
                    "ridx":          spd["line_number"],
                    "referencia":    spd["referencia"],
                    "vehiculo_raw":  spd["vehiculo_raw"],
                    "vehicle_asset": spd["vehicle_asset"],
                    "material":      spd["material"],
                    "unidades":      str(spd["quantity"]) if spd["quantity"] is not None else "",
                    "origen":        spd["source"],
                    "proveedor":     spd["supplier"],
                    "flags":         spd["flags"],
                }
                for spd in spare_parts_data
            ]
            context = self._get_context_base(request)
            context.update({
                "error":               None,
                "fecha":               fecha_str,
                "uncertain_date":      False,
                "confidence":          POST.get("confidence", ""),
                "entradas_enriched":   entradas_enriched_post,
                "repuestos_enriched":  spare_enriched_post,
                "num_entradas":        len(entry_lines_data),
                "num_repuestos":       len(spare_parts_data),
            })
            return render(request, self.template_name, context)

        # ------------------------------------------------------------------
        # Intra-part validation (R1 overlap, R2 HF>HC, R3 gap).
        # Validación intra-parte (R1 solapamiento, R2 HF>HC, R3 laguna).
        # ------------------------------------------------------------------
        from work_order_processor.validators import (
            run_intra_part_validation,
            parse_blocks_from_post,
            validate_inter_overlap,
            TimeBlock,
        )

        num_entradas_post = int(POST.get("num_entradas", len(entry_lines_data)))
        _blocks = parse_blocks_from_post(POST, num_entradas_post, entry_lines_data=entry_lines_data)
        _intra  = run_intra_part_validation(_blocks)

        if not _intra.ok:
            entradas_enriched_post = [
                {
                    "idx":               ld["line_number"],
                    "machine_raw":       ld["machine_raw"],
                    "machine_asset":     ld["machine_asset"],
                    "fault_description": ld["fault_description"],
                    "repair_notes":        ld["repair_notes"],
                    "hc":    ld["hc"].strftime("%H:%M") if ld["hc"] else "",
                    "hf":    ld["hf"].strftime("%H:%M") if ld["hf"] else "",
                    "or_val":            ld["or_val"],
                    "flags":             ld["flags"],
                }
                for ld in entry_lines_data
            ]
            spare_enriched_post = [
                {
                    "ridx":       spd["line_number"],
                    "referencia": spd["referencia"],
                    "vehiculo_raw": spd["vehiculo_raw"],
                    "vehicle_asset": spd["vehicle_asset"],
                    "material":   spd["material"],
                    "unidades":   str(spd["quantity"]) if spd["quantity"] is not None else "",
                    "origen":     spd["source"],
                    "proveedor":  spd["supplier"],
                    "flags":      spd["flags"],
                }
                for spd in spare_parts_data
            ]
            context = self._get_context_base(request)
            context.update({
                "error":               " | ".join(e.message for e in _intra.errors),
                "fecha":               fecha_str,
                "uncertain_date":      False,
                "confidence":          POST.get("confidence", ""),
                "entradas_enriched":   entradas_enriched_post,
                "repuestos_enriched":  spare_enriched_post,
                "num_entradas":        len(entry_lines_data),
                "num_repuestos":       len(spare_parts_data),
            })
            return render(request, self.template_name, context)

        # ------------------------------------------------------------------
        # Atomic persistence / Persistencia atómica.
        # ------------------------------------------------------------------
        try:
            with transaction.atomic():
                # WorkOrder sintético — sin PDF, status=DONE desde creación.
                # Synthetic WorkOrder — no PDF, status=DONE from creation.
                worker_name = (
                    cu.user.get_full_name() or cu.user.username
                ).upper()

                # Build a human-readable synthetic filename mirroring the
                # historical pipeline pattern: WORKER_DD-MM-AAAA.pdf.
                # No real file is created — only the FileField name string
                # is populated so the list view renders a meaningful label.
                #
                # Construir un nombre de fichero sintético legible siguiendo
                # el patrón del pipeline histórico: TRABAJADOR_DD-MM-AAAA.pdf.
                # No se crea ningún fichero real — sólo se asigna la cadena
                # al campo name del FileField para que el listado sea legible.
                date_tag = (
                    work_date.strftime("%d-%m-%Y") if work_date else "SIN-FECHA"
                )
                synthetic_name = f"{worker_name}_{date_tag}.pdf"

                work_order = WorkOrder(
                    company         = company,
                    uploaded_by     = cu,
                    source          = WorkOrder.Source.DIGITAL,
                    status          = WorkOrder.Status.DONE,
                    total_pages     = 1,
                    processed_pages = 1,
                    reviewed        = False,
                )
                work_order.source_pdf.name = synthetic_name
                work_order.save()

                # WorkOrderEntry — one per submitted form (page 1).
                # WorkOrderEntry — uno por formulario enviado (página 1).
                entry = WorkOrderEntry.objects.create(
                    work_order          = work_order,
                    page_number         = 1,
                    worker_name         = worker_name,
                    work_date           = work_date,
                    uncertain_date      = False,
                    extraction_confidence = WorkOrderEntry.Confidence.HIGH,
                    raw_gemini_response = None,
                )

                # WorkOrderEntryLine records / Registros WorkOrderEntryLine.
                created_lines = {}
                for ld in entry_lines_data:
                    line = WorkOrderEntryLine.objects.create(
                        entry                = entry,
                        line_number          = ld["line_number"],
                        machine_asset        = ld["machine_asset"],
                        machine_raw          = ld["machine_raw"],
                        machine_norm         = ld["machine_norm"],
                        fault_description    = ld["fault_description"],
                        repair_notes         = ld["repair_notes"],
                        hc                   = ld["hc"],
                        hf                   = ld["hf"],
                        or_val               = ld["or_val"],
                        delta_hours          = ld["delta_hours"],
                        flags                = ld["flags"],
                        odometer_reading     = ld.get("odometer_reading"),
                        engine_hours_reading = ld.get("engine_hours_reading"),
                        crane_hours_reading  = ld.get("crane_hours_reading"),
                    )
                    created_lines[ld["line_number"]] = line

                # SparePartLine records linked to their entry line.
                # Registros SparePartLine vinculados a su línea de entrada.
                for spd in spare_parts_data:
                    # Resolve target line: always use first created line since
                    # entry_idx sentinel was removed in S012 refactor.
                    # Resolver línea destino: usar siempre la primera línea creada
                    # ya que el centinela entry_idx fue eliminado en el refactor S012.
                    target_line = next(iter(created_lines.values()), None)
                    if target_line is None:
                        continue

                    SparePartLine.objects.create(
                        entry_line  = target_line,
                        line_number = spd["line_number"],
                        reference   = spd["referencia"],
                        vehicle     = spd["vehicle_asset"],
                        material    = spd["material"],
                        quantity    = spd["quantity"],
                        source      = spd["source"],
                        supplier    = spd["supplier"],
                        flags       = spd["flags"],
                    )

            # Activate has_cg_incident if any spare part used the 'Otro' path
            # and its cost centre could not be resolved in MachineAsset.
            # Activar has_cg_incident si algún repuesto usó la ruta 'Otro'
            # y su centro de gasto no pudo resolverse en MachineAsset.
            if any(spd.get("cg_incident") for spd in spare_parts_data):
                WorkOrder.objects.filter(pk=work_order.pk).update(has_cg_incident=True)
                logger.warning(
                    "# [Confirm] WorkOrder #%d marcado con has_cg_incident=True: "
                    "al menos un repuesto tiene un CdG no resuelto en catálogo.",
                    work_order.pk,
                )

            logger.info(
                "# [Confirm] WorkOrder #%d creado correctamente. "
                "Entradas: %d | Repuestos: %d.",
                work_order.pk,
                len(entry_lines_data),
                len(spare_parts_data),
            )

            # ----------------------------------------------------------
            # Zero-meter deactivation — inside atomic block.
            # Desactivacion de ceros — dentro del bloque atomico.
            # ----------------------------------------------------------
            import json as _json_mod
            _zero_raw = POST.get("zero_meters_confirmed", "").strip()
            if _zero_raw:
                try:
                    _zero_data = _json_mod.loads(_zero_raw)
                    for _bIdx_str, _meter_list in _zero_data.items():
                        try:
                            _bIdx = int(_bIdx_str)
                        except (ValueError, TypeError):
                            continue
                        _line = created_lines.get(_bIdx)
                        if _line is None:
                            continue
                        _asset = _line.machine_asset
                        _line_fields  = []
                        _asset_fields = []
                        for _m in _meter_list:
                            _name = _m.get("name", "")
                            if "odometer" in _name:
                                _line.odometer_reading = None
                                _line_fields.append("odometer_reading")
                                if _asset and _asset.has_odometer:
                                    _asset.has_odometer = False
                                    _asset_fields.append("has_odometer")
                            elif "engine_hours" in _name:
                                _line.engine_hours_reading = None
                                _line_fields.append("engine_hours_reading")
                                if _asset and _asset.has_engine_hours:
                                    _asset.has_engine_hours = False
                                    _asset_fields.append("has_engine_hours")
                            elif "crane_hours" in _name:
                                _line.crane_hours_reading = None
                                _line_fields.append("crane_hours_reading")
                                if _asset and _asset.has_crane_hours:
                                    _asset.has_crane_hours = False
                                    _asset_fields.append("has_crane_hours")
                        if _line_fields:
                            _line.save(update_fields=_line_fields)
                        if _asset and _asset_fields:
                            _asset.save(update_fields=list(set(_asset_fields)))
                            logger.info(
                                "# [Confirm] MachineAsset %s: flags desactivados: %s.",
                                _asset.code, _asset_fields,
                            )
                except (_json_mod.JSONDecodeError, Exception) as _ze:
                    logger.warning(
                        "# [Confirm] Error procesando zero_meters_confirmed: %s", _ze
                    )

            # Mark first_repair=False for all assets used in this part.
            # Marcar first_repair=False en todos los activos usados en este parte.
            for ld in entry_lines_data:
                _asset = ld.get("machine_asset")
                if _asset and _asset.first_repair:
                    _asset.first_repair = False
                    _asset.save(update_fields=["first_repair"])
                    logger.info(
                        "# [Confirm] MachineAsset %s: first_repair=False.",
                        _asset.code,
                    )

        except Exception as exc:
            logger.error(
                "# [Confirm] Error en persistencia atómica: %s", exc, exc_info=True
            )
            context = self._get_context_base(request)
            context["error"] = (
                f"Error al guardar el parte: {exc}. "
                "Por favor, inténtalo de nuevo o contacta con el administrador."
            )
            return render(request, self.template_name, context)

        # ------------------------------------------------------------------
        # Synchronous Excel generation / Generación síncrona de Excel.
        # ------------------------------------------------------------------
        try:
            generate_work_order_excel(work_order.pk)
            logger.info(
                "# [Confirm] Excel generado correctamente para WorkOrder #%d.",
                work_order.pk,
            )
        except Exception as exc:
            logger.warning(
                "# [Confirm] Excel no generado para WorkOrder #%d: %s.",
                work_order.pk, exc,
            )
            # Non-fatal: the work order is persisted; Excel can be regenerated.
            # No fatal: el parte está persistido; el Excel puede regenerarse.

        # ------------------------------------------------------------------
        # Regla C — Minimum shift coverage (8h) gate.
        # Regla C — Gate de cobertura mínima de jornada (8h).
        #
        # The total delta_hours across all work blocks must sum to >= 8h,
        # OR the operator must have an active WorkerAbsence for work_date.
        # If neither condition is met, the part is rejected with a clear error.
        #
        # La suma de delta_hours de todos los bloques debe ser >= 8h,
        # O el operario debe tener una WorkerAbsence activa para work_date.
        # Si no se cumple ninguna condición, el parte se rechaza con error claro.
        # ------------------------------------------------------------------
        if work_date is not None:
            from decimal import Decimal as _Dec_C2
            from ivr_config.models import WorkerAbsence as _WA_C2
            _total_hours_c2 = sum(
                (ld["delta_hours"] for ld in _parsed_lines if ld.get("delta_hours") is not None),
                _Dec_C2("0"),
            )
            _has_absence_c2 = _WA_C2.objects.filter(
                company_user=cu,
                start_date__lte=work_date,
                end_date__gte=work_date,
            ).exists()
            if _total_hours_c2 < _Dec_C2("8") and not _has_absence_c2:
                _missing_c2 = _Dec_C2("8") - _total_hours_c2
                context = self._get_context_base(request)
                extraction = request.session.get("operator_upload_extraction", {})
                context.update({
                    "error": (
                        f"La jornada del parte suma {_total_hours_c2} h, "
                        f"pero se requieren al menos 8 h. "
                        f"Faltan {_missing_c2} h para completar la jornada. "
                        f"Añade los bloques de trabajo que faltan o registra "
                        f"una ausencia justificada para esta fecha."
                    ),
                    "extraction":          extraction,
                    "fecha":               POST.get("fecha", ""),
                    "uncertain_date":      False,
                    "confidence":          "",
                    "entradas_enriched":   [],
                    "repuestos_enriched":  [],
                    "num_entradas":        0,
                    "num_repuestos":       0,
                    "min_date":            _get_min_allowed_date(cu).isoformat() if _get_min_allowed_date(cu) else "",
                })
                return render(request, self.template_name, context)

        # Clear session extraction data / Limpiar datos de extracción de sesión.
        request.session.pop("operator_upload_extraction", None)
        request.session.modified = True

        # ------------------------------------------------------------------
        # Inter-part overlap validation (R4/R5).
        # Validación de solapamiento inter-parte (R4/R5).
        # ------------------------------------------------------------------
        _inter = validate_inter_overlap(
            company_user          = cu,
            work_date             = work_date,
            blocks                = _blocks,
            exclude_work_order_pk = work_order.pk,
        )

        if _inter.has_overlap:
            # Mark the new work order and all conflicting ones as incident.
            # Marcar el nuevo parte y todos los que solapan como con incidencia.
            WorkOrder.objects.filter(
                pk__in=[work_order.pk] + _inter.conflicting_ids
            ).update(has_overlap_incident=True)
            logger.warning(
                "# [Confirm] Solapamiento inter-parte detectado. "
                "WorkOrder #%d solapa con: %s.",
                work_order.pk,
                _inter.conflicting_ids,
            )
            django_messages.warning(
                request,
                f"Parte #{work_order.pk} guardado con incidencia de solapamiento."
            )
            context = self._get_context_base(request)
            context.update({
                "overlap_incidents": True,
                "new_work_order_pk": work_order.pk,
                "conflicting_parts": [
                    {"pk": pk, "fecha": fecha}
                    for pk, fecha in zip(
                        _inter.conflicting_ids,
                        _inter.conflicting_dates,
                    )
                ],
                "part_saved": True,
            })
            return render(request, self.template_name, context)

        django_messages.success(
            request,
            f"Parte de trabajo registrado correctamente (#{work_order.pk}). "
            f"El informe Excel está disponible en la lista de partes."
        )
        return redirect("/panel/work-orders/")


class WorkOrderEntryFormView(WorkshopRequiredMixin, View):
    """
    Structured web form entry path for work orders (Via A).
    Allows WORKSHOP and ADMIN users to submit a daily work-order part
    directly via a multi-block web form, with no AI dependency and zero cost.

    GET  /panel/operator/form/
         Renders an empty form with one default work block and an empty
         spare-parts section. Additional blocks and spare-part rows can
         be added dynamically via JavaScript.
    POST /panel/operator/form/
         Applies the same integrity gate as WorkOrderEntryConfirmView and,
         on success, atomically persists:
           WorkOrder (status=DONE, source_pdf blank) +
           WorkOrderEntry (page 1, confidence=HIGH) +
           N x WorkOrderEntryLine +
           M x SparePartLine per entry line.
         Generates the Excel report synchronously after persistence.
    ---
    Via de entrada mediante formulario web estructurado para partes de
    trabajo (Via A). Permite a usuarios WORKSHOP y ADMIN enviar un parte
    diario directamente mediante un formulario web multi-bloque, sin
    dependencia de IA y con coste cero.

    GET  /panel/operator/form/
         Renderiza un formulario vacio con un bloque de trabajo por defecto
         y una seccion de repuestos vacia. Bloques y repuestos adicionales
         se anaden dinamicamente via JavaScript.
    POST /panel/operator/form/
         Aplica la misma barrera de integridad que WorkOrderEntryConfirmView
         y, en caso de exito, persiste atomicamente:
           WorkOrder (status=DONE, source_pdf en blanco) +
           WorkOrderEntry (pagina 1, confianza=HIGH) +
           N x WorkOrderEntryLine +
           M x SparePartLine por linea de entrada.
         Genera el informe Excel de forma sincrona tras la persistencia.
    """

    template_name = "panel/operator/form_entry.html"

    def _get_company_user(self, request):
        """
        Returns the CompanyUser for the authenticated request user.
        ---
        Devuelve el CompanyUser del usuario autenticado en la solicitud.
        """
        return request.user.company_user

    def _get_context_base(self, request):
        """
        Returns the base template context with company and navigation data.
        Also provides the list of active MachineAsset records for autocomplete.
        ---
        Devuelve el contexto base con empresa y datos de navegacion.
        Tambien proporciona la lista de MachineAsset activos para autocompletado.
        """
        from fleet.models import MachineAsset
        cu      = self._get_company_user(request)
        company = cu.company
        assets  = list(
            MachineAsset.objects.filter(company=company, is_active=True)
            .order_by("code")
            .values("code", "brand_model")
        )
        return {
            "company":      company,
            "company_user": cu,
            "active_nav":   "operator_dashboard",
            "assets":       assets,
        }

    def get(self, request, *args, **kwargs):
        """
        Renders the work-order entry form.
        In edit mode (wo_pk present in URL kwargs): loads the existing
        unreviewed digital WorkOrder belonging to the operator, pre-fills
        all fields and passes edit_mode=True to the template so the POST
        handler knows to delete the original before creating the new one.
        In create mode: renders an empty form with one default block.
        Passes min_date to the template for client-side date enforcement.
        ---
        Renderiza el formulario de entrada de partes.
        En modo edicion (wo_pk en URL kwargs): carga el WorkOrder digital
        sin revisar del operario, prerellena todos los campos y pasa
        edit_mode=True al template para que el POST elimine el original
        antes de crear el nuevo. En modo creacion: formulario vacio.
        Pasa min_date para validacion de fecha en el lado cliente.
        """
        from work_order_processor.models import WorkOrder as _WO_E, SparePartLine as _SPL_E
        cu       = self._get_company_user(request)
        company  = cu.company
        min_date = _get_min_allowed_date(cu)
        wo_pk    = kwargs.get("wo_pk")

        if wo_pk is not None:
            # Edit mode — load existing unreviewed digital WorkOrder.
            # Modo edicion — cargar WorkOrder digital sin revisar existente.
            try:
                wo_edit = _WO_E.objects.get(
                    pk=wo_pk,
                    company=company,
                    uploaded_by=cu,
                    reviewed=False,
                    source__in=[
                        _WO_E.Source.DIGITAL,
                        _WO_E.Source.GENERATED,
                    ],
                )
            except _WO_E.DoesNotExist:
                django_messages.error(
                    request,
                    "El parte no existe, ya ha sido revisado o no te pertenece.",
                )
                return redirect("/panel/operator/history/")

            # Build enriched entry lines from the existing WorkOrder.
            # Construir lineas enriquecidas desde el WorkOrder existente.
            entries = list(wo_edit.entries.prefetch_related("lines").all())
            first_entry  = entries[0] if entries else None
            fecha_str    = (
                first_entry.work_date.strftime("%Y-%m-%d")
                if first_entry and first_entry.work_date else ""
            )
            entradas_enriched = []
            repuestos_enriched = []
            ridx = 1
            for entry in entries:
                for line in entry.lines.order_by("line_number"):
                    entradas_enriched.append({
                        "idx":               len(entradas_enriched) + 1,
                        "machine_raw":       line.machine_raw or "",
                        "machine_asset":     line.machine_asset,
                        "fault_description": line.fault_description or "",
                        "repair_notes":      line.repair_notes or "",
                        "hc":  line.hc.strftime("%H:%M") if line.hc else "",
                        "hf":  line.hf.strftime("%H:%M") if line.hf else "",
                        "or_val":            line.or_val or "",
                        "flags":             line.flags or [],
                        "odometer_reading":     float(line.odometer_reading) if line.odometer_reading is not None else "",
                        "engine_hours_reading": float(line.engine_hours_reading) if line.engine_hours_reading is not None else "",
                        "crane_hours_reading":  float(line.crane_hours_reading) if line.crane_hours_reading is not None else "",
                    })
                    for spare in _SPL_E.objects.filter(entry_line=line).order_by("line_number"):
                        repuestos_enriched.append({
                            "ridx":         ridx,
                            "referencia":   spare.reference or "",
                            "vehiculo_raw": "",
                            "vehicle_asset": spare.vehicle,
                            "material":     spare.material or "",
                            "unidades":     str(spare.quantity) if spare.quantity is not None else "",
                            "origen":       spare.source or "WAREHOUSE",
                            "proveedor":    spare.supplier or "",
                            "unit_price":   str(spare.unit_price) if spare.unit_price is not None else "",
                            "flags":        spare.flags or [],
                        })
                        ridx += 1

            context = self._get_context_base(request)
            context.update({
                "edit_mode":         True,
                "edit_wo_pk":        wo_pk,
                "num_entradas":      len(entradas_enriched) or 1,
                "num_repuestos":     len(repuestos_enriched),
                "fecha":             fecha_str,
                "entradas_enriched": entradas_enriched,
                "repuestos_enriched": repuestos_enriched,
                "min_date":          min_date.isoformat() if min_date else "",
            })
            return render(request, self.template_name, context)

        # Create mode — empty form.
        # Modo creacion — formulario vacio.
        context = self._get_context_base(request)
        context.update({
            "num_entradas":  1,
            "num_repuestos": 0,
            "fecha":         "",
            "min_date":      min_date.isoformat() if min_date else "",
        })
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        """
        Parses, validates and atomically persists the submitted form data.
        Applies the same integrity gate used by WorkOrderEntryConfirmView.post().
        On validation failure re-renders the form with error context, preserving
        all data already entered by the operator.
        ---
        Parsea, valida y persiste atomicamente los datos del formulario enviado.
        Aplica la misma barrera de integridad que WorkOrderEntryConfirmView.post().
        En caso de fallo re-renderiza el formulario con contexto de error,
        preservando todos los datos introducidos por el operario.
        """
        import json as _json
        from datetime import datetime, time as dt_time
        from decimal import Decimal, InvalidOperation
        from django.db import transaction
        from fleet.models import MachineAsset
        from work_order_processor.models import (
            WorkOrder, WorkOrderEntry, WorkOrderEntryLine, SparePartLine,
        )
        from work_order_processor.services import (
            generate_work_order_excel,
            _normalise_machine_code,
            _compute_delta_hours,
        )

        cu      = self._get_company_user(request)
        company = cu.company
        POST    = request.POST

        # ------------------------------------------------------------------
        # Parse work date / Parsear fecha del parte.
        # ------------------------------------------------------------------
        fecha_str = POST.get("fecha", "").strip()
        work_date = None
        if fecha_str:
            for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                try:
                    work_date = datetime.strptime(fecha_str, fmt).date()
                    break
                except ValueError:
                    continue

        # ------------------------------------------------------------------
        # Min-date gate — work_date must be strictly after the last reviewed
        # entry for this operator (work_date > last_reviewed_date).
        # Barrera de fecha minima — work_date debe ser estrictamente posterior
        # al ultimo parte revisado del operario.
        # ------------------------------------------------------------------
        if work_date is not None:
            _min_date = _get_min_allowed_date(cu)
            if _min_date is not None and work_date < _min_date:
                from datetime import timedelta as _td_fd
                _last_rev = _min_date - _td_fd(days=1)
                context = self._get_context_base(request)
                context.update({
                    "error": (
                        f"No puedes introducir un parte con fecha "
                        f"{work_date.strftime('%d/%m/%Y')}. "
                        f"El ultimo parte revisado es del "
                        f"{_last_rev.strftime('%d/%m/%Y')} y ya ha sido auditado. "
                        f"La fecha minima permitida es "
                        f"{_min_date.strftime('%d/%m/%Y')}."
                    ),
                    "fecha":              fecha_str,
                    "entradas_enriched":  [],
                    "repuestos_enriched": [],
                    "num_entradas":       1,
                    "num_repuestos":      0,
                    "min_date":           _min_date.isoformat(),
                })
                return render(request, self.template_name, context)

        # ------------------------------------------------------------------
        # Edit mode pre-deletion — in edit mode the original WorkOrder must
        # be deleted BEFORE Gate 0 runs, so Gate 0 does not find it as a
        # conflicting duplicate for the same date.
        # Eliminación previa en modo edición — en modo edición el WorkOrder
        # original debe eliminarse ANTES de que Gate 0 se ejecute, para que
        # Gate 0 no lo encuentre como duplicado conflictivo de la misma fecha.
        # ------------------------------------------------------------------
        _edit_wo_pk_pre = POST.get("edit_wo_pk", "").strip()
        if _edit_wo_pk_pre:
            try:
                _wo_orig_pre = WorkOrder.objects.get(
                    pk=int(_edit_wo_pk_pre),
                    company=company,
                    uploaded_by=cu,
                    reviewed=False,
                    source__in=[
                        WorkOrder.Source.DIGITAL,
                        WorkOrder.Source.GENERATED,
                    ],
                )
                _wo_orig_pre.delete()
            except (WorkOrder.DoesNotExist, ValueError):
                # Original already deleted or pk tampered — proceed normally.
                # Original ya eliminado o pk manipulado — continuar normalmente.
                pass

        # ------------------------------------------------------------------
        # Gate 0 — One work order per operator per date (merge flow).
        # Gate 0 — Un parte por operario por fecha (flujo de merge).
        #
        # Before any INSERT, check whether the operator already has an
        # unreviewed digital or generated work order for the submitted date.
        # If so, serialise the incoming lines into the session and redirect
        # to WorkOrderEntryMergeView for conflict resolution.
        #
        # Antes de cualquier INSERT, comprueba si el operario ya tiene un
        # parte digital o generado sin revisar para la fecha enviada. Si es
        # asi, serializa las lineas entrantes en la sesion y redirige a
        # WorkOrderEntryMergeView para resolver el conflicto.
        # ------------------------------------------------------------------
        if work_date is not None:
            from django.urls import reverse as _rev0
            from work_order_processor.models import WorkOrder as _WO0, WorkOrderEntry as _WOE0
            _existing_entry0 = _WOE0.objects.filter(
                work_order__company=company,
                work_order__uploaded_by=cu,
                work_order__source__in=[
                    _WO0.Source.DIGITAL,
                    _WO0.Source.GENERATED,
                ],
                work_order__reviewed=False,
                work_date=work_date,
            ).select_related("work_order").first()

            if _existing_entry0 is not None:
                # Unreviewed duplicate — parse lines, serialise and redirect to merge view.
                # Duplicado sin revisar — parsear lineas, serializar y redirigir a merge view.
                _gate0_lines = _parse_entry_lines_from_post(POST, company)
                _gate0_spare = _parse_spare_parts_from_post(
                    POST, company, entry_lines_data=_gate0_lines
                )
                request.session["pending_merge_lines"] = _serialize_pending_lines(
                    _gate0_lines, _gate0_spare, work_date
                )
                return redirect(
                    _rev0(
                        "panel:operator_merge",
                        kwargs={"entry_pk": _existing_entry0.pk},
                    )
                )

        # ------------------------------------------------------------------
        # Parse and resolve entry lines and spare parts from POST.
        # Parsear y resolver líneas de entrada y repuestos desde POST.
        # Delegated to module-level helpers (DRY). Resolution uses two-pass
        # strategy: raw iexact first (autocomplete), then normalised code
        # (OCR / handwritten). STTView.post() delegates here via MRO.
        # Delegado a helpers de módulo (DRY). La resolución usa estrategia
        # en dos pasadas: iexact sobre raw primero (autocompletado), luego
        # código normalizado (OCR / manuscrito). STTView.post() delega aquí.
        # ------------------------------------------------------------------
        entry_lines_data = _parse_entry_lines_from_post(POST, company)
        spare_parts_data = _parse_spare_parts_from_post(
            POST, company, entry_lines_data=entry_lines_data
        )

        # ------------------------------------------------------------------
        # Integrity validation (sine qua non gate).
        # Validacion de integridad (barrera sine qua non).
        # ------------------------------------------------------------------
        integrity_errors = []

        if not work_date:
            integrity_errors.append(
                "La fecha del parte es obligatoria y debe tener formato DD/MM/AAAA."
            )

        if not entry_lines_data:
            integrity_errors.append("El parte debe contener al menos un bloque de trabajo.")

        for ld in entry_lines_data:
            blk = f"Bloque {ld['line_number']}"
            if not ld["machine_raw"]:
                integrity_errors.append(f"{blk}: el codigo de maquina es obligatorio.")
            elif ld["machine_asset"] is None:
                integrity_errors.append(
                    f"{blk}: el codigo '{ld['machine_raw']}' no se ha podido "
                    f"identificar en el catalogo de flota. Corrigelo antes de guardar."
                )
            if not ld["hc"]:
                integrity_errors.append(f"{blk}: la hora de inicio (H.C.) es obligatoria.")
            if not ld["hf"]:
                integrity_errors.append(f"{blk}: la hora de fin (H.F.) es obligatoria.")
            if ld["hc"] and ld["hf"] and ld["delta_hours"] is not None:
                if ld["delta_hours"] <= 0:
                    integrity_errors.append(
                        f"{blk}: la H.F. debe ser posterior a la H.C. "
                        f"(Delta horas calculado: {ld['delta_hours']})."
                    )
            if not ld["fault_description"]:
                integrity_errors.append(
                    f"{blk}: la descripcion de la averia es obligatoria."
                )

        # Gate 2b — Meter readings: mandatory counter fields per asset flags.
        # If first_repair=True zeros are allowed (baseline setup).
        # If first_repair=False zeros are blocked — reading must be provided.
        # Gate 2b — Contadores: obligatorios segun flags del activo.
        # Si first_repair=True se permiten ceros (primera toma de datos).
        # Si first_repair=False los ceros se bloquean.
        for ld in entry_lines_data:
            if ld["machine_asset"] is not None:
                asset = ld["machine_asset"]
                blk   = f"Bloque {ld['line_number']}"
                if asset.has_odometer:
                    reading = ld.get("odometer_reading")
                    if reading is None:
                        integrity_errors.append(
                            f"{blk}: lectura de km (odometro) obligatoria para {asset.code}."
                        )
                    elif reading == 0 and not asset.first_repair:
                        integrity_errors.append(
                            f"{blk}: la lectura de km no puede ser cero para {asset.code} "
                            f"(ya tiene partes anteriores registrados)."
                        )
                if asset.has_engine_hours:
                    reading = ld.get("engine_hours_reading")
                    if reading is None:
                        integrity_errors.append(
                            f"{blk}: lectura de horometro motor obligatoria para {asset.code}."
                        )
                    elif reading == 0 and not asset.first_repair:
                        integrity_errors.append(
                            f"{blk}: la lectura de horometro motor no puede ser cero "
                            f"para {asset.code} (ya tiene partes anteriores registrados)."
                        )
                if asset.has_crane_hours:
                    reading = ld.get("crane_hours_reading")
                    if reading is None:
                        integrity_errors.append(
                            f"{blk}: lectura de horometro grua obligatoria para {asset.code}."
                        )
                    elif reading == 0 and not asset.first_repair:
                        integrity_errors.append(
                            f"{blk}: la lectura de horometro grua no puede ser cero "
                            f"para {asset.code} (ya tiene partes anteriores registrados)."
                        )

        for spd in spare_parts_data:
            rep = f"Repuesto {spd['line_number']}"
            if not spd["material"]:
                integrity_errors.append(f"{rep}: la descripcion del material es obligatoria.")
            if spd["quantity"] is None or spd["quantity"] <= 0:
                integrity_errors.append(f"{rep}: las unidades deben ser un numero positivo.")

        if integrity_errors:
            entradas_post = [
                {
                    "idx":               ld["line_number"],
                    "machine_raw":       ld["machine_raw"],
                    "machine_asset":     ld["machine_asset"],
                    "fault_description": ld["fault_description"],
                    "repair_notes":        ld["repair_notes"],
                    "hc":  ld["hc"].strftime("%H:%M") if ld["hc"] else "",
                    "hf":  ld["hf"].strftime("%H:%M") if ld["hf"] else "",
                    "or_val":            ld["or_val"],
                    "flags":             [],
                }
                for ld in entry_lines_data
            ]
            repuestos_post = [
                {
                    "ridx":         spd["line_number"],
                    "referencia":   spd["referencia"],
                    "vehiculo_raw": spd["vehiculo_raw"],
                    "vehicle_asset": spd["vehicle_asset"],
                    "material":     spd["material"],
                    "unidades":     str(spd["quantity"]) if spd["quantity"] is not None else "",
                    "origen":       spd["source"],
                    "proveedor":    spd["supplier"],
                    "flags":        [],
                }
                for spd in spare_parts_data
            ]
            context = self._get_context_base(request)
            context.update({
                "error":              " | ".join(integrity_errors),
                "fecha":              fecha_str,
                "entradas_enriched":  entradas_post,
                "repuestos_enriched": repuestos_post,
                "num_entradas":       len(entry_lines_data),
                "num_repuestos":      len(spare_parts_data),
            })
            return render(request, self.template_name, context)

        # ------------------------------------------------------------------
        # Save confirmation gate — form must have been confirmed via modal.
        # Gate de confirmacion — el formulario debe haber pasado por modal.
        # ------------------------------------------------------------------
        if not POST.get("save_confirmed"):
            entradas_post = [
                {
                    "idx":               ld["line_number"],
                    "machine_raw":       ld["machine_raw"],
                    "machine_asset":     ld["machine_asset"],
                    "fault_description": ld["fault_description"],
                    "repair_notes":      ld["repair_notes"],
                    "hc":  ld["hc"].strftime("%H:%M") if ld["hc"] else "",
                    "hf":  ld["hf"].strftime("%H:%M") if ld["hf"] else "",
                    "or_val":            ld["or_val"],
                    "flags":             [],
                }
                for ld in entry_lines_data
            ]
            repuestos_post = [
                {
                    "ridx":          spd["line_number"],
                    "referencia":    spd["referencia"],
                    "vehiculo_raw":  spd["vehiculo_raw"],
                    "vehicle_asset": spd["vehicle_asset"],
                    "material":      spd["material"],
                    "unidades":      str(spd["quantity"]) if spd["quantity"] is not None else "",
                    "origen":        spd["source"],
                    "proveedor":     spd["supplier"],
                    "flags":         [],
                }
                for spd in spare_parts_data
            ]
            context = self._get_context_base(request)
            context.update({
                "error":              None,
                "fecha":              fecha_str,
                "entradas_enriched":  entradas_post,
                "repuestos_enriched": repuestos_post,
                "num_entradas":       len(entry_lines_data),
                "num_repuestos":      len(spare_parts_data),
            })
            return render(request, self.template_name, context)

        # ------------------------------------------------------------------
        # Intra-part validation (R1 overlap, R2 HF>HC, R3 gap).
        # Validación intra-parte (R1 solapamiento, R2 HF>HC, R3 laguna).
        # ------------------------------------------------------------------
        from work_order_processor.validators import (
            run_intra_part_validation,
            parse_blocks_from_post,
            validate_inter_overlap,
            TimeBlock,
        )

        num_entradas_post = int(POST.get("num_entradas", len(entry_lines_data)))
        _blocks = parse_blocks_from_post(POST, num_entradas_post, entry_lines_data=entry_lines_data)
        _intra  = run_intra_part_validation(_blocks)

        if not _intra.ok:
            # Build error message combining blocking errors and non-blocking warnings.
            # Construir mensaje de error combinando errores bloqueantes y avisos no bloqueantes.
            _error_msgs = [e.message for e in _intra.errors]
            if _intra.warnings:
                _error_msgs += [f"[AVISO] {w.message}" for w in _intra.warnings]
            entradas_post = [
                {
                    "idx":               ld["line_number"],
                    "machine_raw":       ld["machine_raw"],
                    "machine_asset":     ld["machine_asset"],
                    "fault_description": ld["fault_description"],
                    "repair_notes":      ld["repair_notes"],
                    "hc":  ld["hc"].strftime("%H:%M") if ld["hc"] else "",
                    "hf":  ld["hf"].strftime("%H:%M") if ld["hf"] else "",
                    "or_val":            ld["or_val"],
                    "flags":             [],
                }
                for ld in entry_lines_data
            ]
            repuestos_post = [
                {
                    "ridx":          spd["line_number"],
                    "referencia":    spd["referencia"],
                    "vehiculo_raw":  spd["vehiculo_raw"],
                    "vehicle_asset": spd["vehicle_asset"],
                    "material":      spd["material"],
                    "unidades":      str(spd["quantity"]) if spd["quantity"] is not None else "",
                    "origen":        spd["source"],
                    "proveedor":     spd["supplier"],
                    "flags":         [],
                }
                for spd in spare_parts_data
            ]
            context = self._get_context_base(request)
            context.update({
                "error":              " | ".join(_error_msgs),
                "fecha":              fecha_str,
                "entradas_enriched":  entradas_post,
                "repuestos_enriched": repuestos_post,
                "num_entradas":       len(entry_lines_data),
                "num_repuestos":      len(spare_parts_data),
            })
            return render(request, self.template_name, context)

        # Non-blocking warnings from R6/R7 (meter reading jumps).
        # Avisos no bloqueantes de R6/R7 (saltos de contador).
        _meter_warnings = [w.message for w in _intra.warnings]

        # ------------------------------------------------------------------
        # Regla C — Minimum shift coverage (8h) gate.
        # Regla C — Gate de cobertura mínima de jornada (8h).
        #
        # The total delta_hours across all work blocks must sum to >= 8h,
        # OR the operator must have an active WorkerAbsence for work_date.
        # If neither condition is met, the part is rejected with a clear error.
        #
        # La suma de delta_hours de todos los bloques debe ser >= 8h,
        # O el operario debe tener una WorkerAbsence activa para work_date.
        # Si no se cumple ninguna condición, el parte se rechaza con error claro.
        # ------------------------------------------------------------------
        if work_date is not None:
            from decimal import Decimal as _Dec_C
            from ivr_config.models import WorkerAbsence as _WA_C
            _total_hours_c = sum(
                (ld["delta_hours"] for ld in entry_lines_data if ld["delta_hours"] is not None),
                _Dec_C("0"),
            )
            _has_absence_c = _WA_C.objects.filter(
                company_user=cu,
                start_date__lte=work_date,
                end_date__gte=work_date,
            ).exists()
            if _total_hours_c < _Dec_C("8") and not _has_absence_c:
                _missing_c = _Dec_C("8") - _total_hours_c
                entradas_post_c = [
                    {
                        "idx":               ld["line_number"],
                        "machine_raw":       ld["machine_raw"],
                        "machine_asset":     ld["machine_asset"],
                        "fault_description": ld["fault_description"],
                        "repair_notes":      ld["repair_notes"],
                        "hc":  ld["hc"].strftime("%H:%M") if ld["hc"] else "",
                        "hf":  ld["hf"].strftime("%H:%M") if ld["hf"] else "",
                        "or_val":            ld["or_val"],
                        "flags":             [],
                    }
                    for ld in entry_lines_data
                ]
                repuestos_post_c = [
                    {
                        "ridx":          spd["line_number"],
                        "referencia":    spd["referencia"],
                        "vehiculo_raw":  spd["vehiculo_raw"],
                        "vehicle_asset": spd["vehicle_asset"],
                        "material":      spd["material"],
                        "unidades":      str(spd["quantity"]) if spd["quantity"] is not None else "",
                        "origen":        spd["source"],
                        "proveedor":     spd["supplier"],
                        "flags":         [],
                    }
                    for spd in spare_parts_data
                ]
                context = self._get_context_base(request)
                context.update({
                    "error": (
                        f"La jornada del parte suma {_total_hours_c} h, "
                        f"pero se requieren al menos 8 h. "
                        f"Faltan {_missing_c} h para completar la jornada. "
                        f"Añade los bloques de trabajo que faltan o registra "
                        f"una ausencia justificada para esta fecha."
                    ),
                    "fecha":              fecha_str,
                    "entradas_enriched":  entradas_post_c,
                    "repuestos_enriched": repuestos_post_c,
                    "num_entradas":       len(entry_lines_data),
                    "num_repuestos":      len(spare_parts_data),
                    "min_date":           _get_min_allowed_date(cu).isoformat() if _get_min_allowed_date(cu) else "",
                })
                return render(request, self.template_name, context)

        # ------------------------------------------------------------------
        # Atomic persistence / Persistencia atomica.
        # ------------------------------------------------------------------
        # Edit mode — delete original WorkOrder before creating the new one.
        # Modo edicion — eliminar WorkOrder original antes de crear el nuevo.
        edit_wo_pk = POST.get("edit_wo_pk", "").strip()
        if edit_wo_pk:
            try:
                _wo_orig = WorkOrder.objects.get(
                    pk=int(edit_wo_pk),
                    company=company,
                    uploaded_by=cu,
                    reviewed=False,
                    source__in=[
                        WorkOrder.Source.DIGITAL,
                        WorkOrder.Source.GENERATED,
                    ],
                )
                _wo_orig.delete()
            except (WorkOrder.DoesNotExist, ValueError):
                # Original already deleted or pk tampered — proceed normally.
                # Original ya eliminado o pk manipulado — continuar normalmente.
                pass

        try:
            with transaction.atomic():
                worker_name = (
                    cu.user.get_full_name() or cu.user.username
                ).upper()

                work_order = WorkOrder(
                    company         = company,
                    uploaded_by     = cu,
                    source          = WorkOrder.Source.DIGITAL,
                    status          = WorkOrder.Status.DONE,
                    total_pages     = 1,
                    processed_pages = 1,
                    reviewed        = False,
                )
                # Build a human-readable synthetic filename mirroring the
                # historical pipeline pattern: WORKER_DD-MM-AAAA.pdf.
                # No real file is created — only the FileField name string
                # is populated so the list view renders a meaningful label.
                #
                # Construir un nombre de fichero sintético legible siguiendo
                # el patrón del pipeline histórico: TRABAJADOR_DD-MM-AAAA.pdf.
                # No se crea ningún fichero real — sólo se asigna la cadena
                # al campo name del FileField para que el listado sea legible.
                date_tag = (
                    work_date.strftime("%d-%m-%Y") if work_date else "SIN-FECHA"
                )
                synthetic_name = f"{worker_name}_{date_tag}.pdf"

                work_order.source_pdf.name = synthetic_name
                work_order.save()

                entry = WorkOrderEntry.objects.create(
                    work_order            = work_order,
                    page_number           = 1,
                    worker_name           = worker_name,
                    work_date             = work_date,
                    uncertain_date        = False,
                    extraction_confidence = WorkOrderEntry.Confidence.HIGH,
                    raw_gemini_response   = None,
                )

                created_lines = {}
                for ld in entry_lines_data:
                    line = WorkOrderEntryLine.objects.create(
                        entry                = entry,
                        line_number          = ld["line_number"],
                        machine_asset        = ld["machine_asset"],
                        machine_raw          = ld["machine_raw"],
                        machine_norm         = ld["machine_norm"],
                        fault_description    = ld["fault_description"],
                        repair_notes         = ld["repair_notes"],
                        hc                   = ld["hc"],
                        hf                   = ld["hf"],
                        or_val               = ld["or_val"],
                        delta_hours          = ld["delta_hours"],
                        flags                = ld["flags"],
                        odometer_reading     = ld.get("odometer_reading"),
                        engine_hours_reading = ld.get("engine_hours_reading"),
                        crane_hours_reading  = ld.get("crane_hours_reading"),
                    )
                    created_lines[ld["line_number"]] = line

                for spd in spare_parts_data:
                    # Resolve target line: always use first created line since
                    # entry_idx sentinel was removed in S012 refactor.
                    # Resolver línea destino: usar siempre la primera línea creada
                    # ya que el centinela entry_idx fue eliminado en el refactor S012.
                    target_line = next(iter(created_lines.values()), None)
                    if target_line is None:
                        continue
                    SparePartLine.objects.create(
                        entry_line  = target_line,
                        line_number = spd["line_number"],
                        reference   = spd["referencia"],
                        vehicle     = spd["vehicle_asset"],
                        material    = spd["material"],
                        quantity    = spd["quantity"],
                        source      = spd["source"],
                        supplier    = spd["supplier"],
                        flags       = spd["flags"],
                    )

            # Activate has_cg_incident if any spare part used the 'Otro' path
            # and its cost centre could not be resolved in MachineAsset.
            # Activar has_cg_incident si algún repuesto usó la ruta 'Otro'
            # y su centro de gasto no pudo resolverse en MachineAsset.
            if any(spd.get("cg_incident") for spd in spare_parts_data):
                WorkOrder.objects.filter(pk=work_order.pk).update(has_cg_incident=True)
                logger.warning(
                    "# [FormView] WorkOrder #%d marcado con has_cg_incident=True: "
                    "al menos un repuesto tiene un CdG no resuelto en catálogo.",
                    work_order.pk,
                )

            logger.info(
                "# [FormView] WorkOrder #%d creado correctamente (Via A). "
                "Bloques: %d | Repuestos: %d.",
                work_order.pk,
                len(entry_lines_data),
                len(spare_parts_data),
            )

            # ----------------------------------------------------------
            # Zero-meter deactivation — inside atomic block.
            # Desactivacion de ceros — dentro del bloque atomico.
            # ----------------------------------------------------------
            import json as _json_mod
            _zero_raw = POST.get("zero_meters_confirmed", "").strip()
            if _zero_raw:
                try:
                    _zero_data = _json_mod.loads(_zero_raw)
                    for _bIdx_str, _meter_list in _zero_data.items():
                        try:
                            _bIdx = int(_bIdx_str)
                        except (ValueError, TypeError):
                            continue
                        _line = created_lines.get(_bIdx)
                        if _line is None:
                            continue
                        _asset = _line.machine_asset
                        _line_fields  = []
                        _asset_fields = []
                        for _m in _meter_list:
                            _name = _m.get("name", "")
                            if "odometer" in _name:
                                _line.odometer_reading = None
                                _line_fields.append("odometer_reading")
                                if _asset and _asset.has_odometer:
                                    _asset.has_odometer = False
                                    _asset_fields.append("has_odometer")
                            elif "engine_hours" in _name:
                                _line.engine_hours_reading = None
                                _line_fields.append("engine_hours_reading")
                                if _asset and _asset.has_engine_hours:
                                    _asset.has_engine_hours = False
                                    _asset_fields.append("has_engine_hours")
                            elif "crane_hours" in _name:
                                _line.crane_hours_reading = None
                                _line_fields.append("crane_hours_reading")
                                if _asset and _asset.has_crane_hours:
                                    _asset.has_crane_hours = False
                                    _asset_fields.append("has_crane_hours")
                        if _line_fields:
                            _line.save(update_fields=_line_fields)
                        if _asset and _asset_fields:
                            _asset.save(update_fields=list(set(_asset_fields)))
                            logger.info(
                                "# [FormView] MachineAsset %s: flags desactivados: %s.",
                                _asset.code, _asset_fields,
                            )
                except (_json_mod.JSONDecodeError, Exception) as _ze:
                    logger.warning(
                        "# [FormView] Error procesando zero_meters_confirmed: %s", _ze
                    )

            # Mark first_repair=False for all assets used in this part.
            # Marcar first_repair=False en todos los activos usados en este parte.
            for ld in entry_lines_data:
                _asset = ld.get("machine_asset")
                if _asset and _asset.first_repair:
                    _asset.first_repair = False
                    _asset.save(update_fields=["first_repair"])
                    logger.info(
                        "# [FormView] MachineAsset %s: first_repair=False.",
                        _asset.code,
                    )

        except Exception as exc:
            logger.error(
                "# [FormView] Error en persistencia atomica: %s", exc, exc_info=True
            )
            context = self._get_context_base(request)
            context["error"] = (
                f"Error al guardar el parte: {exc}. "
                "Por favor, intentalo de nuevo o contacta con el administrador."
            )
            return render(request, self.template_name, context)

        # ------------------------------------------------------------------
        # Synchronous Excel generation / Generacion sincrona de Excel.
        # ------------------------------------------------------------------
        try:
            generate_work_order_excel(work_order.pk)
            logger.info(
                "# [FormView] Excel generado correctamente para WorkOrder #%d.",
                work_order.pk,
            )
        except Exception as exc:
            logger.warning(
                "# [FormView] Excel no generado para WorkOrder #%d: %s.",
                work_order.pk, exc,
            )

        # ------------------------------------------------------------------
        # Inter-part overlap validation (R4/R5).
        # Validación de solapamiento inter-parte (R4/R5).
        # ------------------------------------------------------------------
        _inter = validate_inter_overlap(
            company_user          = cu,
            work_date             = work_date,
            blocks                = _blocks,
            exclude_work_order_pk = work_order.pk,
        )

        if _inter.has_overlap:
            # Mark the new work order and all conflicting ones as incident.
            # Marcar el nuevo parte y todos los que solapan como con incidencia.
            WorkOrder.objects.filter(
                pk__in=[work_order.pk] + _inter.conflicting_ids
            ).update(has_overlap_incident=True)
            logger.warning(
                "# [FormView] Solapamiento inter-parte detectado. "
                "WorkOrder #%d solapa con: %s.",
                work_order.pk,
                _inter.conflicting_ids,
            )
            django_messages.warning(
                request,
                f"Parte #{work_order.pk} guardado con incidencia de solapamiento."
            )
            context = self._get_context_base(request)
            context.update({
                "overlap_incidents": True,
                "new_work_order_pk": work_order.pk,
                "conflicting_parts": [
                    {"pk": pk, "fecha": fecha}
                    for pk, fecha in zip(
                        _inter.conflicting_ids,
                        _inter.conflicting_dates,
                    )
                ],
                "part_saved": True,
            })
            return render(request, self.template_name, context)

        if _meter_warnings:
            django_messages.warning(
                request,
                "Parte guardado con avisos de contadores: " + " | ".join(_meter_warnings),
            )

        django_messages.success(
            request,
            f"Parte de trabajo registrado correctamente (#{work_order.pk}). "
            f"El informe Excel está disponible en la lista de partes."
        )
        return redirect("/panel/work-orders/")


class WorkOrderEntrySTTView(WorkshopRequiredMixin, View):
    """
    Speech-to-text dictation entry path for work orders (Via B).
    Allows WORKSHOP and ADMIN users to dictate a daily work-order part using
    the browser-native Web Speech API (Chrome/Edge). The recognised text is
    parsed client-side by a JavaScript parser that pre-fills the standard
    form fields. The operator reviews and corrects the pre-filled form before
    submitting. On POST, applies exactly the same integrity gate and atomic
    persistence logic as WorkOrderEntryFormView.

    GET  /panel/operator/stt/
         Renders the dictation template with an empty, pre-fillable form.
         No server-side processing is performed on GET.
    POST /panel/operator/stt/
         Reuses WorkOrderEntryFormView.post() logic verbatim:
           - Parses fecha, entry lines and spare-part lines from POST.
           - Applies the three-gate integrity barrier (sine qua non).
           - On success, atomically persists WorkOrder + WorkOrderEntry +
             N x WorkOrderEntryLine + M x SparePartLine and generates Excel.
           - On failure, re-renders stt_entry.html with error context,
             preserving all data already entered by the operator.
    ---
    Vía de entrada por dictado de voz para partes de trabajo (Vía B).
    Permite a usuarios WORKSHOP y ADMIN dictar un parte diario usando la
    Web Speech API nativa del navegador (Chrome/Edge). El texto reconocido
    es parseado en cliente por un parser JavaScript que pre-rellena los
    campos estándar del formulario. El operario revisa y corrige antes de
    enviar. En POST aplica exactamente la misma barrera de integridad y
    lógica de persistencia atómica que WorkOrderEntryFormView.

    GET  /panel/operator/stt/
         Renderiza el template de dictado con un formulario vacío y pre-rellenable.
         No se realiza ningún procesamiento server-side en GET.
    POST /panel/operator/stt/
         Reutiliza verbatim la lógica de WorkOrderEntryFormView.post():
           - Parsea fecha, bloques de entrada y repuestos del POST.
           - Aplica la barrera de integridad de tres gates (sine qua non).
           - En caso de éxito, persiste atómicamente WorkOrder + WorkOrderEntry +
             N x WorkOrderEntryLine + M x SparePartLine y genera el Excel.
           - En caso de fallo, re-renderiza stt_entry.html con contexto de error,
             preservando todos los datos introducidos por el operario.
    """

    template_name = "panel/operator/stt_entry.html"

    def _get_company_user(self, request):
        """
        Returns the CompanyUser for the authenticated request user.
        ---
        Devuelve el CompanyUser del usuario autenticado en la solicitud.
        """
        return request.user.company_user

    def _get_context_base(self, request):
        """
        Returns the base template context with company and navigation data.
        Also provides the list of active MachineAsset records for autocomplete.
        Identical to WorkOrderEntryFormView._get_context_base().
        ---
        Devuelve el contexto base con empresa y datos de navegación.
        También proporciona la lista de MachineAsset activos para autocompletado.
        Idéntico a WorkOrderEntryFormView._get_context_base().
        """
        from fleet.models import MachineAsset
        cu      = self._get_company_user(request)
        company = cu.company
        assets  = list(
            MachineAsset.objects.filter(company=company, is_active=True)
            .order_by("code")
            .values("code", "brand_model")
        )
        return {
            "company":      company,
            "company_user": cu,
            "active_nav":   "operator_dashboard",
            "assets":       assets,
        }

    def get(self, request, *args, **kwargs):
        """
        Renders the STT dictation template with an empty pre-fillable form.
        One default work block is included server-side; the JS parser may
        populate it after the operator completes the dictation.
        ---
        Renderiza el template de dictado STT con un formulario vacío y
        pre-rellenable. Un bloque de trabajo por defecto se incluye desde
        el servidor; el parser JS puede poblarlo tras el dictado del operario.
        """
        context = self._get_context_base(request)
        context.update({
            "num_entradas":  1,
            "num_repuestos": 0,
            "fecha":         "",
        })
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        """
        Delegates entirely to WorkOrderEntryFormView.post(), which contains
        the canonical implementation of the three-gate integrity barrier and
        atomic persistence block shared by both Via A (Form) and Via B (STT).
        The only behavioural difference between the two views is the template
        rendered on validation failure — WorkOrderEntryFormView uses
        form_entry.html while this view uses stt_entry.html. That difference
        is handled transparently because both views define self.template_name
        and the FormView.post() renders via self.template_name.

        Since STTView inherits WorkshopRequiredMixin and defines its own
        _get_company_user() and _get_context_base() — identical to FormView —
        the delegation is safe: FormView.post() calls self._get_company_user()
        and self._get_context_base(), which resolve to STTView's own methods
        via normal MRO, so the correct template and context are used throughout.
        ---
        Delega completamente en WorkOrderEntryFormView.post(), que contiene la
        implementación canónica de la barrera de integridad de tres gates y el
        bloque de persistencia atómica compartidos por la Vía A (Form) y la
        Vía B (STT). La única diferencia de comportamiento entre ambas vistas
        es el template renderizado en fallo de validación — WorkOrderEntryFormView
        usa form_entry.html mientras esta vista usa stt_entry.html. Esa diferencia
        se gestiona de forma transparente porque ambas vistas definen
        self.template_name y FormView.post() renderiza mediante self.template_name.

        Como STTView hereda WorkshopRequiredMixin y define sus propios métodos
        _get_company_user() y _get_context_base() — idénticos a los de FormView —
        la delegación es segura: FormView.post() llama a self._get_company_user()
        y self._get_context_base(), que resuelven a los métodos propios de STTView
        vía MRO normal, por lo que el template y contexto correctos se usan en
        todo momento.
        """
        return WorkOrderEntryFormView.post(self, request, *args, **kwargs)


class WorkOrderEntrySTTExtractView(WorkshopRequiredMixin, View):
    """
    JSON endpoint that receives a raw speech-to-text transcript and uses
    Gemini Flash (text-only, Vertex AI) to extract structured work-order
    fields from natural-language Spanish input.

    POST /panel/operator/stt/extract/
         Body (JSON): {"transcript": "<text>"}
         Response (JSON):
           {
             "fecha":              "DD/MM/AAAA" | "",
             "machine_raw":        "<code>" | "",
             "hc":                 "HH:MM" | "",
             "hf":                 "HH:MM" | "",
             "fault_description": "<text>" | "",
             "repair_notes":         "<text>" | "",
             "or_val":             "<text>" | ""
           }
         On extraction failure returns the same schema with all empty strings
         so the client can still render the form for manual correction.
    ---
    Endpoint JSON que recibe una transcripción de dictado por voz y utiliza
    Gemini Flash (solo texto, Vertex AI) para extraer campos estructurados
    de un parte de trabajo desde entrada en español coloquial.

    POST /panel/operator/stt/extract/
         Cuerpo (JSON): {"transcript": "<texto>"}
         Respuesta (JSON): misma estructura que arriba.
         En caso de fallo devuelve el mismo esquema con cadenas vacías para
         que el cliente pueda renderizar el formulario para corrección manual.
    """

    # Extraction prompt for natural-language Spanish work-order dictation.
    # Prompt de extracción para dictado de parte de trabajo en español coloquial.
    _STT_EXTRACT_PROMPT = """Eres un asistente especializado en extraer datos de partes de trabajo dictados
por voz en español coloquial por operarios de taller de maquinaria industrial.

El operario puede usar lenguaje informal, números hablados (ocho, catorce, veinte),
meses en letra o número, abreviaturas y frases coloquiales. Tu tarea es interpretar
el texto con máxima tolerancia y extraer los siguientes campos:

- fecha: fecha del parte en formato DD/MM/AAAA. Acepta "veinte del cuatro de 2026",
  "20/4/2026", "20 de abril de 2026", "el dia 3 de mayo de 2026", etc.
  Si no puedes determinarla con certeza, devuelve cadena vacía.
- machine_raw: código alfanumérico de la máquina. Puede aparecer como "A-44",
  "A44", "vehículo A 44", "maquina JD5090R", etc. Devuelve solo el código,
  sin la keyword. Si el reconocedor de voz separa letras y números con espacio
  (ej: "a 44"), reconstruye el código sin espacio ("A44").
- hc: hora de inicio en formato HH:MM. Acepta "de 8 a 14", "hora de inicio 8",
  "desde las ocho", "8:00", etc. Si no puedes determinarla, devuelve cadena vacía.
- hf: hora de fin en formato HH:MM. Mismas variantes que hc.
- fault_description: descripción de la avería o tarea. Texto limpio en español,
  sin keywords ni relleno (elimina frases como "descripción de la avería",
  "parte de repair_noteses", "orden de reparación", "ahora", etc.).
- repair_notes: descripción de la reparación realizada. Texto limpio. Si no se
  menciona explícitamente, devuelve cadena vacía.
- or_val: referencia de la orden de reparación (O.R.). Puede ser un nombre propio,
  número o código. Si no se menciona, devuelve cadena vacía.

REGLAS OBLIGATORIAS:
1. Responde ÚNICAMENTE con un objeto JSON válido. Sin texto adicional, sin bloques
   de código markdown, sin explicaciones.
2. Todos los campos son obligatorios en la respuesta. Si no puedes extraer un valor,
   usa cadena vacía "".
3. Las horas siempre en formato HH:MM con ceros a la izquierda (08:00, 14:00).
4. La fecha siempre en formato DD/MM/AAAA con ceros a la izquierda (20/04/2026).
5. machine_raw siempre en MAYÚSCULAS.

Formato de respuesta exacto:
{
  "fecha": "",
  "machine_raw": "",
  "hc": "",
  "hf": "",
  "fault_description": "",
  "repair_notes": "",
  "or_val": ""
}

Transcripción del operario:
"""

    def post(self, request, *args, **kwargs):
        """
        Receives a plain-text Spanish transcript from the browser's Web Speech
        API via a JSON body {"transcript": "<text>"}, sends it to Gemini 2.5
        Flash (text-only, Vertex AI) and returns a structured JSON with the
        extracted work-order fields.

        This is intentionally text-in / JSON-out: the browser transcribes the
        audio natively (free, no server round-trip for audio bytes) and only
        the resulting text string reaches the server. Gemini handles all the
        semantic extraction — date parsing, machine code normalisation, time
        range detection, fault description cleanup — with far higher accuracy
        than a client-side JS parser.

        POST /panel/operator/stt/extract/
             Body (JSON): {"transcript": "<texto dictado por el operario>"}
             Response (JSON):
               {
                 "fecha":              "DD/MM/AAAA" | "",
                 "machine_raw":        "<codigo>" | "",
                 "hc":                 "HH:MM" | "",
                 "hf":                 "HH:MM" | "",
                 "fault_description": "<texto>" | "",
                 "repair_notes":         "<texto>" | "",
                 "or_val":             "<texto>" | ""
               }
             On any failure returns the same schema with all empty strings so
             the client can still render the form for manual correction.
        ---
        Recibe una transcripción de texto plano en español desde la Web Speech
        API del navegador vía cuerpo JSON {"transcript": "<texto>"}, la envía a
        Gemini 2.5 Flash (solo texto, Vertex AI) y devuelve un JSON estructurado
        con los campos del parte de trabajo extraídos.

        El diseño es texto-entrada / JSON-salida: el navegador transcribe el
        audio de forma nativa (gratuita, sin envío de bytes de audio al servidor)
        y solo la cadena de texto resultante llega al servidor. Gemini gestiona
        toda la extracción semántica — parsing de fechas, normalización de códigos
        de máquina, detección de rangos horarios, limpieza de descripción de avería
        — con una precisión muy superior a la de un parser JS en cliente.

        En cualquier fallo devuelve el mismo esquema con cadenas vacías para
        que el cliente pueda renderizar el formulario para corrección manual.
        """
        import json as _json
        import re as _re
        from django.http import JsonResponse
        from work_order_processor.services import _get_gemini_client, _GEMINI_MODEL
        from google.genai.types import GenerateContentConfig, HttpOptions, ThinkingConfig

        _EMPTY = {
            "fecha": "", "machine_raw": "", "hc": "", "hf": "",
            "fault_description": "", "repair_notes": "", "or_val": "",
        }

        # JSON schema for structured output — guarantees field presence and types.
        # Esquema JSON para salida estructurada — garantiza presencia y tipo de campos.
        _RESPONSE_SCHEMA = {
            "type": "object",
            "properties": {
                "fecha":              {"type": "string"},
                "machine_raw":        {"type": "string"},
                "hc":                 {"type": "string"},
                "hf":                 {"type": "string"},
                "fault_description": {"type": "string"},
                "repair_notes":         {"type": "string"},
                "or_val":             {"type": "string"},
            },
            "required": [
                "fecha", "machine_raw", "hc", "hf",
                "fault_description", "repair_notes", "or_val",
            ],
        }

        # Parse JSON body — reject requests without a non-empty transcript.
        # Parsear cuerpo JSON — rechazar peticiones sin transcripción no vacía.
        try:
            body       = _json.loads(request.body)
            transcript = (body.get("transcript") or "").strip()
        except (_json.JSONDecodeError, AttributeError):
            return JsonResponse({"error": "Cuerpo JSON inválido."}, status=400)

        if not transcript:
            return JsonResponse({"error": "La transcripción está vacía."}, status=400)

        logger.info(
            "# [STTExtract] Transcripción recibida (%d chars): %s…",
            len(transcript),
            transcript[:120],
        )

        try:
            client = _get_gemini_client()

            response = client.models.generate_content(
                model    = _GEMINI_MODEL,
                contents = [self._STT_EXTRACT_PROMPT + transcript],
                config   = GenerateContentConfig(
                    http_options       = HttpOptions(timeout=30_000),
                    response_mime_type = "application/json",
                    response_schema    = _RESPONSE_SCHEMA,
                    thinking_config    = ThinkingConfig(thinking_budget=0),
                    temperature        = 0.0,
                    max_output_tokens  = 512,
                ),
            )

            # response_mime_type + response_schema guarantee pure structured JSON
            # without markdown fences and with all fields present.
            # thinking_budget=0 disables thinking for this simple extraction task,
            # preventing thinking tokens from consuming the output token budget.
            #
            # response_mime_type + response_schema garantizan JSON estructurado puro
            # sin bloques markdown y con todos los campos presentes.
            # thinking_budget=0 desactiva el thinking para esta tarea simple de
            # extracción, evitando que los tokens de pensamiento consuman el budget.
            raw_text  = response.text.strip()
            extracted = _json.loads(raw_text)
            result    = {k: str(extracted.get(k, "") or "").strip() for k in _EMPTY}

            logger.info(
                "# [STTExtract] Extracción Gemini completada. "
                "maquina=%s | fecha=%s | hc=%s | hf=%s.",
                result["machine_raw"], result["fecha"],
                result["hc"], result["hf"],
            )
            return JsonResponse(result)

        except Exception as exc:
            logger.error(
                "# [STTExtract] Error en extracción Gemini texto: %s", exc, exc_info=True
            )
            return JsonResponse(_EMPTY)


class WorkOrderEntryHistoryView(WorkshopRequiredMixin, View):
    """
    Four-tab personal history view for WORKSHOP role operators.
    ADMIN and SUPERVISOR are automatically redirected to WorkOrderAdminHistoryView.

    Tabs:
      1 — Periodo actual  : work orders within the operator's active WorkPeriod
                            (end_date=None or end_date >= today). Total period hours.
                            Read-only.
      2 — Histórico       : work orders from closed WorkPeriod records, grouped
                            by period descending. Read-only.
      3 — Horas extra     : calculation of overtime for the active period.
                            Formula: worked_hours - (working_days * 8).
                            working_days = Mon–Fri count from start_date to today.
                            Read-only viewer, no editing.
      4 — Ausencias       : WorkerAbsence records for the authenticated operator.
                            Read-only viewer (type, dates, notes).

    GET /panel/operator/history/

    ---

    Vista de historial personal de cuatro pestanas para operarios con rol WORKSHOP.
    ADMIN y SUPERVISOR son redirigidos automaticamente a WorkOrderAdminHistoryView.

    Pestanas:
      1 — Periodo actual  : partes del WorkPeriod activo del operario
                            (end_date=None o end_date >= hoy). Horas totales del periodo.
                            Solo lectura.
      2 — Historico       : partes de WorkPeriod cerrados agrupados por periodo
                            en orden descendente. Solo lectura.
      3 — Horas extra     : calculo de horas extra para el periodo activo.
                            Formula: horas_trabajadas - (dias_laborables * 8).
                            dias_laborables = conteo lun–vie desde start_date a hoy.
                            Solo visor, sin edicion.
      4 — Ausencias       : registros WorkerAbsence del operario autenticado.
                            Solo lectura (tipo, fechas, notas).

    GET /panel/operator/history/
    """

    template_name = "panel/operator/history.html"

    def _get_own_presence(self, company_user):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

    def _count_working_days(self, start_date, end_date):
        """
        Counts Monday–Friday days (working days) in the closed interval
        [start_date, end_date]. Both dates are inclusive.
        Returns 0 if start_date > end_date.
        ---
        Cuenta los dias de lunes a viernes (dias laborables) en el intervalo
        cerrado [start_date, end_date]. Ambas fechas son inclusivas.
        Devuelve 0 si start_date > end_date.
        """
        from datetime import timedelta
        count   = 0
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:   # 0=Mon … 4=Fri / 0=Lun … 4=Vie
                count += 1
            current += timedelta(days=1)
        return count

    def _enrich_work_orders_for_period(self, qs):
        """
        Converts a WorkOrder queryset into a list of enriched dicts for period
        tab rendering. Each dict includes pk, fecha, num_bloques, horas_totales,
        reviewed. Accumulates total hours as Decimal.
        ---
        Convierte un queryset de WorkOrder en una lista de dicts enriquecidos
        para el renderizado de la pestana de periodo. Cada dict incluye pk, fecha,
        num_bloques, horas_totales, reviewed. Acumula horas totales como Decimal.
        """
        from decimal import Decimal
        result      = []
        total_hours = Decimal("0")
        for wo in qs:
            entries_list  = list(wo.entries.all())
            first_entry   = entries_list[0] if entries_list else None
            work_date     = first_entry.work_date if first_entry else None
            num_bloques   = sum(entry.lines.count() for entry in entries_list)
            horas_totales = sum(
                (line.delta_hours
                 for entry in entries_list
                 for line in entry.lines.all()
                 if line.delta_hours is not None),
                Decimal("0"),
            )
            total_hours += horas_totales
            result.append({
                "pk":                  wo.pk,
                "fecha":               work_date,
                "num_bloques":         num_bloques,
                "horas_totales":       horas_totales,
                "reviewed":            wo.reviewed,
                "has_overlap_incident": wo.has_overlap_incident,
                "source":              wo.source,
            })
        return result, total_hours

    def get(self, request, *args, **kwargs):
        """
        Builds the four-tab WORKSHOP history and renders the template.
        ADMIN and SUPERVISOR are redirected immediately to the admin history view.
        ---
        Construye el historial de cuatro pestanas WORKSHOP y renderiza el template.
        ADMIN y SUPERVISOR son redirigidos inmediatamente a la vista de historial
        de administrador.
        """
        from decimal import Decimal
        from datetime import date as dt_date
        from django.urls import reverse
        from ivr_config.models import WorkerAbsence, WorkPeriod

        cu      = request.user.company_user
        company = cu.company
        role    = cu.role
        today   = dt_date.today()

        # ADMIN and SUPERVISOR always use the dedicated admin history view.
        # ADMIN y SUPERVISOR siempre usan la vista de historial de administrador.
        if role in (CompanyUser.ROLE_ADMIN, CompanyUser.ROLE_SUPERVISOR):
            return redirect(reverse("panel:work_order_admin_history"))

        active_tab = request.GET.get("tab", "current_period")

        # ------------------------------------------------------------------
        # Base queryset helper — helper de queryset base.
        # Scoped to DIGITAL and GENERATED sources only — PDF_UPLOAD parts
        # belong exclusively to the SUPERVISOR/ADMIN WorkOrderListView.
        # Restringido a origenes DIGITAL y GENERATED — los partes PDF_UPLOAD
        # pertenecen exclusivamente a la WorkOrderListView de SUPERVISOR/ADMIN.
        # ------------------------------------------------------------------
        def _base_qs():
            return (
                WorkOrder.objects
                .filter(
                    company=company,
                    uploaded_by=cu,
                    source__in=[
                        WorkOrder.Source.DIGITAL,
                        WorkOrder.Source.GENERATED,
                    ],
                )
                .prefetch_related(
                    Prefetch(
                        "entries",
                        queryset=WorkOrderEntry.objects.prefetch_related("lines"),
                    )
                )
                .order_by("entries__work_date")
            )

        # ------------------------------------------------------------------
        # Tab 1 — Periodo actual / Current period.
        # ------------------------------------------------------------------
        active_period = (
            WorkPeriod.objects
            .filter(
                company_user=cu,
            )
            .filter(
                Q(end_date__isnull=True) | Q(end_date__gte=today)
            )
            .order_by("-start_date")
            .first()
        )

        current_period_list  = []
        current_period_hours = Decimal("0")

        if active_period:
            # Active period exists — filter to its date range.
            # Periodo activo existente — filtrar a su rango de fechas.
            period_qs = _base_qs().filter(
                entries__work_date__gte=active_period.start_date,
            )
            if active_period.end_date:
                period_qs = period_qs.filter(
                    entries__work_date__lte=active_period.end_date,
                )
            period_qs = period_qs.distinct()
        else:
            # No active period configured yet — show all operator parts as
            # a fallback so the operator is not left with an empty screen.
            # Sin periodo activo configurado — mostrar todos los partes del
            # operario como fallback para no dejar la pantalla vacía.
            period_qs = _base_qs().distinct()

        current_period_list, current_period_hours = (
            self._enrich_work_orders_for_period(period_qs)
        )

        # ------------------------------------------------------------------
        # Tab 2 — Histórico por periodos cerrados / Closed periods history.
        # ------------------------------------------------------------------
        closed_periods = (
            WorkPeriod.objects
            .filter(company_user=cu, end_date__isnull=False, end_date__lt=today)
            .order_by("-start_date")
        )

        period_groups = []
        for period in closed_periods:
            pqs = _base_qs().filter(
                entries__work_date__gte=period.start_date,
                entries__work_date__lte=period.end_date,
            ).distinct()
            wo_list, period_hours = self._enrich_work_orders_for_period(pqs)
            period_label = (
                period.label
                or f"{period.start_date:%d/%m/%Y} – {period.end_date:%d/%m/%Y}"
            )
            period_groups.append({
                "label":       period_label,
                "total_hours": period_hours,
                "work_orders": wo_list,
            })

        # ------------------------------------------------------------------
        # Tab 3 — Horas extra / Overtime calculation.
        # ------------------------------------------------------------------
        overtime_hours    = Decimal("0")
        working_days_count = 0

        if active_period:
            period_end_for_calc = (
                active_period.end_date
                if active_period.end_date and active_period.end_date < today
                else today
            )
            working_days_count = self._count_working_days(
                active_period.start_date, period_end_for_calc
            )
            expected_hours = Decimal(working_days_count) * Decimal("8")
            overtime_hours = current_period_hours - expected_hours

        # ------------------------------------------------------------------
        # Tab 4 — Ausencias del operario / Operator absences (read-only).
        # ------------------------------------------------------------------
        absences = (
            WorkerAbsence.objects
            .filter(company_user=cu)
            .order_by("-start_date")
        )

        context = {
            "company":               company,
            "company_user":          cu,
            "own_presence":          self._get_own_presence(cu),
            "active_nav":            "operator_history",
            "active_tab":            active_tab,
            # Tab 1
            "active_period":         active_period,
            "current_period_list":   current_period_list,
            "current_period_hours":  current_period_hours,
            # Tab 2
            "period_groups":         period_groups,
            # Tab 3 — overtime_worked_hours is the raw sum used in the template
            # formula display; overtime_hours is the net surplus/deficit.
            # Tab 3 — overtime_worked_hours es la suma bruta usada en el template;
            # overtime_hours es el superávit/déficit neto.
            "working_days_count":    working_days_count,
            "overtime_hours":        overtime_hours,
            "overtime_worked_hours": current_period_hours,
            # Tab 4
            "absences":              absences,
        }
        return render(request, self.template_name, context)


class WorkerAbsenceCreateView(SupervisorAccessMixin, View):
    """
    Creates a WorkerAbsence record from the absence modal in admin_history.html.
    Receives the form POST from the modal's form action pointing to
    'panel:worker_absence_create'. On success or failure, always redirects
    back to the Absences tab of WorkOrderAdminHistoryView.

    POST /panel/worker-absences/create/
        Body params:
          company_user_pk (int)  — pk of the target CompanyUser (must belong to company).
          absence_type    (str)  — one of the WorkerAbsence.ABSENCE_* constants.
          start_date      (str)  — ISO date YYYY-MM-DD.
          end_date        (str)  — ISO date YYYY-MM-DD.
          notes           (str)  — optional free text.

    ---

    Crea un registro WorkerAbsence desde el modal de ausencias de admin_history.html.
    Recibe el POST del formulario del modal cuya accion apunta a
    'panel:worker_absence_create'. En caso de exito o fallo, siempre redirige
    de vuelta a la pestana Ausencias de WorkOrderAdminHistoryView.

    POST /panel/worker-absences/create/
        Parametros del cuerpo:
          company_user_pk (int)  — pk del CompanyUser objetivo (debe pertenecer a empresa).
          absence_type    (str)  — una de las constantes WorkerAbsence.ABSENCE_*.
          start_date      (str)  — fecha ISO YYYY-MM-DD.
          end_date        (str)  — fecha ISO YYYY-MM-DD.
          notes           (str)  — texto libre opcional.
    """

    def post(self, request, *args, **kwargs):
        """
        Validates the POST data, creates the WorkerAbsence and redirects.
        Performs server-side validation: company scope, absence_type whitelist,
        date ordering (start_date <= end_date).
        ---
        Valida los datos POST, crea el WorkerAbsence y redirige.
        Realiza validacion en el servidor: scope de empresa, lista blanca de
        absence_type, ordenacion de fechas (start_date <= end_date).
        """
        from datetime import datetime
        from django.urls import reverse
        from ivr_config.models import WorkerAbsence

        cu      = request.user.company_user
        company = cu.company
        ABSENCES_TAB_URL = reverse("panel:work_order_admin_history") + "?tab=absences"

        # ------------------------------------------------------------------
        # Resolve target CompanyUser — must belong to the same company.
        # Resolver CompanyUser objetivo — debe pertenecer a la misma empresa.
        # ------------------------------------------------------------------
        try:
            cu_pk       = int(request.POST.get("company_user_pk", ""))
            target_cu   = CompanyUser.objects.get(pk=cu_pk, company=company)
        except (ValueError, TypeError, CompanyUser.DoesNotExist):
            django_messages.error(
                request,
                "Operario no encontrado o no pertenece a esta empresa.",
            )
            return redirect(ABSENCES_TAB_URL)

        # ------------------------------------------------------------------
        # Validate absence_type against model choices whitelist.
        # Validar absence_type contra la lista blanca de opciones del modelo.
        # ------------------------------------------------------------------
        absence_type    = request.POST.get("absence_type", "").strip()
        valid_types     = {k for k, _ in WorkerAbsence.ABSENCE_CHOICES}
        if absence_type not in valid_types:
            django_messages.error(
                request,
                f"Tipo de ausencia '{absence_type}' no válido.",
            )
            return redirect(ABSENCES_TAB_URL)

        # ------------------------------------------------------------------
        # Parse and validate dates.
        # Parsear y validar fechas.
        # ------------------------------------------------------------------
        def _parse_iso(value):
            """Parses YYYY-MM-DD string, returns date or None. / Parsea cadena YYYY-MM-DD."""
            try:
                return datetime.strptime(value.strip(), "%Y-%m-%d").date()
            except (ValueError, AttributeError):
                return None

        start_date = _parse_iso(request.POST.get("start_date", ""))
        end_date   = _parse_iso(request.POST.get("end_date",   ""))

        if not start_date or not end_date:
            django_messages.error(
                request,
                "Las fechas de inicio y fin son obligatorias y deben tener formato YYYY-MM-DD.",
            )
            return redirect(ABSENCES_TAB_URL)

        if start_date > end_date:
            django_messages.error(
                request,
                "La fecha de inicio no puede ser posterior a la fecha de fin.",
            )
            return redirect(ABSENCES_TAB_URL)

        notes = request.POST.get("notes", "").strip()

        # ------------------------------------------------------------------
        # Create the WorkerAbsence record.
        # Crear el registro WorkerAbsence.
        # ------------------------------------------------------------------
        WorkerAbsence.objects.create(
            company_user  = target_cu,
            absence_type  = absence_type,
            start_date    = start_date,
            end_date      = end_date,
            registered_by = cu,
            notes         = notes,
        )

        operator_name = (
            target_cu.user.get_full_name() or target_cu.user.username
        )
        django_messages.success(
            request,
            f"Ausencia de {operator_name} registrada correctamente "
            f"({start_date:%d/%m/%Y} – {end_date:%d/%m/%Y}).",
        )
        return redirect(ABSENCES_TAB_URL)


class WorkerAbsenceUpdateView(SupervisorAccessMixin, View):
    """
    Updates an existing WorkerAbsence record from the absence modal in
    admin_history.html. Receives the form POST from the edit modal.
    On success or failure, always redirects back to the Absences tab of
    WorkOrderAdminHistoryView.

    POST /panel/worker-absences/<pk>/update/
        Body params:
          absence_type (str) — one of the WorkerAbsence.ABSENCE_* constants.
          start_date   (str) — ISO date YYYY-MM-DD.
          end_date     (str) — ISO date YYYY-MM-DD.
          notes        (str) — optional free text.
    ---
    Actualiza un registro WorkerAbsence existente desde el modal de edición
    de admin_history.html. Recibe el POST del formulario del modal de edición.
    En caso de éxito o fallo, siempre redirige a la pestaña Ausencias de
    WorkOrderAdminHistoryView.

    POST /panel/worker-absences/<pk>/update/
        Parámetros del cuerpo:
          absence_type (str) — una de las constantes WorkerAbsence.ABSENCE_*.
          start_date   (str) — fecha ISO YYYY-MM-DD.
          end_date     (str) — fecha ISO YYYY-MM-DD.
          notes        (str) — texto libre opcional.
    """

    def post(self, request, pk, *args, **kwargs):
        """
        Validates the POST data, updates the WorkerAbsence and redirects.
        Performs server-side validation: company scope, absence_type whitelist,
        date ordering (start_date <= end_date).
        ---
        Valida los datos POST, actualiza el WorkerAbsence y redirige.
        Realiza validacion en servidor: scope de empresa, lista blanca de
        absence_type, ordenacion de fechas (start_date <= end_date).
        """
        from datetime import datetime
        from django.urls import reverse
        from ivr_config.models import WorkerAbsence

        cu      = request.user.company_user
        company = cu.company
        ABSENCES_TAB_URL = reverse("panel:work_order_admin_history") + "?tab=absences"

        # ------------------------------------------------------------------
        # Resolve WorkerAbsence — must belong to the same company.
        # Resolver WorkerAbsence — debe pertenecer a la misma empresa.
        # ------------------------------------------------------------------
        try:
            absence = WorkerAbsence.objects.get(
                pk=pk,
                company_user__company=company,
            )
        except WorkerAbsence.DoesNotExist:
            django_messages.error(
                request,
                "Ausencia no encontrada o no pertenece a esta empresa.",
            )
            return redirect(ABSENCES_TAB_URL)

        # ------------------------------------------------------------------
        # Validate absence_type against model choices whitelist.
        # Validar absence_type contra la lista blanca de opciones del modelo.
        # ------------------------------------------------------------------
        absence_type = request.POST.get("absence_type", "").strip()
        valid_types  = {k for k, _ in WorkerAbsence.ABSENCE_CHOICES}
        if absence_type not in valid_types:
            django_messages.error(
                request,
                f"Tipo de ausencia '{absence_type}' no válido.",
            )
            return redirect(ABSENCES_TAB_URL)

        # ------------------------------------------------------------------
        # Parse and validate dates.
        # Parsear y validar fechas.
        # ------------------------------------------------------------------
        def _parse_iso(value):
            """Parses YYYY-MM-DD string, returns date or None. / Parsea cadena YYYY-MM-DD."""
            try:
                return datetime.strptime(value.strip(), "%Y-%m-%d").date()
            except (ValueError, AttributeError):
                return None

        start_date = _parse_iso(request.POST.get("start_date", ""))
        end_date   = _parse_iso(request.POST.get("end_date",   ""))

        if not start_date or not end_date:
            django_messages.error(
                request,
                "Las fechas de inicio y fin son obligatorias y deben tener formato YYYY-MM-DD.",
            )
            return redirect(ABSENCES_TAB_URL)

        if start_date > end_date:
            django_messages.error(
                request,
                "La fecha de inicio no puede ser posterior a la fecha de fin.",
            )
            return redirect(ABSENCES_TAB_URL)

        notes = request.POST.get("notes", "").strip()

        # ------------------------------------------------------------------
        # Update the WorkerAbsence record.
        # Actualizar el registro WorkerAbsence.
        # ------------------------------------------------------------------
        absence.absence_type = absence_type
        absence.start_date   = start_date
        absence.end_date     = end_date
        absence.notes        = notes
        absence.save(update_fields=["absence_type", "start_date", "end_date", "notes"])

        operator_name = (
            absence.company_user.user.get_full_name()
            or absence.company_user.user.username
        )
        django_messages.success(
            request,
            f"Ausencia de {operator_name} actualizada correctamente "
            f"({start_date:%d/%m/%Y} – {end_date:%d/%m/%Y}).",
        )
        return redirect(ABSENCES_TAB_URL)


class WorkerAbsenceDeleteView(SupervisorAccessMixin, View):
    """
    Deletes a WorkerAbsence record scoped to the authenticated user's company.
    On success or failure, always redirects back to the Absences tab of
    WorkOrderAdminHistoryView.

    POST /panel/worker-absences/<pk>/delete/
    ---
    Elimina un registro WorkerAbsence acotado a la empresa del usuario
    autenticado. En caso de éxito o fallo, siempre redirige a la pestaña
    Ausencias de WorkOrderAdminHistoryView.

    POST /panel/worker-absences/<pk>/delete/
    """

    def post(self, request, pk, *args, **kwargs):
        """
        Resolves the WorkerAbsence by pk scoped to the company, deletes it
        and redirects back to the Absences tab.
        ---
        Resuelve el WorkerAbsence por pk acotado a la empresa, lo elimina
        y redirige de vuelta a la pestaña Ausencias.
        """
        from django.urls import reverse
        from ivr_config.models import WorkerAbsence

        cu      = request.user.company_user
        company = cu.company
        ABSENCES_TAB_URL = reverse("panel:work_order_admin_history") + "?tab=absences"

        # ------------------------------------------------------------------
        # Resolve WorkerAbsence — must belong to the same company.
        # Resolver WorkerAbsence — debe pertenecer a la misma empresa.
        # ------------------------------------------------------------------
        try:
            absence = WorkerAbsence.objects.select_related(
                "company_user__user"
            ).get(
                pk=pk,
                company_user__company=company,
            )
        except WorkerAbsence.DoesNotExist:
            django_messages.error(
                request,
                "Ausencia no encontrada o no pertenece a esta empresa.",
            )
            return redirect(ABSENCES_TAB_URL)

        operator_name = (
            absence.company_user.user.get_full_name()
            or absence.company_user.user.username
        )
        absence.delete()

        django_messages.success(
            request,
            f"Ausencia de {operator_name} eliminada correctamente.",
        )
        return redirect(ABSENCES_TAB_URL)


# ---------------------------------------------------------------------------
# Module-level helpers for the merge flow (S018).
# Helpers de modulo para el flujo de merge (S018).
# ---------------------------------------------------------------------------


def _serialize_pending_lines(parsed_lines, parsed_repuestos, parsed_date):
    """
    Serialises the incoming form lines and spare parts into a JSON-safe
    list of dicts suitable for storage in the Django session.

    Each line dict contains:
        machine_raw, machine_asset_pk, fault_description, repair_notes,
        hc ("HH:MM"|null), hf ("HH:MM"|null), delta_hours (str|null),
        odometer_reading (str|null), engine_hours_reading (str|null),
        crane_hours_reading (str|null),
        repuestos: [{material, reference, quantity, source,
                     supplier, unit_price}]

    The date is stored as an ISO string so the merge view can
    reconstruct it.
    ---
    Serializa las lineas del formulario entrante y los repuestos en una
    lista de dicts JSON-safe apta para su almacenamiento en la sesion.

    La fecha se almacena como cadena ISO para que la vista de merge
    pueda reconstruirla.
    """
    serialized = []
    for ld in parsed_lines:
        hc_val = ld["hc"].strftime("%H:%M") if ld["hc"] else None
        hf_val = ld["hf"].strftime("%H:%M") if ld["hf"] else None

        # Collect spare parts for this batch (entry_idx removed in S012).
        # Recopilar repuestos del lote (entry_idx eliminado en S012).
        line_repuestos = []
        for spd in parsed_repuestos:
            unit_price_val = str(spd["unit_price"]) if spd.get("unit_price") is not None else None
            line_repuestos.append({
                "material":   spd["material"],
                "reference":  spd["referencia"],
                "quantity":   str(spd["quantity"]) if spd["quantity"] is not None else None,
                "source":     spd["source"],
                "supplier":   spd["supplier"],
                "unit_price": unit_price_val,
            })

        serialized.append({
            "machine_raw":           ld["machine_raw"],
            "machine_asset_pk":      ld["machine_asset"].pk if ld["machine_asset"] else None,
            "fault_description":     ld["fault_description"],
            "repair_notes":          ld["repair_notes"],
            "hc":                    hc_val,
            "hf":                    hf_val,
            "delta_hours":           str(ld["delta_hours"]) if ld["delta_hours"] is not None else None,
            "odometer_reading":      str(ld["odometer_reading"]) if ld.get("odometer_reading") is not None else None,
            "engine_hours_reading":  str(ld["engine_hours_reading"]) if ld.get("engine_hours_reading") is not None else None,
            "crane_hours_reading":   str(ld["crane_hours_reading"]) if ld.get("crane_hours_reading") is not None else None,
            "repuestos":             line_repuestos,
        })

    return {
        "lines":     serialized,
        "work_date": parsed_date.isoformat() if parsed_date else None,
    }


def _get_min_allowed_date(cu):
    # Returns the minimum work_date allowed for the given CompanyUser.
    # Rule: the day AFTER the most recent reviewed WorkOrderEntry for
    # this operator. If no reviewed entry exists, returns None.
    # Enforces: work_date > last_reviewed_date.
    # ---
    # Devuelve la fecha de trabajo minima permitida para el CompanyUser.
    # Regla: el dia SIGUIENTE al WorkOrderEntry revisado mas reciente.
    # Si no existe ninguno, devuelve None (sin restriccion).
    # Impone: work_date > last_reviewed_date.
    from datetime import timedelta
    from work_order_processor.models import WorkOrderEntry
    last_reviewed = (
        WorkOrderEntry.objects
        .filter(
            work_order__company=cu.company,
            work_order__uploaded_by=cu,
            work_order__reviewed=True,
        )
        .order_by("-work_date")
        .values_list("work_date", flat=True)
        .first()
    )
    if last_reviewed is None:
        return None
    return last_reviewed + timedelta(days=1)


def _detect_overlaps(existing_lines, new_lines):
    """
    Detects time overlaps between existing WorkOrderEntryLine records
    and a list of new line dicts from the session pending_merge_lines.

    Overlap condition (open intervals): hc_e < hf_n AND hc_n < hf_e.
    Lines with null hc or hf are silently ignored.

    Returns a list of tuples:
        (idx_e, idx_n, hc_e_str, hf_e_str, hc_n_str, hf_n_str)
    where idx_e is 1-based into existing_lines and idx_n is 1-based
    into new_lines.
    ---
    Detecta solapamientos temporales entre WorkOrderEntryLine existentes
    y la lista de dicts de lineas nuevas del payload pending_merge_lines.

    Condicion (intervalos abiertos): hc_e < hf_n AND hc_n < hf_e.
    Las lineas con hc o hf nulos se ignoran.

    Devuelve lista de tuplas:
        (idx_e, idx_n, hc_e_str, hf_e_str, hc_n_str, hf_n_str)
    """
    from datetime import datetime as _dt_ov

    def _t(val):
        """
        Parses HH:MM string to time, returns None on failure.
        ---
        Parsea cadena HH:MM a time, devuelve None en fallo.
        """
        if val is None:
            return None
        try:
            return _dt_ov.strptime(str(val).strip(), "%H:%M").time()
        except ValueError:
            return None

    conflicts = []
    for idx_e, existing_line in enumerate(existing_lines, start=1):
        hc_e = existing_line.hc
        hf_e = existing_line.hf
        if hc_e is None or hf_e is None:
            continue
        for idx_n, new_line in enumerate(new_lines, start=1):
            hc_n = _t(new_line.get("hc"))
            hf_n = _t(new_line.get("hf"))
            if hc_n is None or hf_n is None:
                continue
            # Open-interval overlap: hc_e < hf_n AND hc_n < hf_e.
            # Solapamiento intervalo abierto: hc_e < hf_n AND hc_n < hf_e.
            if hc_e < hf_n and hc_n < hf_e:
                conflicts.append((
                    idx_e,
                    idx_n,
                    hc_e.strftime("%H:%M"),
                    hf_e.strftime("%H:%M"),
                    hc_n.strftime("%H:%M"),
                    hf_n.strftime("%H:%M"),
                ))
    return conflicts


class WorkOrderEntryMergeView(WorkshopRequiredMixin, View):
    """
    Merge view for resolving conflicts when an operator tries to submit
    a new work order on a date that already has an unreviewed digital or
    generated entry. Presents existing and incoming lines side by side
    so the operator can choose one of three actions:

      discard_new      — keep existing entry, discard incoming lines.
      discard_existing — delete existing WorkOrder (CASCADE) and create
                         a new one from the pending session lines.
      merge            — append incoming lines to the existing entry.
                         Only available when no time overlaps exist.

    The operator may edit hc/hf before choosing an action.
    Client-side JS recalculates overlaps in real time; the server
    revalidates on every merge POST.

    GET  /panel/operator/merge/<int:entry_pk>/
    POST /panel/operator/merge/<int:entry_pk>/
         merge_action: discard_new | discard_existing | merge

    Accessible to WORKSHOP and ADMIN roles (WorkshopRequiredMixin).
    ---
    Vista de merge para resolver conflictos cuando un operario envia
    un parte en una fecha con entrada digital sin revisar preexistente.

    GET  /panel/operator/merge/<int:entry_pk>/
    POST /panel/operator/merge/<int:entry_pk>/
         merge_action: discard_new | discard_existing | merge

    Accesible para roles WORKSHOP y ADMIN (WorkshopRequiredMixin).
    """

    template_name = "panel/operator/merge_entry.html"

    # ------------------------------------------------------------------
    # Private helpers / Helpers privados
    # ------------------------------------------------------------------

    def _get_pending(self, request):
        """
        Returns the pending_merge_lines dict from the session, or None.
        ---
        Devuelve el dict pending_merge_lines de la sesion, o None.
        """
        return request.session.get("pending_merge_lines")

    def _clear_pending(self, request):
        """
        Removes pending_merge_lines from the session.
        ---
        Elimina pending_merge_lines de la sesion.
        """
        request.session.pop("pending_merge_lines", None)
        request.session.modified = True

    def _resolve_entry(self, entry_pk, company, cu):
        """
        Retrieves the WorkOrderEntry by pk, scoped to operator company
        and user. Returns None if not found or inaccessible.
        ---
        Recupera el WorkOrderEntry por pk, acotado a empresa y usuario
        del operario. Devuelve None si no existe o no es accesible.
        """
        try:
            return WorkOrderEntry.objects.select_related("work_order").get(
                pk=entry_pk,
                work_order__company=company,
                work_order__uploaded_by=cu,
                work_order__source__in=[
                    WorkOrder.Source.DIGITAL,
                    WorkOrder.Source.GENERATED,
                ],
                work_order__reviewed=False,
            )
        except WorkOrderEntry.DoesNotExist:
            return None

    def _parse_time_str(self, val):
        """
        Parses HH:MM string to datetime.time, returns None on failure.
        ---
        Parsea cadena HH:MM a datetime.time, devuelve None en fallo.
        """
        from datetime import time as _time
        if not val:
            return None
        try:
            parts = str(val).strip().split(":")
            return _time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            return None

    def _to_decimal(self, val):
        """
        Converts str/int/float to Decimal, returns None on failure.
        ---
        Convierte str/int/float a Decimal, devuelve None en fallo.
        """
        from decimal import Decimal, InvalidOperation
        if val is None:
            return None
        try:
            return Decimal(str(val))
        except InvalidOperation:
            return None

    def _parse_edited_hc_hf(self, POST, prefix, count):
        """
        Parses operator-edited hc/hf from POST for a set of lines
        identified by prefix and count (1-based).
        Returns a list of dicts: [{hc: HH:MM|None, hf: HH:MM|None}].
        ---
        Parsea hc/hf editados del POST para un conjunto de lineas
        identificadas por prefix y count (base 1).
        """
        result = []
        for i in range(1, count + 1):
            hc_raw = POST.get(f"{prefix}{i}_hc", "").strip() or None
            hf_raw = POST.get(f"{prefix}{i}_hf", "").strip() or None
            result.append({"hc": hc_raw, "hf": hf_raw})
        return result

    def _build_context(self, company, cu, existing_entry, existing_lines,
                       new_lines, work_date_iso, conflicts, merge_error=None):
        """
        Builds the template context dict for the merge view.
        ---
        Construye el dict de contexto del template para la vista de merge.
        """
        return {
            "company":        company,
            "company_user":   cu,
            "active_nav":     "operator_dashboard",
            "existing_entry": existing_entry,
            "existing_lines": existing_lines,
            "new_lines":      new_lines,
            "work_date":      work_date_iso,
            "conflicts":      conflicts,
            "has_conflicts":  bool(conflicts),
            "merge_error":    merge_error,
        }

    def _create_lines_from_session(self, new_lines, edited_new,
                                   target_entry, start_line_number, company):
        """
        Creates WorkOrderEntryLine and SparePartLine records from the
        session pending data inside an already-open atomic block.
        edited_new may provide operator-corrected hc/hf values.
        ---
        Crea WorkOrderEntryLine y SparePartLine desde los datos pendientes
        de la sesion dentro de un bloque atomico ya abierto.
        edited_new puede aportar hc/hf corregidos por el operario.
        """
        from fleet.models import MachineAsset
        from work_order_processor.models import SparePartLine
        from work_order_processor.services import (
            _normalise_machine_code,
            _compute_delta_hours,
        )

        for idx, line_data in enumerate(new_lines):
            edits  = edited_new[idx] if idx < len(edited_new) else {}
            hc_str = edits.get("hc") or line_data.get("hc")
            hf_str = edits.get("hf") or line_data.get("hf")
            hc_val = self._parse_time_str(hc_str)
            hf_val = self._parse_time_str(hf_str)
            delta  = _compute_delta_hours(hc_val, hf_val)

            # Resolve MachineAsset from pk stored in session.
            # Resolver MachineAsset desde pk almacenado en sesion.
            asset = None
            _asset_pk = line_data.get("machine_asset_pk")
            if _asset_pk is not None:
                try:
                    asset = MachineAsset.objects.get(
                        pk=_asset_pk, company=company
                    )
                except MachineAsset.DoesNotExist:
                    pass

            machine_raw  = line_data.get("machine_raw", "")
            machine_norm = _normalise_machine_code(machine_raw)

            new_line = WorkOrderEntryLine.objects.create(
                entry                = target_entry,
                line_number          = start_line_number + idx,
                machine_asset        = asset,
                machine_raw          = machine_raw,
                machine_norm         = machine_norm or "",
                fault_description    = line_data.get("fault_description", ""),
                repair_notes         = line_data.get("repair_notes", ""),
                hc                   = hc_val,
                hf                   = hf_val,
                or_val               = "",
                delta_hours          = delta,
                flags                = [],
                odometer_reading     = self._to_decimal(line_data.get("odometer_reading")),
                engine_hours_reading = self._to_decimal(line_data.get("engine_hours_reading")),
                crane_hours_reading  = self._to_decimal(line_data.get("crane_hours_reading")),
            )

            # SparePartLine records for this line.
            # Registros SparePartLine para esta linea.
            for rep_idx, rep in enumerate(line_data.get("repuestos", []), start=1):
                SparePartLine.objects.create(
                    entry_line  = new_line,
                    line_number = rep_idx,
                    reference   = rep.get("reference", ""),
                    vehicle     = None,
                    material    = rep.get("material", ""),
                    quantity    = self._to_decimal(rep.get("quantity")),
                    source      = rep.get("source", "WAREHOUSE"),
                    supplier    = rep.get("supplier", ""),
                    flags       = [],
                )

    # ------------------------------------------------------------------
    # Views / Vistas
    # ------------------------------------------------------------------

    def get(self, request, entry_pk, *args, **kwargs):
        """
        Renders the merge resolution page. Detects initial overlaps.
        Redirects to operator history with an error if session data is
        missing or the entry is inaccessible.
        ---
        Renderiza la pagina de resolucion de merge. Detecta solapamientos
        iniciales. Redirige al historial si faltan datos o el entry no
        es accesible.
        """
        from django.urls import reverse

        cu      = request.user.company_user
        company = cu.company

        pending = self._get_pending(request)
        if not pending:
            django_messages.error(
                request,
                "No hay datos de parte pendiente en sesion. "
                "El formulario ha expirado o fue enviado ya.",
            )
            return redirect(reverse("panel:operator_history"))

        existing_entry = self._resolve_entry(entry_pk, company, cu)
        if existing_entry is None:
            self._clear_pending(request)
            django_messages.error(
                request,
                "El parte existente no se ha encontrado o no es accesible.",
            )
            return redirect(reverse("panel:operator_history"))

        existing_lines = list(existing_entry.lines.order_by("line_number"))
        new_lines      = pending.get("lines", [])
        work_date_iso  = pending.get("work_date")

        conflicts = _detect_overlaps(existing_lines, new_lines)

        context = self._build_context(
            company, cu, existing_entry, existing_lines,
            new_lines, work_date_iso, conflicts,
        )
        return render(request, self.template_name, context)

    def post(self, request, entry_pk, *args, **kwargs):
        """
        Processes the merge action chosen by the operator.

        discard_new      — Clears the session and redirects to history.
        discard_existing — Deletes the existing WorkOrder (CASCADE) and
                           creates a new one from the pending session data.
        merge            — Re-validates overlaps with edited hc/hf values.
                           Appends new lines to existing entry if no conflicts.
        ---
        Procesa la accion de merge elegida por el operario.

        discard_new      — Limpia sesion y redirige al historial.
        discard_existing — Elimina WorkOrder existente y crea nuevo desde sesion.
        merge            — Revalida solapamientos con hc/hf editados. Anade
                           lineas al entry existente si no hay conflictos.
        """
        from datetime import datetime as _dtp
        from django.db import transaction
        from django.urls import reverse
        from work_order_processor.services import generate_work_order_excel

        cu      = request.user.company_user
        company = cu.company

        pending = self._get_pending(request)
        if not pending:
            django_messages.error(
                request,
                "No hay datos de parte pendiente en sesion. "
                "El formulario ha expirado o fue enviado ya.",
            )
            return redirect(reverse("panel:operator_history"))

        existing_entry = self._resolve_entry(entry_pk, company, cu)
        if existing_entry is None:
            self._clear_pending(request)
            django_messages.error(
                request,
                "El parte existente no se ha encontrado o no es accesible.",
            )
            return redirect(reverse("panel:operator_history"))

        merge_action   = request.POST.get("merge_action", "").strip()
        existing_lines = list(existing_entry.lines.order_by("line_number"))
        new_lines      = pending.get("lines", [])
        work_date_iso  = pending.get("work_date")

        # ------------------------------------------------------------------
        # Action: discard_new
        # ------------------------------------------------------------------
        if merge_action == "discard_new":
            self._clear_pending(request)
            django_messages.success(
                request,
                "Parte nuevo descartado. Se conserva el parte existente.",
            )
            return redirect(reverse("panel:operator_history"))

        # ------------------------------------------------------------------
        # Action: discard_existing
        # ------------------------------------------------------------------
        if merge_action == "discard_existing":
            work_date = None
            if work_date_iso:
                try:
                    work_date = _dtp.strptime(work_date_iso, "%Y-%m-%d").date()
                except ValueError:
                    pass

            try:
                with transaction.atomic():
                    # CASCADE deletes existing entry and all its lines.
                    # CASCADE elimina el entry existente y todas sus lineas.
                    existing_entry.work_order.delete()

                    worker_name = (
                        cu.user.get_full_name() or cu.user.username
                    ).upper()
                    date_tag = (
                        work_date.strftime("%d-%m-%Y") if work_date else "SIN-FECHA"
                    )
                    synthetic_name = f"{worker_name}_{date_tag}.pdf"

                    new_wo = WorkOrder(
                        company         = company,
                        uploaded_by     = cu,
                        source          = WorkOrder.Source.DIGITAL,
                        status          = WorkOrder.Status.DONE,
                        total_pages     = 1,
                        processed_pages = 1,
                        reviewed        = False,
                    )
                    new_wo.source_pdf.name = synthetic_name
                    new_wo.save()

                    new_entry = WorkOrderEntry.objects.create(
                        work_order            = new_wo,
                        page_number           = 1,
                        worker_name           = worker_name,
                        work_date             = work_date,
                        uncertain_date        = False,
                        extraction_confidence = WorkOrderEntry.Confidence.HIGH,
                        raw_gemini_response   = None,
                    )

                    # Create lines from session data (no edited hc/hf here).
                    # Crear lineas desde datos de sesion (sin edicion hc/hf).
                    self._create_lines_from_session(
                        new_lines, [], new_entry, 1, company
                    )

            except Exception as exc:
                logger.error(
                    "# [MergeView] Error en discard_existing: %s", exc, exc_info=True
                )
                django_messages.error(
                    request,
                    f"Error al procesar el merge: {exc}. Intentalo de nuevo.",
                )
                return redirect(reverse("panel:operator_history"))

            self._clear_pending(request)
            try:
                generate_work_order_excel(new_wo.pk)
            except Exception as exc:
                logger.warning(
                    "# [MergeView] Excel no generado para WorkOrder #%d: %s",
                    new_wo.pk, exc,
                )
            django_messages.success(
                request,
                "Parte existente sustituido correctamente. "
                "El nuevo parte ha sido registrado.",
            )
            return redirect(reverse("panel:operator_history"))

        # ------------------------------------------------------------------
        # Action: merge
        # ------------------------------------------------------------------
        if merge_action == "merge":
            edited_existing = self._parse_edited_hc_hf(
                request.POST, "existing_line_", len(existing_lines)
            )
            edited_new = self._parse_edited_hc_hf(
                request.POST, "new_line_", len(new_lines)
            )

            # Build in-memory copies with edited hc/hf for overlap detection.
            # Construir copias en memoria con hc/hf editados para deteccion.
            class _LineCopy:
                pass

            existing_copies = []
            for line, edits in zip(existing_lines, edited_existing):
                copy    = _LineCopy()
                copy.hc = self._parse_time_str(edits["hc"]) if edits["hc"] else line.hc
                copy.hf = self._parse_time_str(edits["hf"]) if edits["hf"] else line.hf
                existing_copies.append(copy)

            new_copies = []
            for nd, edits in zip(new_lines, edited_new):
                new_copies.append({
                    "hc": edits["hc"] if edits["hc"] else nd.get("hc"),
                    "hf": edits["hf"] if edits["hf"] else nd.get("hf"),
                })

            conflicts = _detect_overlaps(existing_copies, new_copies)

            if conflicts:
                context = self._build_context(
                    company, cu, existing_entry, existing_lines,
                    new_lines, work_date_iso, conflicts,
                    merge_error=(
                        "No es posible fusionar: existen solapamientos horarios. "
                        "Edita los horarios para resolver los conflictos."
                    ),
                )
                return render(request, self.template_name, context)

            # No conflicts — append new lines to existing entry atomically.
            # Sin conflictos — anadir lineas al entry existente de forma atomica.
            try:
                with transaction.atomic():
                    start_number = existing_entry.lines.count() + 1
                    self._create_lines_from_session(
                        new_lines, edited_new, existing_entry, start_number, company
                    )
            except Exception as exc:
                logger.error(
                    "# [MergeView] Error en merge: %s", exc, exc_info=True
                )
                django_messages.error(
                    request,
                    f"Error al fusionar el parte: {exc}. Intentalo de nuevo.",
                )
                return redirect(reverse("panel:operator_history"))

            self._clear_pending(request)
            try:
                generate_work_order_excel(existing_entry.work_order.pk)
            except Exception as exc:
                logger.warning(
                    "# [MergeView] Excel no regenerado para WorkOrder #%d: %s",
                    existing_entry.work_order.pk, exc,
                )
            django_messages.success(
                request,
                f"Parte fusionado correctamente. Tareas anadidas al parte del "
                f"{work_date_iso or 'fecha desconocida'}.",
            )
            return redirect(reverse("panel:operator_history"))

        # Unknown merge_action — redirect with warning.
        # merge_action desconocido — redirigir con aviso.
        django_messages.warning(
            request,
            "Accion de merge no reconocida. No se ha realizado ningun cambio.",
        )
        return redirect(reverse("panel:operator_history"))


class WorkOrderAdminHistoryView(SupervisorAccessMixin, View):

    """
    Four-tab management history view for ADMIN and SUPERVISOR roles.
    Provides a comprehensive interface for reviewing, exporting and managing
    all operators' work orders, absences and work periods within the company.

    Tabs:
      1 — Pendientes  : unreviewed work orders for all company operators.
                        Filters: operator, date, machine.
                        Actions: mark as reviewed, link to edit view.
      2 — Revisados   : reviewed work orders. Excel export available HERE ONLY
                        (single work order or date-range multi-export).
                        Filters: operator, date range, machine.
      3 — Histórico   : all work orders with cross-filters (operator, date
                        range, machine, review status). Read-only.
      4 — Ausencias   : WorkerAbsence records per operator with type/date
                        filters. Actions: create, edit, delete absence.
                        Action 'Generar partes del periodo': creates synthetic
                        WorkOrder records (one per working day Mon–Fri) for the
                        absence range, tagged with generated_by=current user.

    GET /panel/work-orders/history/
        Optional GET params:
          tab         (str)  — active tab: pending|reviewed|history|absences.
                               Default: pending.
          operator_pk (int)  — filter by CompanyUser pk (scoped to company).
          date_from   (str)  — ISO date YYYY-MM-DD start of range.
          date_to     (str)  — ISO date YYYY-MM-DD end of range.
          machine     (str)  — MachineAsset.code icontains filter.

    ---

    Vista de historial de gestion de cuatro pestanas para roles ADMIN y SUPERVISOR.
    Proporciona una interfaz completa para revisar, exportar y gestionar todos los
    partes de trabajo, ausencias y periodos de trabajo de los operarios de la empresa.

    Pestanas:
      1 — Pendientes  : partes sin revisar de todos los operarios de la empresa.
                        Filtros: operario, fecha, maquina.
                        Acciones: marcar como revisado, enlace a vista de edicion.
      2 — Revisados   : partes revisados. Exportacion Excel disponible SOLO AQUI
                        (parte individual o multi-exportacion por rango de fechas).
                        Filtros: operario, rango de fechas, maquina.
      3 — Historico   : todos los partes con filtros cruzados (operario, rango de
                        fechas, maquina, estado de revision). Solo lectura.
      4 — Ausencias   : registros WorkerAbsence por operario con filtros de tipo y
                        fecha. Acciones: alta, edicion, baja de ausencia.
                        Accion 'Generar partes del periodo': crea registros WorkOrder
                        sinteticos (uno por dia laborable lun–vie) para el rango de
                        la ausencia, etiquetados con generated_by=usuario actual.

    GET /panel/work-orders/history/
        Parametros GET opcionales:
          tab         (str)  — pestana activa: pending|reviewed|history|absences.
                               Por defecto: pending.
          operator_pk (int)  — filtrar por pk de CompanyUser (acotado a empresa).
          date_from   (str)  — fecha ISO YYYY-MM-DD inicio del rango.
          date_to     (str)  — fecha ISO YYYY-MM-DD fin del rango.
          machine     (str)  — filtro icontains sobre MachineAsset.code.
    """

    template_name = "panel/work_orders/admin_history.html"

    # Spanish month names for display labels.
    # Nombres de mes en castellano para etiquetas de visualizacion.
    _MESES_ES = {
        1: "Enero",   2: "Febrero",  3: "Marzo",    4: "Abril",
        5: "Mayo",    6: "Junio",    7: "Julio",     8: "Agosto",
        9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
    }

    def _get_own_presence(self, company_user):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

    def _parse_date(self, value):
        """
        Parses an ISO date string (YYYY-MM-DD) and returns a date object,
        or None if the value is absent or malformed.
        ---
        Parsea una cadena de fecha ISO (YYYY-MM-DD) y devuelve un objeto date,
        o None si el valor esta ausente o malformado.
        """
        from datetime import datetime
        if not value:
            return None
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None

    def _build_base_queryset(self, company):
        """
        Returns the base WorkOrder queryset scoped to the company, restricted
        to DIGITAL and GENERATED sources (operator-entered parts only).
        PDF_UPLOAD parts belong exclusively to WorkOrderListView.
        All required related data is prefetched for the admin history tabs.
        ---
        Devuelve el queryset base de WorkOrder acotado a la empresa, restringido
        a los origenes DIGITAL y GENERATED (partes introducidos por operarios).
        Los partes PDF_UPLOAD pertenecen exclusivamente a WorkOrderListView.
        Todos los datos relacionados se prefetchean para las pestanas del historial.
        """
        return (
            WorkOrder.objects
            .filter(
                company=company,
                source__in=[
                    WorkOrder.Source.DIGITAL,
                    WorkOrder.Source.GENERATED,
                ],
            )
            .select_related("uploaded_by__user", "reviewed_by__user", "generated_by__user")
            .prefetch_related(
                Prefetch(
                    "entries",
                    queryset=WorkOrderEntry.objects.prefetch_related("lines"),
                )
            )
            .order_by("-id")
        )

    def _apply_filters(self, qs, operator_pk, date_from, date_to, machine, company):
        """
        Applies the optional GET filters to a WorkOrder queryset.
        operator_pk filters by uploaded_by; date_from/date_to filter by the
        first entry's work_date; machine filters by machine_asset__code.
        ---
        Aplica los filtros GET opcionales a un queryset de WorkOrder.
        operator_pk filtra por uploaded_by; date_from/date_to filtran por
        work_date del primer entry; machine filtra por machine_asset__code.
        """
        if operator_pk:
            try:
                cu_pk = int(operator_pk)
                qs = qs.filter(uploaded_by__pk=cu_pk, uploaded_by__company=company)
            except (ValueError, TypeError):
                pass
        if date_from:
            qs = qs.filter(entries__work_date__gte=date_from)
        if date_to:
            qs = qs.filter(entries__work_date__lte=date_to)
        if machine:
            qs = qs.filter(
                entries__lines__machine_asset__code__icontains=machine
            )
        return qs.distinct()

    def _enrich_work_orders(self, qs):
        """
        Converts a WorkOrder queryset into a list of enriched dicts suitable
        for template rendering. Each dict includes pk, fecha, operator name,
        num_bloques, horas_totales and reviewed flag.
        ---
        Convierte un queryset de WorkOrder en una lista de dicts enriquecidos
        adecuados para renderizado en template. Cada dict incluye pk, fecha,
        nombre del operario, num_bloques, horas_totales y flag reviewed.
        """
        from decimal import Decimal
        result = []
        for wo in qs:
            entries_list  = list(wo.entries.all())
            first_entry   = entries_list[0] if entries_list else None
            work_date     = first_entry.work_date if first_entry else None
            num_bloques   = sum(entry.lines.count() for entry in entries_list)
            horas_totales = sum(
                (line.delta_hours
                 for entry in entries_list
                 for line in entry.lines.all()
                 if line.delta_hours is not None),
                Decimal("0"),
            )
            operator_name = (
                wo.uploaded_by.user.get_full_name() or wo.uploaded_by.user.username
                if wo.uploaded_by else "Desconocido"
            )
            result.append({
                "pk":            wo.pk,
                "fecha":         work_date,
                "operator_name": operator_name,
                "operator_pk":   wo.uploaded_by.pk if wo.uploaded_by else None,
                "num_bloques":   num_bloques,
                "horas_totales": horas_totales,
                "reviewed":      wo.reviewed,
                "reviewed_by":   (
                    wo.reviewed_by.user.get_full_name() or wo.reviewed_by.user.username
                    if wo.reviewed_by else None
                ),
                "reviewed_at":   wo.reviewed_at,
                "generated_by":  (
                    wo.generated_by.user.get_full_name() or wo.generated_by.user.username
                    if wo.generated_by else None
                ),
                "excel_url": wo.excel_file.url if wo.excel_file else None,
            })
        return result

    def get(self, request, *args, **kwargs):
        """
        Renders the four-tab admin history page. Resolves GET filters,
        builds each tab's queryset independently and passes all data to
        the template context.
        ---
        Renderiza la pagina de historial de administrador de cuatro pestanas.
        Resuelve los filtros GET, construye el queryset de cada pestana
        de forma independiente y pasa todos los datos al contexto del template.
        """
        cu      = request.user.company_user
        company = cu.company

        # ------------------------------------------------------------------
        # Resolve GET parameters / Resolver parametros GET.
        # ------------------------------------------------------------------
        active_tab   = request.GET.get("tab", "pending")
        operator_pk  = request.GET.get("operator_pk", "").strip()
        date_from    = self._parse_date(request.GET.get("date_from", ""))
        date_to      = self._parse_date(request.GET.get("date_to", ""))
        machine      = request.GET.get("machine", "").strip()

        # ------------------------------------------------------------------
        # Operator selector list (all active company users).
        # Lista de selector de operarios (todos los usuarios activos de la empresa).
        # ------------------------------------------------------------------
        operators = (
            CompanyUser.objects
            .filter(
                company=company,
                is_active=True,
                role=CompanyUser.ROLE_WORKSHOP,
            )
            .select_related("user")
            .order_by("user__last_name", "user__first_name")
        )

        # ------------------------------------------------------------------
        # Tab 1 — Pending (unreviewed work orders).
        # Pestana 1 — Pendientes (partes sin revisar).
        # ------------------------------------------------------------------
        qs_pending = self._build_base_queryset(company).filter(reviewed=False)
        qs_pending = self._apply_filters(
            qs_pending, operator_pk, date_from, date_to, machine, company
        )
        pending_list = self._enrich_work_orders(qs_pending)

        # ------------------------------------------------------------------
        # Tab 2 — Reviewed (reviewed work orders — Excel export available).
        # Pestana 2 — Revisados (partes revisados — exportacion Excel disponible).
        # ------------------------------------------------------------------
        qs_reviewed = self._build_base_queryset(company).filter(reviewed=True)
        qs_reviewed = self._apply_filters(
            qs_reviewed, operator_pk, date_from, date_to, machine, company
        )
        reviewed_list = self._enrich_work_orders(qs_reviewed)

        # ------------------------------------------------------------------
        # Tab 3 — Full history (all work orders, cross-filters).
        # Pestana 3 — Historico completo (todos los partes, filtros cruzados).
        # ------------------------------------------------------------------
        qs_history = self._build_base_queryset(company).filter(reviewed=True)
        qs_history = self._apply_filters(
            qs_history, operator_pk, date_from, date_to, machine, company
        )
        history_list = self._enrich_work_orders(qs_history)

        # ------------------------------------------------------------------
        # Tab 4 — Absences (WorkerAbsence records for the company).
        # Pestana 4 — Ausencias (registros WorkerAbsence de la empresa).
        # ------------------------------------------------------------------
        from ivr_config.models import WorkerAbsence
        absence_qs = (
            WorkerAbsence.objects
            .filter(company_user__company=company)
            .select_related(
                "company_user__user",
                "registered_by__user",
            )
            .order_by("-start_date")
        )
        # Optional operator filter on absences tab.
        # Filtro de operario opcional en la pestana de ausencias.
        if operator_pk:
            try:
                absence_qs = absence_qs.filter(company_user__pk=int(operator_pk))
            except (ValueError, TypeError):
                pass
        absences_list = list(absence_qs)

        # ------------------------------------------------------------------
        # Suggested period start — last closed period end_date + 1 day.
        # Inicio sugerido de periodo — end_date del ultimo periodo cerrado + 1 dia.
        # ------------------------------------------------------------------
        from ivr_config.models import WorkPeriod
        from datetime import timedelta as _td
        last_closed = (
            WorkPeriod.objects
            .filter(
                company_user__company=company,
                end_date__isnull=False,
            )
            .order_by("-end_date")
            .values_list("end_date", "start_date")
            .first()
        )
        if last_closed:
            _last_end              = last_closed[0]
            _last_start            = last_closed[1]
            _period_len            = _last_end - _last_start
            suggested_period_start = (_last_end + _td(days=1)).strftime("%Y-%m-%d")
            suggested_period_end   = (_last_end + _td(days=1) + _period_len).strftime("%Y-%m-%d")
        else:
            suggested_period_start = ""
            suggested_period_end   = ""

        context = {
            "company":                cu.company,
            "company_user":           cu,
            "own_presence":           self._get_own_presence(cu),
            "active_nav":             "work_order_admin_history",
            "active_tab":             active_tab,
            "operators":              operators,
            "operator_pk":            operator_pk,
            "date_from":              request.GET.get("date_from", ""),
            "date_to":                request.GET.get("date_to", ""),
            "machine":                machine,
            "pending_list":           pending_list,
            "reviewed_list":          reviewed_list,
            "history_list":           history_list,
            "absences_list":          absences_list,
            "suggested_period_start": suggested_period_start,
            "suggested_period_end":   suggested_period_end,
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        """
        Dispatches POST actions for the admin history view.

        Supported actions:
          generate_absence_parts — creates synthetic WorkOrders from a WorkerAbsence.
          delete_work_order      — deletes a single WorkOrder by pk.
          bulk_action            — applies mark_reviewed or delete to a set of PKs.

        ---

        Despacha las acciones POST de la vista de historial de administrador.

        Acciones soportadas:
          generate_absence_parts — crea WorkOrders sinteticos desde un WorkerAbsence.
          delete_work_order      — elimina un WorkOrder individual por pk.
          bulk_action            — aplica mark_reviewed o delete a un conjunto de PKs.
        """
        from datetime import timedelta, date as dt_date
        from django.db import transaction
        from ivr_config.models import WorkerAbsence
        from work_order_processor.models import WorkOrder, WorkOrderEntry, WorkOrderEntryLine
        from django.urls import reverse

        cu      = request.user.company_user
        company = cu.company
        action  = request.POST.get("action", "").strip()

        # ------------------------------------------------------------------
        # Action: delete_work_order — delete a single digital/generated part.
        # Accion: delete_work_order — eliminar un parte digital/generado individual.
        # ------------------------------------------------------------------
        if action == "delete_work_order":
            active_tab = request.POST.get("active_tab", "pending")
            try:
                wo_pk      = int(request.POST.get("work_order_pk", ""))
                work_order = WorkOrder.objects.get(
                    pk=wo_pk,
                    company=company,
                    source__in=[WorkOrder.Source.DIGITAL, WorkOrder.Source.GENERATED],
                )
                work_order.delete()
                django_messages.success(request, f"Parte #{wo_pk} eliminado correctamente.")
            except (ValueError, TypeError, WorkOrder.DoesNotExist):
                django_messages.error(
                    request,
                    "Parte no encontrado o no pertenece a esta empresa.",
                )
            return redirect(
                reverse("panel:work_order_admin_history") + f"?tab={active_tab}"
            )

        # ------------------------------------------------------------------
        # Action: bulk_action — mark reviewed or delete multiple parts.
        # Accion: bulk_action — marcar revisados o eliminar multiples partes.
        # ------------------------------------------------------------------
        if action == "bulk_action":
            active_tab  = request.POST.get("active_tab", "pending")
            bulk_op     = request.POST.get("bulk_op", "").strip()
            raw_pks     = request.POST.getlist("selected_pks")

            try:
                pk_list = [int(p) for p in raw_pks if p.strip().isdigit()]
            except (ValueError, TypeError):
                pk_list = []

            if not pk_list:
                django_messages.warning(request, "No se ha seleccionado ningún parte.")
                return redirect(
                    reverse("panel:work_order_admin_history") + f"?tab={active_tab}"
                )

            # Scope to company + digital/generated sources only.
            # Acotar a empresa + origenes digital/generado unicamente.
            qs = WorkOrder.objects.filter(
                pk__in=pk_list,
                company=company,
                source__in=[WorkOrder.Source.DIGITAL, WorkOrder.Source.GENERATED],
            )

            if bulk_op == "mark_reviewed":
                from django.utils.timezone import now as tz_now
                updated = qs.filter(reviewed=False).update(
                    reviewed    = True,
                    reviewed_by = cu,
                    reviewed_at = tz_now(),
                )
                django_messages.success(
                    request,
                    f"{updated} parte(s) marcado(s) como revisado(s).",
                )
            elif bulk_op == "delete":
                count  = qs.count()
                qs.delete()
                django_messages.success(
                    request,
                    f"{count} parte(s) eliminado(s) correctamente.",
                )
            else:
                django_messages.error(request, "Operación en bloque no reconocida.")

            return redirect(
                reverse("panel:work_order_admin_history") + f"?tab={active_tab}"
            )

        if action != "generate_absence_parts":
            django_messages.error(request, "Acción no reconocida.")
            return redirect(reverse("panel:work_order_admin_history") + "?tab=absences")

        # Resolve WorkerAbsence — must belong to same company.
        # Resolver WorkerAbsence — debe pertenecer a la misma empresa.
        try:
            absence_pk = int(request.POST.get("absence_pk", ""))
            absence    = WorkerAbsence.objects.select_related("company_user__user").get(
                pk=absence_pk,
                company_user__company=company,
            )
        except (ValueError, TypeError, WorkerAbsence.DoesNotExist):
            django_messages.error(
                request,
                "Registro de ausencia no encontrado o no pertenece a esta empresa.",
            )
            return redirect(reverse("panel:work_order_admin_history") + "?tab=absences")

        # Enumerate working days (Mon–Fri) in the absence range.
        # Enumerar dias laborables (lun–vie) en el rango de la ausencia.
        current_day = absence.start_date
        working_days = []
        while current_day <= absence.end_date:
            if current_day.weekday() < 5:   # 0=Mon … 4=Fri / 0=Lun … 4=Vie
                working_days.append(current_day)
            current_day += timedelta(days=1)

        if not working_days:
            django_messages.warning(
                request,
                f"El rango de la ausencia ({absence.start_date} – {absence.end_date}) "
                f"no contiene días laborables (lunes a viernes). No se han generado partes.",
            )
            return redirect(reverse("panel:work_order_admin_history") + "?tab=absences")

        created_count = 0
        skipped_count = 0

        try:
            with transaction.atomic():
                for work_day in working_days:
                    # Skip if a WorkOrder already exists for this operator/date.
                    # Saltar si ya existe un WorkOrder para este operario/fecha.
                    already_exists = WorkOrder.objects.filter(
                        company=company,
                        uploaded_by=absence.company_user,
                        entries__work_date=work_day,
                    ).exists()
                    if already_exists:
                        skipped_count += 1
                        continue

                    # Build synthetic source_pdf name for identification.
                    # Construir nombre sintetico de source_pdf para identificacion.
                    synthetic_name = (
                        f"AUSENCIA_{absence.get_absence_type_display().upper()}_"
                        f"{work_day.strftime('%Y%m%d')}_"
                        f"{absence.company_user.user.username.upper()}.pdf"
                    )

                    work_order = WorkOrder.objects.create(
                        company      = company,
                        uploaded_by  = absence.company_user,
                        generated_by = cu,
                        source       = WorkOrder.Source.GENERATED,
                        status       = WorkOrder.Status.DONE,
                    )
                    # Assign synthetic source_pdf name without storing a real file.
                    # Asignar nombre sintetico de source_pdf sin almacenar fichero real.
                    work_order.source_pdf.name = synthetic_name
                    work_order.save()

                    entry = WorkOrderEntry.objects.create(
                        work_order            = work_order,
                        page_number           = 1,
                        worker_name           = (
                            absence.company_user.user.get_full_name()
                            or absence.company_user.user.username
                        ).upper(),
                        work_date             = work_day,
                        uncertain_date        = False,
                        extraction_confidence = WorkOrderEntry.Confidence.HIGH,
                        raw_gemini_response   = None,
                    )

                    WorkOrderEntryLine.objects.create(
                        entry             = entry,
                        line_number       = 1,
                        machine_asset     = None,
                        machine_raw       = "",
                        machine_norm      = "",
                        fault_description = absence.get_absence_type_display(),
                        repair_notes      = "",
                        hc                = None,
                        hf                = None,
                        or_val            = "",
                        delta_hours       = 8,
                        flags             = [],
                    )
                    created_count += 1

        except Exception as exc:
            logger.error(
                "# [AdminHistory] Error generando partes de ausencia pk=%d: %s",
                absence.pk, exc, exc_info=True,
            )
            django_messages.error(
                request,
                f"Error al generar los partes: {exc}. "
                "Por favor, inténtalo de nuevo o contacta con el administrador.",
            )
            return redirect(reverse("panel:work_order_admin_history") + "?tab=absences")

        # Build summary message for the supervisor.
        # Construir mensaje resumen para el supervisor.
        msg_parts = []
        if created_count:
            msg_parts.append(f"{created_count} parte(s) generado(s) correctamente.")
        if skipped_count:
            msg_parts.append(
                f"{skipped_count} día(s) omitido(s) por existir ya un parte para esa fecha."
            )
        django_messages.success(request, " ".join(msg_parts))
        return redirect(reverse("panel:work_order_admin_history") + "?tab=absences")


class WorkPeriodListView(SupervisorAccessMixin, View):
    """
    Lists all WorkPeriod records for the authenticated user's company,
    grouped by operator and ordered descending by start_date.
    Renders the full work_period_list.html page on GET.

    GET /panel/work-periods/
    ---
    Lista todos los registros WorkPeriod de la empresa del usuario autenticado,
    agrupados por operario y ordenados descendentemente por start_date.
    Renderiza la página completa work_period_list.html en GET.

    GET /panel/work-periods/
    """

    template_name = "panel/work_orders/work_period_list.html"

    def _get_own_presence(self, company_user):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

    def get(self, request, *args, **kwargs):
        """
        Builds the context with all WorkPeriod records grouped by operator
        and renders the work_period_list template.
        ---
        Construye el contexto con todos los registros WorkPeriod agrupados
        por operario y renderiza el template work_period_list.
        """
        from ivr_config.models import WorkPeriod

        cu      = request.user.company_user
        company = cu.company

        operators = (
            CompanyUser.objects
            .filter(company=company, is_active=True, role=CompanyUser.ROLE_WORKSHOP)
            .select_related("user")
            .order_by("user__last_name", "user__first_name")
        )

        operator_groups = []
        for operator in operators:
            periods = (
                WorkPeriod.objects
                .filter(company_user=operator)
                .select_related("created_by__user")
                .order_by("-start_date")
            )
            operator_groups.append({
                "operator":    operator,
                "periods":     list(periods),
                "has_open":    any(p.end_date is None for p in periods),
            })

        context = {
            "company":          company,
            "company_user":     cu,
            "own_presence":     self._get_own_presence(cu),
            "active_nav":       "work_period_list",
            "operator_groups":  operator_groups,
            "operators":        operators,
        }
        return render(request, self.template_name, context)


class WorkPeriodCreateView(SupervisorAccessMixin, View):
    """
    Creates a new global WorkPeriod for ALL active WORKSHOP operators
    belonging to the authenticated supervisor's company.
    The work period is company-wide: the same start_date and label are
    applied to every active WORKSHOP operator in a single operation.
    Operators that already have an open period are skipped individually
    and reported back to the user via a warning message.
    On success or failure, redirects to work_period_list.

    POST /panel/work-periods/create/
    ---
    Crea un nuevo WorkPeriod global para TODOS los operarios WORKSHOP
    activos de la empresa del supervisor autenticado.
    El periodo de trabajo es de ámbito empresarial: la misma start_date
    y etiqueta se aplican a todos los operarios WORKSHOP activos.
    Los operarios que ya tienen un periodo abierto se omiten individualmente
    y se notifican al usuario mediante un mensaje de aviso.
    En éxito o fallo, redirige a work_period_list.

    POST /panel/work-periods/create/
    """

    def post(self, request, *args, **kwargs):
        """
        Validates POST data, creates a WorkPeriod for every active WORKSHOP
        operator in the company and redirects to work_period_list.
        Operators with an already-open period are skipped individually and
        reported back via a warning django message.
        ---
        Valida los datos POST, crea un WorkPeriod para cada operario WORKSHOP
        activo de la empresa y redirige a work_period_list.
        Los operarios con un periodo ya abierto se omiten individualmente y
        se notifican al usuario mediante un mensaje de aviso de Django.
        """
        from datetime import datetime
        from django.urls import reverse
        from ivr_config.models import WorkPeriod

        cu       = request.user.company_user
        company  = cu.company
        LIST_URL = reverse("panel:work_period_list")

        # Parse and validate start_date from POST.
        # Parsear y validar start_date del POST.
        raw_start = request.POST.get("start_date", "").strip()
        try:
            start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
        except (ValueError, AttributeError):
            django_messages.error(
                request,
                "La fecha de inicio es obligatoria y debe tener formato YYYY-MM-DD.",
            )
            return redirect(LIST_URL)

        label = request.POST.get("label", "").strip()

        # Parse optional end_date — if provided, applied to all created periods.
        # Parsear end_date opcional — si se proporciona, se aplica a todos los periodos creados.
        raw_end = request.POST.get("end_date", "").strip()
        end_date_parsed = None
        if raw_end:
            try:
                end_date_parsed = datetime.strptime(raw_end, "%Y-%m-%d").date()
                if end_date_parsed < start_date:
                    django_messages.error(
                        request,
                        "La fecha de fin no puede ser anterior a la fecha de inicio.",
                    )
                    return redirect(LIST_URL)
            except (ValueError, AttributeError):
                end_date_parsed = None

        # Retrieve all active WORKSHOP operators for the company.
        # Obtener todos los operarios WORKSHOP activos de la empresa.
        workshop_operators = list(
            CompanyUser.objects
            .filter(company=company, is_active=True, role=CompanyUser.ROLE_WORKSHOP)
            .select_related("user")
            .order_by("user__last_name", "user__first_name")
        )

        if not workshop_operators:
            django_messages.error(
                request,
                "No hay operarios de taller activos en la empresa. No se ha creado ningún periodo.",
            )
            return redirect(LIST_URL)

        # Iterate operators: skip those with an already-open period.
        # Iterar operarios: omitir los que ya tienen un periodo abierto.
        created_count = 0
        skipped_names = []

        for operator in workshop_operators:
            if WorkPeriod.objects.filter(
                company_user=operator, end_date__isnull=True
            ).exists():
                skipped_names.append(
                    operator.user.get_full_name() or operator.user.username
                )
                continue

            WorkPeriod.objects.create(
                company_user = operator,
                start_date   = start_date,
                end_date     = end_date_parsed,
                label        = label,
                created_by   = cu,
            )
            created_count += 1

        # Build feedback messages for the user.
        # Construir mensajes de respuesta para el usuario.
        if created_count > 0:
            django_messages.success(
                request,
                f"Periodo de trabajo creado para {created_count} operario"
                f"{'s' if created_count != 1 else ''} "
                f"(inicio: {start_date:%d/%m/%Y}).",
            )
        else:
            django_messages.warning(
                request,
                "No se ha creado ningún periodo: todos los operarios tienen ya un periodo abierto.",
            )

        if skipped_names:
            skipped_list = ", ".join(skipped_names)
            django_messages.warning(
                request,
                f"Operarios omitidos por tener periodo abierto: {skipped_list}.",
            )

        return redirect(LIST_URL)


class WorkPeriodCloseView(SupervisorAccessMixin, View):
    """
    Closes an open WorkPeriod by assigning its end_date.
    Validates: company scope, open period, end_date >= start_date.
    On success or failure, redirects to work_period_list.

    POST /panel/work-periods/<pk>/close/
    ---
    Cierra un WorkPeriod abierto asignando end_date.
    Valida: scope empresa, periodo abierto, end_date >= start_date.
    En éxito o fallo, redirige a work_period_list.

    POST /panel/work-periods/<pk>/close/
    """

    def post(self, request, pk, *args, **kwargs):
        """
        Validates end_date, closes WorkPeriod and redirects.
        ---
        Valida end_date, cierra WorkPeriod y redirige.
        """
        from datetime import datetime
        from django.urls import reverse
        from ivr_config.models import WorkPeriod

        cu       = request.user.company_user
        company  = cu.company
        LIST_URL = reverse("panel:work_period_list")

        try:
            period = WorkPeriod.objects.select_related("company_user__user").get(
                pk=pk, company_user__company=company,
            )
        except WorkPeriod.DoesNotExist:
            django_messages.error(request, "Periodo de trabajo no encontrado o no pertenece a esta empresa.")
            return redirect(LIST_URL)

        if period.end_date is not None:
            django_messages.error(request, "Este periodo ya está cerrado y no puede modificarse.")
            return redirect(LIST_URL)

        raw_end = request.POST.get("end_date", "").strip()
        try:
            end_date = datetime.strptime(raw_end, "%Y-%m-%d").date()
        except (ValueError, AttributeError):
            django_messages.error(request, "La fecha de fin es obligatoria y debe tener formato YYYY-MM-DD.")
            return redirect(LIST_URL)

        if end_date < period.start_date:
            django_messages.error(request, f"La fecha de fin ({end_date:%d/%m/%Y}) no puede ser anterior a la fecha de inicio ({period.start_date:%d/%m/%Y}).")
            return redirect(LIST_URL)

        period.end_date = end_date
        period.save(update_fields=["end_date"])
        operator_name = period.company_user.user.get_full_name() or period.company_user.user.username
        django_messages.success(request, f"Periodo de {operator_name} cerrado correctamente ({period.start_date:%d/%m/%Y} – {end_date:%d/%m/%Y}).")
        return redirect(LIST_URL)


class WorkOrderAdminExportView(SupervisorAccessMixin, View):
    """
    Excel export endpoint scoped exclusively to digital and generated work
    orders (WorkOrder.Source.DIGITAL and WorkOrder.Source.GENERATED).
    Designed for use from WorkOrderAdminHistoryView tab Revisados.

    Supports two export modes via the POST field export_mode:

      single_sheet — One flat sheet with all WorkOrderEntryLine records from
        the selected WorkOrders, grouped by operator name then work date.
        A dark-blue separator row bearing the operator name is inserted before
        each new operator block. Data is read directly from the DB.

      multi_sheet  — One sheet per distinct operator (worker_name derived from
        uploaded_by CompanyUser). Each sheet is built from the individual Excel
        stored in WorkOrder.excel_file (regenerated on-the-fly if missing).
        Sheet title truncated to 31 characters (Excel limit).

    Optional POST filter operator_pk restricts the export to a single operator.

    POST /panel/work-orders/admin-export/
         Body params:
           pks         (list[int]) — WorkOrder primary keys to export.
           export_mode (str)       — single_sheet | multi_sheet.
           operator_pk (int)       — optional operator filter.

    Returns HttpResponse with Content-Disposition attachment (xlsx).
    Returns HTTP 400 on invalid pks or unknown export_mode.
    ---
    Endpoint de exportación Excel exclusivo para partes digitales y generados
    (WorkOrder.Source.DIGITAL y WorkOrder.Source.GENERATED).
    Diseñado para su uso desde la pestaña Revisados de WorkOrderAdminHistoryView.

    Soporta dos modos de exportación via el campo POST export_mode:

      single_sheet — Una hoja plana con todos los WorkOrderEntryLine de los
        WorkOrders seleccionados, agrupados por nombre de operario y fecha.
        Una fila separadora azul oscuro con el nombre del operario se inserta
        antes de cada nuevo bloque de operario. Los datos se leen de la BD.

      multi_sheet  — Una hoja por operario distinto (worker_name derivado del
        CompanyUser uploaded_by). Cada hoja se construye desde el Excel
        individual almacenado en WorkOrder.excel_file (regenerado si falta).
        Título de hoja truncado a 31 caracteres (límite de Excel).

    El filtro POST opcional operator_pk restringe la exportación a un operario.

    POST /panel/work-orders/admin-export/
         Parámetros del cuerpo:
           pks         (list[int]) — claves primarias de WorkOrder a exportar.
           export_mode (str)       — single_sheet | multi_sheet.
           operator_pk (int)       — filtro de operario opcional.

    Devuelve HttpResponse con Content-Disposition attachment (xlsx).
    Devuelve HTTP 400 ante pks inválidos o export_mode desconocido.
    """

    def post(self, request, *args, **kwargs):
        """
        Builds the admin export Excel file from the selected WorkOrder pks,
        restricted to DIGITAL and GENERATED sources only.
        Supports single_sheet and multi_sheet export modes.
        ---
        Construye el Excel de exportación admin desde los pks de WorkOrder
        seleccionados, restringido a orígenes DIGITAL y GENERATED únicamente.
        Soporta los modos de exportación single_sheet y multi_sheet.
        """
        import io
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
        from django.http import HttpResponse, HttpResponseBadRequest
        from django.utils.timezone import now as tz_now
        from work_order_processor.models import WorkOrderEntry, WorkOrderEntryLine
        from work_order_processor.services import (
            generate_work_order_excel as _gen_excel,
        )

        cu      = request.user.company_user
        company = cu.company

        # ------------------------------------------------------------------
        # Validate export_mode.
        # Validar export_mode.
        # ------------------------------------------------------------------
        export_mode = request.POST.get("export_mode", "single_sheet").strip()
        if export_mode not in ("single_sheet", "multi_sheet"):
            return HttpResponseBadRequest(
                f"# [ADMIN EXPORT] Modo de exportación desconocido: {export_mode!r}."
            )

        # ------------------------------------------------------------------
        # Collect and validate requested pks.
        # Recopilar y validar los pks solicitados.
        # ------------------------------------------------------------------
        raw_pks = request.POST.getlist("pks")
        try:
            pk_list = [int(pk) for pk in raw_pks if pk]
        except (ValueError, TypeError):
            return HttpResponseBadRequest("# [ADMIN EXPORT] Parámetros pks inválidos.")

        if not pk_list:
            return HttpResponseBadRequest(
                "# [ADMIN EXPORT] No se han seleccionado partes para exportar."
            )

        # ------------------------------------------------------------------
        # Resolve optional operator filter.
        # Resolver filtro de operario opcional.
        # ------------------------------------------------------------------
        operator_pk_raw = request.POST.get("operator_pk", "").strip()
        operator_filter = None
        if operator_pk_raw:
            try:
                operator_filter = int(operator_pk_raw)
            except (ValueError, TypeError):
                operator_filter = None

        # ------------------------------------------------------------------
        # Retrieve DONE + reviewed DIGITAL/GENERATED WorkOrders for company.
        # Obtener partes DONE + revisados DIGITAL/GENERATED de la empresa.
        # ------------------------------------------------------------------
        qs = WorkOrder.objects.filter(
            pk__in=pk_list,
            company=company,
            status=WorkOrder.Status.DONE,
            reviewed=True,
            source__in=[WorkOrder.Source.DIGITAL, WorkOrder.Source.GENERATED],
        ).order_by("pk")

        if operator_filter:
            qs = qs.filter(uploaded_by__pk=operator_filter)

        work_orders = list(qs)

        if not work_orders:
            return HttpResponseBadRequest(
                "# [ADMIN EXPORT] Ninguno de los partes seleccionados es digital/generado, "
                "está revisado y en estado DONE."
            )

        # ------------------------------------------------------------------
        # Helper — derive operator name from WorkOrder.uploaded_by.
        # Auxiliar — derivar nombre del operario desde WorkOrder.uploaded_by.
        # ------------------------------------------------------------------
        def _get_operator_name(wo):
            """
            Returns the full name of the operator who submitted the work order,
            or a fallback label if uploaded_by is not set.
            ---
            Devuelve el nombre completo del operario que envió el parte,
            o una etiqueta de reserva si uploaded_by no está establecido.
            """
            if wo.uploaded_by:
                return (
                    wo.uploaded_by.user.get_full_name()
                    or wo.uploaded_by.user.username
                )
            return f"Operario #{wo.pk}"

        # ------------------------------------------------------------------
        # Helper — copy one openpyxl sheet into a destination workbook.
        # Auxiliar — copiar una hoja openpyxl en un libro destino.
        # ------------------------------------------------------------------
        def _copy_sheet(src_sheet, dest_wb, title):
            """
            Copies src_sheet (cells, styles, column widths, row heights) into
            a new sheet named title in dest_wb.
            ---
            Copia src_sheet (celdas, estilos, anchos de columna, alturas de
            fila) en una nueva hoja llamada title en dest_wb.
            """
            dest_sheet = dest_wb.create_sheet(title=title[:31])
            for row in src_sheet.iter_rows():
                for cell in row:
                    dest_cell = dest_sheet.cell(
                        row=cell.row, column=cell.column, value=cell.value
                    )
                    if cell.has_style:
                        dest_cell.font          = cell.font.copy()
                        dest_cell.fill          = cell.fill.copy()
                        dest_cell.alignment     = cell.alignment.copy()
                        dest_cell.border        = cell.border.copy()
                        dest_cell.number_format = cell.number_format
            for col_letter, col_dim in src_sheet.column_dimensions.items():
                dest_sheet.column_dimensions[col_letter].width = col_dim.width
            for row_num, row_dim in src_sheet.row_dimensions.items():
                dest_sheet.row_dimensions[row_num].height = row_dim.height
            return dest_sheet

        # ==================================================================
        # MODE: single_sheet
        # Reads WorkOrderEntryLine records directly from the DB.
        # Groups by operator name (asc) then work_date (asc).
        # Inserts a dark-blue separator row before each new operator block.
        # ==================================================================
        # MODO: single_sheet
        # Lee WorkOrderEntryLine directamente de la BD.
        # Agrupa por nombre de operario (asc) y work_date (asc).
        # Inserta fila separadora azul oscuro antes de cada nuevo operario.
        # ==================================================================
        if export_mode == "single_sheet":

            wo_map = {wo.pk: wo for wo in work_orders}

            rows = (
                WorkOrderEntryLine.objects
                .filter(entry__work_order__pk__in=list(wo_map.keys()))
                .select_related(
                    "entry__work_order",
                    "entry",
                    "machine_asset",
                )
                .order_by(
                    "entry__work_order__uploaded_by__user__last_name",
                    "entry__work_order__uploaded_by__user__first_name",
                    "entry__work_date",
                    "entry__work_order__pk",
                    "line_number",
                )
            )

            wb   = openpyxl.Workbook()
            ws   = wb.active
            ws.title = "Partes digitales"

            # Header row style — Estilo de fila de encabezado.
            header_fill = PatternFill("solid", fgColor="1F3864")
            header_font = Font(bold=True, color="FFFFFF", size=10)
            headers = [
                "Operario", "Fecha", "Máquina / CdG",
                "Descripción avería", "Notas reparación",
                "H. inicio", "H. fin", "Δ Horas",
            ]
            for col_idx, h in enumerate(headers, start=1):
                cell            = ws.cell(row=1, column=col_idx, value=h)
                cell.fill       = header_fill
                cell.font       = header_font
                cell.alignment  = Alignment(horizontal="center", vertical="center")

            # Separator row style — Estilo de fila separadora de operario.
            sep_fill = PatternFill("solid", fgColor="2F5496")
            sep_font = Font(bold=True, color="FFFFFF", size=10)

            current_row      = 2
            current_operator = None

            for line in rows:
                wo            = line.entry.work_order
                operator_name = _get_operator_name(wo)
                work_date     = line.entry.work_date

                # Insert separator row when operator changes.
                # Insertar fila separadora cuando cambia el operario.
                if operator_name != current_operator:
                    current_operator = operator_name
                    sep_cell = ws.cell(
                        row=current_row, column=1, value=operator_name
                    )
                    sep_cell.fill      = sep_fill
                    sep_cell.font      = sep_font
                    sep_cell.alignment = Alignment(vertical="center")
                    ws.merge_cells(
                        start_row=current_row, start_column=1,
                        end_row=current_row,   end_column=len(headers),
                    )
                    current_row += 1

                ws.cell(row=current_row, column=1, value=operator_name)
                ws.cell(row=current_row, column=2,
                        value=work_date.strftime("%d/%m/%Y") if work_date else "")
                ws.cell(row=current_row, column=3,
                        value=line.machine_asset.code if line.machine_asset else line.machine_raw or "")
                ws.cell(row=current_row, column=4, value=line.fault_description or "")
                ws.cell(row=current_row, column=5, value=line.repair_notes or "")
                ws.cell(row=current_row, column=6,
                        value=line.hc.strftime("%H:%M") if line.hc else "")
                ws.cell(row=current_row, column=7,
                        value=line.hf.strftime("%H:%M") if line.hf else "")
                ws.cell(row=current_row, column=8,
                        value=float(line.delta_hours) if line.delta_hours is not None else "")
                current_row += 1

            # Auto-fit column widths — Ajuste automático de anchos de columna.
            for col in ws.columns:
                max_len = max(
                    (len(str(cell.value)) for cell in col if cell.value),
                    default=10,
                )
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)

            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            filename = f"partes_digitales_{tz_now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            response = HttpResponse(
                buf.read(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response

        # ==================================================================
        # MODE: multi_sheet
        # One sheet per distinct operator derived from uploaded_by.
        # Copies the first sheet of each WorkOrder.excel_file.
        # Regenerates the Excel on-the-fly if the file is missing.
        # ==================================================================
        # MODO: multi_sheet
        # Una hoja por operario distinto derivado de uploaded_by.
        # Copia la primera hoja de cada WorkOrder.excel_file.
        # Regenera el Excel al vuelo si el archivo falta.
        # ==================================================================
        dest_wb = openpyxl.Workbook()
        dest_wb.remove(dest_wb.active)   # remove default blank sheet / eliminar hoja vacía por defecto

        # Group work orders by operator name.
        # Agrupar partes por nombre de operario.
        from collections import defaultdict
        operator_groups = defaultdict(list)
        for wo in work_orders:
            operator_groups[_get_operator_name(wo)].append(wo)

        for operator_name, wo_list in sorted(operator_groups.items()):
            sheet_title = operator_name[:31]
            sheet_added = False

            for wo in wo_list:
                # Regenerate Excel if missing.
                # Regenerar Excel si falta.
                if not wo.excel_file or not wo.excel_file.name:
                    try:
                        _gen_excel(wo.pk)
                        wo.refresh_from_db(fields=["excel_file"])
                    except Exception:
                        logger.warning(
                            "# [AdminExport] No se pudo regenerar Excel para WorkOrder #%d.",
                            wo.pk,
                        )
                        continue

                try:
                    src_wb     = openpyxl.load_workbook(wo.excel_file.path)
                    src_sheet  = src_wb.worksheets[0]
                    if not sheet_added:
                        _copy_sheet(src_sheet, dest_wb, sheet_title)
                        sheet_added = True
                    else:
                        # Append rows of subsequent WOs to the existing sheet.
                        # Añadir filas de WOs posteriores a la hoja existente.
                        dest_sheet = dest_wb[sheet_title]
                        start_row  = dest_sheet.max_row + 1
                        for row in src_sheet.iter_rows(min_row=2):
                            for cell in row:
                                dest_cell = dest_sheet.cell(
                                    row=start_row + cell.row - 2,
                                    column=cell.column,
                                    value=cell.value,
                                )
                                if cell.has_style:
                                    dest_cell.font      = cell.font.copy()
                                    dest_cell.fill      = cell.fill.copy()
                                    dest_cell.alignment = cell.alignment.copy()
                except Exception as exc:
                    logger.warning(
                        "# [AdminExport] Error procesando Excel WorkOrder #%d: %s",
                        wo.pk, exc,
                    )
                    continue

        if not dest_wb.worksheets:
            return HttpResponseBadRequest(
                "# [ADMIN EXPORT] No se pudo generar ninguna hoja Excel. "
                "Verifica que los partes seleccionados tienen Excel generado."
            )

        buf = io.BytesIO()
        dest_wb.save(buf)
        buf.seek(0)

        filename = f"partes_digitales_multi_{tz_now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        response = HttpResponse(
            buf.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class AnalyticsProfileDeleteView(AdminRoleRequiredMixin, View):
    """
    JSON endpoint for deleting a single AnalyticsProfile by primary key.

    DELETE /panel/analytics/profiles/<pk>/
           Deletes the profile only if it belongs to the authenticated
           CompanyUser. Returns HTTP 200 on success, HTTP 404 if not found
           or owned by a different user.
    ---
    Endpoint JSON para eliminar un AnalyticsProfile concreto por clave primaria.

    DELETE /panel/analytics/profiles/<pk>/
           Elimina el perfil solo si pertenece al CompanyUser autenticado.
           Devuelve HTTP 200 en caso de éxito, HTTP 404 si no se encuentra
           o pertenece a otro usuario.
    """

    def delete(self, request, pk):
        """
        Deletes the AnalyticsProfile identified by pk, scoped to the current user.
        ---
        Elimina el AnalyticsProfile identificado por pk, acotado al usuario actual.
        """
        from django.http import JsonResponse

        try:
            company_user = request.user.company_user
        except AttributeError:
            return JsonResponse({"error": "Sin perfil de empresa asociado."}, status=403)

        try:
            profile = AnalyticsProfile.objects.get(pk=pk, company_user=company_user)
        except AnalyticsProfile.DoesNotExist:
            return JsonResponse({"error": "Perfil no encontrado."}, status=404)

        nombre = profile.nombre
        profile.delete()
        return JsonResponse({"deleted": True, "nombre": nombre})


# ===========================================================================
# Fleet / Centros de gasto — Hito 12 Paso 4
# ===========================================================================

class MachineAssetListView(AdminRoleRequiredMixin, View):
    """
    List view for MachineAsset records belonging to the authenticated user's
    company. Supports filtering by family and is_active status.
    Renders the full list page on GET. HTMX partial refresh is triggered by
    the filter controls in the template.

    GET /panel/fleet/

    ---

    Vista de listado de registros MachineAsset pertenecientes a la empresa
    del usuario autenticado. Soporta filtrado por family e is_active.
    Renderiza la página completa en GET. El refresco parcial HTMX se activa
    desde los controles de filtro del template.

    GET /panel/fleet/
    """

    template_name         = "panel/fleet/list.html"
    template_name_partial = "panel/fleet/_table_fragment.html"

    def _get_own_presence(self, company_user):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        return PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

    def _build_queryset(self, company, request):
        """
        Builds the filtered MachineAsset queryset from GET parameters.
        Supported filters: family (str), is_active ('1'=active, '0'=inactive, ''=all).
        ---
        Construye el queryset filtrado de MachineAsset desde los parámetros GET.
        Filtros soportados: family (str), is_active ('1'=activo, '0'=inactivo, ''=todos).
        """
        from fleet.models import MachineAsset

        qs = MachineAsset.objects.filter(company=company).order_by(
            "company_code", "family", "code"
        )

        family_filter = request.GET.get("family", "").strip()
        if family_filter:
            qs = qs.filter(family__iexact=family_filter)

        active_filter = request.GET.get("is_active", "")
        if active_filter == "1":
            qs = qs.filter(is_active=True)
        elif active_filter == "0":
            qs = qs.filter(is_active=False)

        return qs

    def _get_families(self, company):
        """
        Returns a sorted list of distinct family values for the company's assets.
        Used to populate the family filter dropdown.
        ---
        Retorna una lista ordenada de valores de family distintos para los activos
        de la empresa. Se usa para poblar el desplegable de filtro de familia.
        """
        from fleet.models import MachineAsset

        return (
            MachineAsset.objects
            .filter(company=company)
            .exclude(family="")
            .values_list("family", flat=True)
            .distinct()
            .order_by("family")
        )

    def get(self, request, *args, **kwargs):
        """
        Renders the fleet list page or a partial HTMX table fragment.
        Detects HTMX requests via the HX-Request header and returns only
        the table fragment for partial page updates.
        ---
        Renderiza la página de listado de flota o un fragmento parcial HTMX.
        Detecta peticiones HTMX via la cabecera HX-Request y devuelve solo
        el fragmento de tabla para actualizaciones parciales.
        """
        from fleet.models import MachineAsset
        from panel.forms import MachineAssetForm

        company_user = request.user.company_user
        company      = company_user.company
        qs           = self._build_queryset(company, request)
        families     = self._get_families(company)
        form         = MachineAssetForm()

        ctx = {
            "company":      company,
            "company_user": company_user,
            "own_presence": self._get_own_presence(company_user),
            "active_nav":   "fleet",
            "assets":       qs,
            "families":     families,
            "form":         form,
            "filter_family":    request.GET.get("family", ""),
            "filter_is_active": request.GET.get("is_active", ""),
        }

        if request.headers.get("HX-Request"):
            return render(request, self.template_name_partial, ctx)
        return render(request, self.template_name, ctx)


class MachineAssetCreateView(AdminRoleRequiredMixin, View):
    """
    Creates a new MachineAsset for the authenticated user's company.
    Accepts HTMX POST requests and returns an updated table fragment on success,
    or a form fragment with validation errors on failure.

    POST /panel/fleet/create/

    ---

    Crea un nuevo MachineAsset para la empresa del usuario autenticado.
    Acepta peticiones POST HTMX y devuelve un fragmento de tabla actualizado
    en caso de éxito, o un fragmento de formulario con errores en caso de fallo.

    POST /panel/fleet/create/
    """

    def post(self, request, *args, **kwargs):
        """
        Validates the form and creates the MachineAsset. On success returns
        the updated table fragment. On failure returns the form with errors.
        ---
        Valida el formulario y crea el MachineAsset. En caso de éxito devuelve
        el fragmento de tabla actualizado. En caso de fallo devuelve el formulario
        con errores.
        """
        from fleet.models import MachineAsset
        from panel.forms import MachineAssetForm

        company_user = request.user.company_user
        company      = company_user.company
        form         = MachineAssetForm(request.POST)

        if form.is_valid():
            asset         = form.save(commit=False)
            asset.company = company
            asset.code    = asset.code.strip().upper()
            asset.save()
            qs = MachineAsset.objects.filter(company=company).order_by(
                "company_code", "family", "code"
            )
            return render(request, "panel/fleet/_table_fragment.html", {
                "assets":       qs,
                "company_user": company_user,
                "company":      company,
            })

        return render(request, "panel/fleet/_form_fragment.html", {
            "form":         form,
            "company_user": company_user,
            "company":      company,
            "form_action":  "create",
        })


class MachineAssetUpdateView(AdminRoleRequiredMixin, View):
    """
    Updates an existing MachineAsset belonging to the authenticated user's company.
    Accepts HTMX POST requests and returns an updated table fragment on success,
    or a form fragment with validation errors on failure.

    POST /panel/fleet/<pk>/update/

    ---

    Actualiza un MachineAsset existente perteneciente a la empresa del usuario
    autenticado. Acepta peticiones POST HTMX y devuelve un fragmento de tabla
    actualizado en caso de éxito, o un formulario con errores en caso de fallo.

    POST /panel/fleet/<pk>/update/
    """

    def get(self, request, pk, *args, **kwargs):
        """
        Returns the pre-filled edit form fragment for the given asset pk.
        Called via HTMX GET from the edit modal trigger in the table.
        Returns 404 if the asset does not belong to the company.
        ---
        Devuelve el fragmento de formulario de edición pre-relleno para el pk dado.
        Invocado via HTMX GET desde el disparador del modal de edición en la tabla.
        Devuelve 404 si el activo no pertenece a la empresa.
        """
        from fleet.models import MachineAsset
        from panel.forms import MachineAssetForm
        from django.http import Http404

        company_user = request.user.company_user
        company      = company_user.company

        try:
            asset = MachineAsset.objects.get(pk=pk, company=company)
        except MachineAsset.DoesNotExist:
            raise Http404

        form = MachineAssetForm(instance=asset)
        return render(request, "panel/fleet/_form_fragment.html", {
            "form":         form,
            "asset":        asset,
            "company_user": company_user,
            "company":      company,
            "form_action":  "update",
        })

    def post(self, request, pk, *args, **kwargs):
        """
        Validates the form and updates the MachineAsset identified by pk.
        Returns 404 if the asset does not belong to the company.
        ---
        Valida el formulario y actualiza el MachineAsset identificado por pk.
        Devuelve 404 si el activo no pertenece a la empresa.
        """
        from fleet.models import MachineAsset
        from panel.forms import MachineAssetForm
        from django.http import Http404

        company_user = request.user.company_user
        company      = company_user.company

        try:
            asset = MachineAsset.objects.get(pk=pk, company=company)
        except MachineAsset.DoesNotExist:
            raise Http404

        form = MachineAssetForm(request.POST, instance=asset)

        if form.is_valid():
            updated       = form.save(commit=False)
            updated.code  = updated.code.strip().upper()
            updated.save()
            qs = MachineAsset.objects.filter(company=company).order_by(
                "company_code", "family", "code"
            )
            return render(request, "panel/fleet/_table_fragment.html", {
                "assets":       qs,
                "company_user": company_user,
                "company":      company,
            })

        return render(request, "panel/fleet/_form_fragment.html", {
            "form":         form,
            "asset":        asset,
            "company_user": company_user,
            "company":      company,
            "form_action":  "update",
        })


class MachineAssetDeactivateView(AdminRoleRequiredMixin, View):
    """
    Sets is_active=False on a MachineAsset belonging to the authenticated user's
    company. Does not delete the record — preserves historical data integrity.
    Returns an updated table row fragment via HTMX.

    POST /panel/fleet/<pk>/deactivate/

    ---

    Establece is_active=False en un MachineAsset perteneciente a la empresa del
    usuario autenticado. No elimina el registro — preserva la integridad del
    histórico. Devuelve un fragmento de fila de tabla actualizado via HTMX.

    POST /panel/fleet/<pk>/deactivate/
    """

    def post(self, request, pk, *args, **kwargs):
        """
        Marks the asset as inactive and returns the updated table fragment.
        Returns 404 if the asset does not belong to the company.
        ---
        Marca el activo como inactivo y devuelve el fragmento de tabla actualizado.
        Devuelve 404 si el activo no pertenece a la empresa.
        """
        from fleet.models import MachineAsset
        from django.http import Http404

        company_user = request.user.company_user
        company      = company_user.company

        try:
            asset = MachineAsset.objects.get(pk=pk, company=company)
        except MachineAsset.DoesNotExist:
            raise Http404

        asset.is_active = False
        asset.save(update_fields=["is_active"])

        qs = MachineAsset.objects.filter(company=company).order_by(
            "company_code", "family", "code"
        )
        return render(request, "panel/fleet/_table_fragment.html", {
            "assets":       qs,
            "company_user": company_user,
            "company":      company,
        })


class MachineAssetReactivateView(AdminRoleRequiredMixin, View):
    """
    Sets is_active=True on a MachineAsset belonging to the authenticated user's
    company. Counterpart to MachineAssetDeactivateView — allows reversing an
    accidental deactivation. Returns an updated table fragment via HTMX.

    POST /panel/fleet/<pk>/reactivate/

    ---

    Establece is_active=True en un MachineAsset perteneciente a la empresa del
    usuario autenticado. Contraparte de MachineAssetDeactivateView — permite
    revertir una baja accidental. Devuelve un fragmento de tabla actualizado
    via HTMX.

    POST /panel/fleet/<pk>/reactivate/
    """

    def post(self, request, pk, *args, **kwargs):
        """
        Marks the asset as active and returns the updated table fragment.
        Returns 404 if the asset does not belong to the company.
        ---
        Marca el activo como activo y devuelve el fragmento de tabla actualizado.
        Devuelve 404 si el activo no pertenece a la empresa.
        """
        from fleet.models import MachineAsset
        from django.http import Http404

        company_user = request.user.company_user
        company      = company_user.company

        try:
            asset = MachineAsset.objects.get(pk=pk, company=company)
        except MachineAsset.DoesNotExist:
            raise Http404

        asset.is_active = True
        asset.save(update_fields=["is_active"])

        qs = MachineAsset.objects.filter(company=company).order_by(
            "company_code", "family", "code"
        )
        return render(request, "panel/fleet/_table_fragment.html", {
            "assets":       qs,
            "company_user": company_user,
            "company":      company,
        })


class MachineAssetDeleteView(AdminRoleRequiredMixin, View):
    """
    Permanently deletes a MachineAsset only if it has no associated
    WorkOrderEntryLine records (referential integrity guard).
    Only available to ADMIN role.
    Returns an updated table fragment on success or a JSON error on failure.

    POST /panel/fleet/<pk>/delete/

    ---

    Elimina permanentemente un MachineAsset solo si no tiene registros
    WorkOrderEntryLine asociados (guardia de integridad referencial).
    Solo disponible para el rol ADMIN.
    Devuelve un fragmento de tabla actualizado en caso de éxito o un error
    JSON en caso de fallo.

    POST /panel/fleet/<pk>/delete/
    """

    def post(self, request, pk, *args, **kwargs):
        """
        Deletes the asset if it has no linked work-order lines.
        Returns HTTP 409 with a JSON error message if linked lines exist.
        Returns 404 if the asset does not belong to the company.
        ---
        Elimina el activo si no tiene líneas de parte asociadas.
        Devuelve HTTP 409 con un mensaje de error JSON si existen líneas vinculadas.
        Devuelve 404 si el activo no pertenece a la empresa.
        """
        from fleet.models import MachineAsset
        from django.http import Http404, JsonResponse

        company_user = request.user.company_user
        company      = company_user.company

        try:
            asset = MachineAsset.objects.get(pk=pk, company=company)
        except MachineAsset.DoesNotExist:
            raise Http404

        # Referential integrity guard — block deletion if work-order lines exist.
        # Guardia de integridad referencial — bloquear si existen líneas de parte.
        if asset.work_order_lines.exists():
            return JsonResponse(
                {
                    "error": (
                        f"No se puede eliminar '{asset.code}': tiene partes de trabajo "
                        f"asociados. Use 'Dar de baja' para desactivarlo."
                    )
                },
                status=409,
            )

        asset.delete()

        qs = MachineAsset.objects.filter(company=company).order_by(
            "company_code", "family", "code"
        )
        return render(request, "panel/fleet/_table_fragment.html", {
            "assets":       qs,
            "company_user": company_user,
            "company":      company,
        })


class WorkshopAssetDetailView(WorkshopRequiredMixin, View):
    """
    JSON endpoint that returns the meter-reading flags and current reference
    values for a single MachineAsset identified by its code, scoped to the
    authenticated user's company.

    Used by the three operator entry templates (form_entry, stt_entry,
    confirm_entry) to reveal/hide the odometer and hourmeter input fields
    dynamically when the operator selects a work block's Centre de Gasto.

    GET /panel/operator/assets/detail/?code=XX
        Returns HTTP 200 with JSON payload on success.
        Returns HTTP 404 if the asset does not exist for the company.
        Returns HTTP 400 if the `code` parameter is absent or blank.

    Response schema:
        {
          "has_odometer":     bool,
          "has_engine_hours": bool,
          "has_crane_hours":  bool,
          "mileage":          float | null,
          "hours":            float | null
        }

    ---

    Endpoint JSON que devuelve los flags de lecturas de contadores y los
    valores de referencia actuales para un MachineAsset identificado por su
    código, acotado a la empresa del usuario autenticado.

    Usado por los tres templates de entrada del operario (form_entry,
    stt_entry, confirm_entry) para revelar/ocultar dinámicamente los campos
    de odómetro y horómetro cuando el operario selecciona el Centro de Gasto
    de un bloque de trabajo.

    GET /panel/operator/assets/detail/?code=XX
        Devuelve HTTP 200 con payload JSON en caso de éxito.
        Devuelve HTTP 404 si el activo no existe para la empresa.
        Devuelve HTTP 400 si el parámetro `code` está ausente o en blanco.

    Esquema de respuesta:
        {
          "has_odometer":     bool,
          "has_engine_hours": bool,
          "has_crane_hours":  bool,
          "mileage":          float | null,
          "hours":            float | null
        }
    """

    def get(self, request, *args, **kwargs):
        """
        Returns meter-reading flags and reference values for the requested asset.
        Scoped to the authenticated user's company. Returns HTTP 400 on missing
        code and HTTP 404 if the asset does not exist for the company.
        ---
        Devuelve los flags de contadores y valores de referencia del activo
        solicitado. Acotado a la empresa del usuario autenticado. Devuelve
        HTTP 400 si falta el código y HTTP 404 si el activo no existe.
        """
        from django.http import JsonResponse
        from fleet.models import MachineAsset

        code = request.GET.get("code", "").strip()
        if not code:
            return JsonResponse(
                {"error": "Parámetro 'code' obligatorio."},
                status=400,
            )

        company = request.user.company_user.company

        try:
            asset = MachineAsset.objects.get(
                code__iexact=code,
                company=company,
            )
        except MachineAsset.DoesNotExist:
            return JsonResponse(
                {"error": f"Activo '{code}' no encontrado en catálogo."},
                status=404,
            )

        return JsonResponse({
            "has_odometer":     asset.has_odometer,
            "has_engine_hours": asset.has_engine_hours,
            "has_crane_hours":  asset.has_crane_hours,
            "first_repair":     asset.first_repair,
            "mileage":          float(asset.mileage) if asset.mileage is not None else None,
            "hours":            float(asset.hours)   if asset.hours   is not None else None,
        })


class WorkOrderMachineFilterView(SupervisorAccessMixin, View):
    """
    JSON endpoint returning distinct MachineAsset codes present in the
    WorkOrderEntryLine records of DIGITAL/GENERATED WorkOrders for the
    authenticated company, optionally filtered by operator and date range.
    Used by the admin history machine autocomplete (Bug B fix).

    GET /panel/work-orders/machines/
        Optional GET params:
          operator_pk (int)  — filter by uploaded_by CompanyUser pk.
          date_from   (str)  — ISO date YYYY-MM-DD start of range.
          date_to     (str)  — ISO date YYYY-MM-DD end of range.
        Returns: {"results": ["G12", "A44", ...]}

    Accessible to SUPERVISOR and ADMIN roles (SupervisorAccessMixin).

    ---

    Endpoint JSON que devuelve los códigos de MachineAsset distintos presentes
    en los WorkOrderEntryLine de los WorkOrders DIGITAL/GENERATED de la empresa
    autenticada, con filtro opcional por operario y rango de fechas.
    Usado por el autocompletado de máquina de admin_history (corrección Bug B).

    GET /panel/work-orders/machines/
        Parámetros GET opcionales:
          operator_pk (int)  — filtrar por pk de CompanyUser uploaded_by.
          date_from   (str)  — fecha ISO YYYY-MM-DD inicio del rango.
          date_to     (str)  — fecha ISO YYYY-MM-DD fin del rango.
        Devuelve: {"results": ["G12", "A44", ...]}

    Accesible para los roles SUPERVISOR y ADMIN (SupervisorAccessMixin).
    """

    def get(self, request, *args, **kwargs):
        """
        Returns distinct MachineAsset codes present in the filtered WorkOrders.
        ---
        Devuelve los códigos de MachineAsset distintos en los WorkOrders filtrados.
        """
        from django.http import JsonResponse
        from datetime import datetime as _dt_mf
        from work_order_processor.models import WorkOrderEntryLine

        company       = request.user.company_user.company
        operator_pk   = request.GET.get("operator_pk", "").strip()
        date_from_raw = request.GET.get("date_from", "").strip()
        date_to_raw   = request.GET.get("date_to",   "").strip()
        q_raw         = request.GET.get("q",         "").strip()

        def _parse_iso(val):
            """Parses YYYY-MM-DD string, returns date or None.
            --- Parsea cadena YYYY-MM-DD, devuelve date o None."""
            if not val:
                return None
            try:
                return _dt_mf.strptime(val, "%Y-%m-%d").date()
            except ValueError:
                return None

        date_from = _parse_iso(date_from_raw)
        date_to   = _parse_iso(date_to_raw)

        # Base queryset — scoped to DIGITAL/GENERATED sources for the company.
        # Queryset base — acotado a orígenes DIGITAL/GENERATED de la empresa.
        qs = (
            WorkOrderEntryLine.objects
            .filter(
                entry__work_order__company=company,
                entry__work_order__source__in=[
                    WorkOrder.Source.DIGITAL,
                    WorkOrder.Source.GENERATED,
                ],
                machine_asset__isnull=False,
            )
        )

        # Optional operator filter / Filtro de operario opcional.
        if operator_pk:
            try:
                qs = qs.filter(
                    entry__work_order__uploaded_by__pk=int(operator_pk),
                    entry__work_order__uploaded_by__company=company,
                )
            except (ValueError, TypeError):
                pass

        # Optional date range filter / Filtro de rango de fechas opcional.
        if date_from:
            qs = qs.filter(entry__work_date__gte=date_from)
        if date_to:
            qs = qs.filter(entry__work_date__lte=date_to)

        # Optional machine code icontains filter / Filtro icontains de codigo de maquina.
        if q_raw:
            qs = qs.filter(machine_asset__code__icontains=q_raw)

        codes = (
            qs
            .values_list("machine_asset__code", flat=True)
            .distinct()
            .order_by("machine_asset__code")
        )

        return JsonResponse({"results": list(codes)})



class WorkOrderDescriptionAutocompleteView(WorkshopRequiredMixin, View):
    """
    Returns up to 8 unique values from WorkOrderEntryLine.fault_description
    or WorkOrderEntryLine.repair_notes that contain the query string (case-
    insensitive). Scoped to the authenticated user's company.

    Used by the description typeahead widget (_description_typeahead.html)
    in the three operator entry templates (form_entry, stt_entry,
    confirm_entry).

    GET /panel/operator/descriptions/?field=fault_description&q=XXX
    GET /panel/operator/descriptions/?field=repair_notes&q=XXX

    Response: {"results": ["value1", "value2", ...]}

    ---

    Devuelve hasta 8 valores únicos de WorkOrderEntryLine.fault_description
    o WorkOrderEntryLine.repair_notes que contengan la cadena de búsqueda
    (insensible a mayúsculas). Restringido a la empresa del usuario autenticado.

    Utilizado por el widget de typeahead de descripciones
    (_description_typeahead.html) en los tres templates de entrada del
    operario (form_entry, stt_entry, confirm_entry).

    GET /panel/operator/descriptions/?field=fault_description&q=XXX
    GET /panel/operator/descriptions/?field=repair_notes&q=XXX

    Respuesta: {"results": ["valor1", "valor2", ...]}
    """

    # Whitelist of allowed field names to prevent arbitrary field injection.
    # Lista blanca de campos permitidos para evitar inyección de campo arbitrario.
    _ALLOWED_FIELDS = {"fault_description", "repair_notes"}
    # Minimum query length to avoid full-table scans on short strings.
    # Longitud mínima de consulta para evitar escaneos completos con cadenas cortas.
    _MIN_QUERY_LEN  = 2
    # Maximum number of suggestions returned per request.
    # Número máximo de sugerencias devueltas por petición.
    _MAX_RESULTS    = 8

    def get(self, request, *args, **kwargs):
        """
        Validates the `field` and `q` parameters, queries the database and
        returns a JSON list of matching description values.

        Returns {"results": []} for invalid field, missing or too-short query.

        ---

        Valida los parámetros `field` y `q`, consulta la base de datos y
        devuelve una lista JSON de valores de descripción coincidentes.

        Devuelve {"results": []} para campo inválido, consulta ausente o
        demasiado corta.
        """
        from django.http import JsonResponse
        from work_order_processor.models import WorkOrderEntryLine

        field = request.GET.get("field", "").strip()
        q     = request.GET.get("q",     "").strip()

        # Validate field against whitelist — reject unknown fields immediately.
        # Validar campo contra la lista blanca — rechazar campos desconocidos.
        if field not in self._ALLOWED_FIELDS:
            return JsonResponse({"results": []})

        # Enforce minimum query length to avoid overly broad results.
        # Aplicar longitud mínima de consulta para evitar resultados demasiado amplios.
        if len(q) < self._MIN_QUERY_LEN:
            return JsonResponse({"results": []})

        company_user = request.user.company_user
        company      = company_user.company

        # Build the icontains filter dynamically using the validated field name.
        # Construir el filtro icontains dinámicamente usando el nombre de campo validado.
        lookup = {field + "__icontains": q}

        qs = (
            WorkOrderEntryLine.objects
            .filter(entry__work_order__company=company, **lookup)
            .exclude(**{field: ""})
            .values_list(field, flat=True)
            .distinct()
            .order_by(field)
            [:self._MAX_RESULTS]
        )

        return JsonResponse({"results": list(qs)})

