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
            .filter(company=company, status__in=[
                WorkOrder.Status.PENDING,
                WorkOrder.Status.PROCESSING,
            ])
            .order_by("-upload_date")
        )
        wo_error = (
            WorkOrder.objects
            .filter(company=company, status=WorkOrder.Status.ERROR)
            .order_by("-upload_date")
        )
        wo_pending = (
            WorkOrder.objects
            .filter(company=company, status=WorkOrder.Status.DONE, reviewed=False)
            .order_by("-upload_date")
        )
        wo_reviewed = (
            WorkOrder.objects
            .filter(company=company, status=WorkOrder.Status.DONE, reviewed=True)
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
                         Recomputes delta_horas from hc/hf and re-resolves
                         machine_asset from the updated maquina_norm.
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
                         Recalcula delta_horas desde hc/hf y re-resuelve machine_asset
                         desde el maquina_norm actualizado.
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
            # delta_horas across all its lines. None values are skipped.
            # Used by _entry_group_fragment.html to render the day-total badge.
            #
            # Calcular el total de horas trabajadas en esta entrada (día) sumando
            # delta_horas de todas sus líneas. Los valores None se omiten.
            # Usado por _entry_group_fragment.html para el badge de total de jornada.
            day_total_raw = sum(
                (l.delta_horas for l in lines if l.delta_horas is not None),
                0,
            )
            day_total = round(day_total_raw, 2) if any(
                l.delta_horas is not None for l in lines
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

        return render(request, self.template_name, {
            "company":      company,
            "company_user": company_user,
            "own_presence": self._get_own_presence(company_user),
            "active_nav":   "work_orders",
            "work_order":   work_order,
            "groups":       groups,
        })

    def post(self, request, pk):
        """
        Dispatches POST actions: save_line or regenerate.
        ---
        Despacha las acciones POST: save_line o regenerate.
        """
        from work_order_processor.models import WorkOrderEntry, WorkOrderEntryLine
        from work_order_processor.services import (
            _compute_delta_horas,
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

            # Parse and update maquina_norm + machine_asset.
            # Parsear y actualizar maquina_norm + machine_asset.
            raw_norm = request.POST.get("maquina_norm", "").strip()
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
            delta = _compute_delta_horas(hc, hf)

            # Parse flags from comma-separated string.
            # Parsear flags desde cadena separada por comas.
            flags_raw = request.POST.get("flags", "").strip()
            flags     = [f.strip() for f in flags_raw.split(",") if f.strip()]                         if flags_raw else []

            # Persist changes.
            # Persistir cambios.
            line.maquina_norm       = norm
            line.machine_asset      = asset
            line.descripcion_averia = request.POST.get("descripcion_averia", "").strip()
            line.reparacion         = request.POST.get("reparacion", "").strip()
            line.hc                 = hc
            line.hf                 = hf
            line.or_val             = request.POST.get("or_val", "").strip()
            line.delta_horas        = delta
            line.flags              = flags
            line.save(update_fields=[
                "maquina_norm", "machine_asset", "descripcion_averia",
                "reparacion", "hc", "hf", "or_val", "delta_horas", "flags",
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
           maquina_norm        : str  — normalised machine code.
           descripcion_averia  : str  — fault description.
           reparacion          : str  — repair description.
           hc                  : str  — start time  HH:MM.
           hf                  : str  — end time    HH:MM.
           or_val              : str  — repair order reference.
           flags               : str  — comma-separated flag list.
         Server recomputes delta_horas from hc/hf and re-resolves machine_asset
         from the updated maquina_norm. Returns the rendered _line_row.html partial
         (a single <tr> element) with HTTP 200.
         Returns HTTP 404 if the WorkOrder or line do not exist or belong to another
         company. Returns HTTP 400 on an unexpected processing error.

    Restricted to the ADMIN role (AdminRoleRequiredMixin).

    ---

    Endpoint HTMX que guarda un único WorkOrderEntryLine y devuelve la fila <tr>
    actualizada como fragmento HTML consumido por el editor inline.

    POST /panel/work-orders/<wo_pk>/lines/<line_pk>/save/
         Campos POST esperados (todos opcionales — los ausentes se tratan como vacíos):
           maquina_norm        : str  — código de máquina normalizado.
           descripcion_averia  : str  — descripción de la avería.
           reparacion          : str  — descripción de la reparación.
           hc                  : str  — hora de comienzo HH:MM.
           hf                  : str  — hora de fin      HH:MM.
           or_val              : str  — referencia de orden de reparación.
           flags               : str  — lista de flags separada por comas.
         El servidor recalcula delta_horas desde hc/hf y re-resuelve machine_asset
         desde el maquina_norm actualizado. Devuelve el parcial _line_row.html
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
            _compute_delta_horas,
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
        # Parse maquina_norm and re-resolve machine_asset.
        # Parsear maquina_norm y re-resolver machine_asset.
        # ------------------------------------------------------------------
        raw_norm = request.POST.get("maquina_norm", "").strip()
        norm     = _normalise_machine_code(raw_norm) if raw_norm else raw_norm
        asset    = _resolve_machine_asset(norm, company=company) if norm else None

        # ------------------------------------------------------------------
        # Parse hc / hf and recompute delta_horas.
        # Parsear hc / hf y recalcular delta_horas.
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
        delta = _compute_delta_horas(hc, hf)

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
        line.maquina_norm       = norm
        line.machine_asset      = asset
        line.descripcion_averia = request.POST.get("descripcion_averia", "").strip()
        line.reparacion         = request.POST.get("reparacion", "").strip()
        line.hc                 = hc
        line.hf                 = hf
        line.or_val             = request.POST.get("or_val", "").strip()
        line.delta_horas        = delta
        line.flags              = flags
        line.save(update_fields=[
            "maquina_norm", "machine_asset", "descripcion_averia",
            "reparacion", "hc", "hf", "or_val", "delta_horas", "flags",
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
                maquina_norm="",
                maquina_raw="",
                descripcion_averia="",
                reparacion="",
                hc=None,
                hf=None,
                or_val="",
                delta_horas=None,
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
         overwrites only the fields of the target line (maquina_raw, maquina_norm,
         machine_asset, descripcion_averia, reparacion, hc, hf, or_val,
         delta_horas, flags) and returns the rendered _line_row.html partial
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
         sobreescribe únicamente los campos de la línea objetivo (maquina_raw,
         maquina_norm, machine_asset, descripcion_averia, reparacion, hc, hf,
         or_val, delta_horas, flags) y devuelve el parcial _line_row.html
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
            _compute_delta_horas,
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
        # in that case restore re-resolves machine_asset from the stored maquina_norm
        # and recomputes delta_horas from the stored hc/hf, preserving all other fields.
        #
        # Guardia: raw_gemini_response debe existir para partes con origen Gemini.
        # Para partes digitales (Vía A/B/C confirm) raw_gemini_response es None —
        # en ese caso el restore re-resuelve machine_asset desde maquina_norm almacenado
        # y recalcula delta_horas desde hc/hf almacenados, preservando el resto.
        raw = entry.raw_gemini_response

        if not raw or not isinstance(raw, dict):
            # Digital work order path — re-resolve asset and recompute hours only.
            # Ruta de parte digital — re-resolver activo y recalcular horas únicamente.
            maquina_norm  = _normalise_machine_code(line.maquina_raw or "")
            machine_asset = _resolve_machine_asset(maquina_norm, company=company) if maquina_norm else None
            delta         = _compute_delta_horas(line.hc, line.hf)

            line.maquina_norm  = maquina_norm
            line.machine_asset = machine_asset
            line.delta_horas   = delta
            line.save(update_fields=["maquina_norm", "machine_asset", "delta_horas"])

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
        maquina_raw   = (bloque.get("maquina_raw") or "").strip()
        maquina_norm  = _normalise_machine_code(maquina_raw)
        machine_asset = _resolve_machine_asset(maquina_norm, company=company)
        hc            = _parse_time(bloque.get("hc"))
        hf            = _parse_time(bloque.get("hf"))
        delta         = _compute_delta_horas(hc, hf)
        flags         = bloque.get("flags") or []
        if not isinstance(flags, list):
            flags = []

        line.maquina_raw        = maquina_raw
        line.maquina_norm       = maquina_norm
        line.machine_asset      = machine_asset
        line.descripcion_averia = (bloque.get("descripcion_averia") or "")
        line.reparacion         = (bloque.get("reparacion") or "")
        line.hc                 = hc
        line.hf                 = hf
        line.or_val             = (bloque.get("or_val") or "")
        line.delta_horas        = delta
        line.flags              = flags
        line.save(update_fields=[
            "maquina_raw", "maquina_norm", "machine_asset",
            "descripcion_averia", "reparacion", "hc", "hf",
            "or_val", "delta_horas", "flags",
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
                    line.machine_asset.codigo if line.machine_asset else ""
                )
                hc_display    = (
                    line.hc.strftime("%H:%M") if line.hc else ""
                )
                hf_display    = (
                    line.hf.strftime("%H:%M") if line.hf else ""
                )
                delta_display = (
                    str(line.delta_horas) if line.delta_horas is not None else ""
                )
                flags_display = ", ".join(line.flags) if line.flags else ""

                row_values = [
                    worker_name,
                    date_display,
                    line.line_number,
                    line.maquina_norm,
                    line.maquina_raw,
                    asset_code,
                    line.descripcion_averia,
                    line.reparacion,
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
                "codigo":      str,
                "marca_modelo": str,
                "delta_horas": float | null,
                "weekday":     int | null   // 0=Mon … 4=Fri
            },
            ...
        ],
        "work_orders": [
            {"id": int, "label": str},
            ...
        ],
        "assets": [
            {"codigo": str, "marca_modelo": str},
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
                "codigo":       str,
                "marca_modelo": str,
                "delta_horas":  float | null,
                "weekday":      int | null   // 0=Lun … 4=Vie
            },
            ...
        ],
        "work_orders": [
            {"id": int, "label": str},
            ...
        ],
        "assets": [
            {"codigo": str, "marca_modelo": str},
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
            .order_by("entry__work_date", "machine_asset__codigo")
        )

        lines = []
        for line in qs:
            work_date  = line.entry.work_date
            delta      = float(line.delta_horas) if line.delta_horas is not None else None
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
                "codigo":      line.machine_asset.codigo,
                "marca_modelo": line.machine_asset.marca_modelo,
                "delta_horas": delta,
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
            c = line["codigo"]
            if c not in seen_assets:
                seen_assets[c] = line["marca_modelo"]
        assets = [
            {"codigo": c, "marca_modelo": m}
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
    'q' GET parameter (matches against codigo and marca_modelo).
    Used by the operator work-order entry form (Hito 7 / Paso 5).

    GET /panel/operator/assets/?q=<query>
        Returns a JSON array of {codigo, marca_modelo} objects, max 20 results.
        If 'q' is absent or blank, returns the first 20 active assets ordered
        by codigo.
    ---
    Endpoint JSON que devuelve registros MachineAsset de la empresa del
    CompanyUser autenticado. Admite búsqueda incremental mediante el parámetro
    GET opcional 'q' (busca en codigo y marca_modelo).
    Usado por el formulario de entrada de partes del operario (Hito 7 / Paso 5).

    GET /panel/operator/assets/?q=<query>
        Devuelve un array JSON de objetos {codigo, marca_modelo}, máx. 20 resultados.
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
        qs = MachineAsset.objects.filter(company=company, es_activo=True)

        if q:
            # Case-insensitive search on codigo and marca_modelo.
            # Búsqueda sin distinción de mayúsculas en codigo y marca_modelo.
            qs = qs.filter(
                django_models.Q(codigo__icontains=q) |
                django_models.Q(marca_modelo__icontains=q)
            )

        assets = list(
            qs.order_by("codigo")
            .values("codigo", "marca_modelo")[:20]
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
      Pass 1 — direct iexact on maquina_raw: covers autocomplete selections
               where the field contains the exact asset.codigo string.
      Pass 2 — iexact on _normalise_machine_code(maquina_raw): covers OCR
               and handwritten input where normalisation is required.

    Returns a list of dicts ready to feed the integrity gate and the
    atomic persistence block.
    ---
    Parsea y resuelve las líneas de entrada de bloque de trabajo enviadas
    por POST.

    Estrategia de resolución para machine_asset (dos pasadas):
      Pasada 1 — iexact directo sobre maquina_raw: cubre selecciones del
                 autocompletado donde el campo contiene el asset.codigo exacto.
      Pasada 2 — iexact sobre _normalise_machine_code(maquina_raw): cubre
                 entrada OCR y manuscrita donde se requiere normalización.

    Devuelve una lista de dicts lista para la barrera de integridad y el
    bloque de persistencia atómica.
    """
    import json as _json
    from datetime import time as _dt_time
    from fleet.models import MachineAsset
    from work_order_processor.services import (
        _normalise_machine_code,
        _compute_delta_horas,
    )

    num_entradas     = int(POST.get("num_entradas", "1") or "1")
    entry_lines_data = []

    for i in range(1, num_entradas + 1):
        pfx         = f"entrada_{i}_"
        maquina_raw = POST.get(f"{pfx}maquina_raw", "").strip()
        desc_averia = POST.get(f"{pfx}descripcion_averia", "").strip()
        reparacion  = POST.get(f"{pfx}reparacion", "").strip()
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

        maquina_norm  = _normalise_machine_code(maquina_raw)
        machine_asset = None

        if maquina_raw:
            # Pass 1 — direct iexact on raw (autocomplete writes exact codigo).
            # Pasada 1 — iexact directo sobre raw (autocompletado escribe codigo exacto).
            try:
                machine_asset = MachineAsset.objects.get(
                    codigo__iexact=maquina_raw, company=company
                )
            except (MachineAsset.DoesNotExist, MachineAsset.MultipleObjectsReturned):
                machine_asset = MachineAsset.objects.filter(
                    codigo__iexact=maquina_raw, company=company
                ).first()

        if machine_asset is None and maquina_norm:
            # Pass 2 — normalised code (OCR / handwritten input).
            # Pasada 2 — código normalizado (entrada OCR / manuscrita).
            try:
                machine_asset = MachineAsset.objects.get(
                    codigo__iexact=maquina_norm, company=company
                )
            except (MachineAsset.DoesNotExist, MachineAsset.MultipleObjectsReturned):
                machine_asset = MachineAsset.objects.filter(
                    codigo__iexact=maquina_norm, company=company
                ).first()

        delta_horas = _compute_delta_horas(hc, hf)

        try:
            flags = _json.loads(flags_raw) if flags_raw else []
        except (ValueError, TypeError):
            flags = []

        entry_lines_data.append({
            "line_number":        i,
            "maquina_raw":        maquina_raw,
            "maquina_norm":       maquina_norm or "",
            "machine_asset":      machine_asset,
            "descripcion_averia": desc_averia,
            "reparacion":         reparacion,
            "hc":                 hc,
            "hf":                 hf,
            "or_val":             or_val,
            "delta_horas":        delta_horas,
            "flags":              flags,
        })

    return entry_lines_data


def _parse_spare_parts_from_post(POST, company):
    """
    Parses and resolves spare-part lines submitted via POST.

    Applies the same two-pass resolution strategy as _parse_entry_lines_from_post
    for the vehicle asset field (vehiculo_raw).

    Returns a list of dicts ready to feed the integrity gate and the
    atomic persistence block.
    ---
    Parsea y resuelve las líneas de repuesto enviadas por POST.

    Aplica la misma estrategia de resolución en dos pasadas que
    _parse_entry_lines_from_post para el campo de activo de vehículo (vehiculo_raw).

    Devuelve una lista de dicts lista para la barrera de integridad y el
    bloque de persistencia atómica.
    """
    from decimal import Decimal, InvalidOperation
    from fleet.models import MachineAsset
    from work_order_processor.services import _normalise_machine_code

    num_repuestos    = int(POST.get("num_repuestos", "0") or "0")
    spare_parts_data = []

    for r in range(1, num_repuestos + 1):
        pfx          = f"repuesto_{r}_"
        referencia   = POST.get(f"{pfx}referencia", "").strip()
        vehiculo_raw = POST.get(f"{pfx}vehiculo_raw", "").strip()
        material     = POST.get(f"{pfx}material", "").strip()
        unidades_str = POST.get(f"{pfx}unidades", "").strip()
        origen       = POST.get(f"{pfx}origen", "WAREHOUSE").strip()
        proveedor    = POST.get(f"{pfx}proveedor", "").strip()
        entry_idx    = int(POST.get(f"{pfx}entry_idx", "1") or "1")

        quantity = None
        if unidades_str:
            try:
                quantity = Decimal(unidades_str.replace(",", "."))
            except InvalidOperation:
                quantity = None

        if origen not in ("SUPPLIER", "WAREHOUSE"):
            origen = "WAREHOUSE"

        veh_norm  = _normalise_machine_code(vehiculo_raw)
        veh_asset = None

        if vehiculo_raw:
            # Pass 1 — direct iexact on raw.
            # Pasada 1 — iexact directo sobre raw.
            try:
                veh_asset = MachineAsset.objects.get(
                    codigo__iexact=vehiculo_raw, company=company
                )
            except (MachineAsset.DoesNotExist, MachineAsset.MultipleObjectsReturned):
                veh_asset = MachineAsset.objects.filter(
                    codigo__iexact=vehiculo_raw, company=company
                ).first()

        if veh_asset is None and veh_norm:
            # Pass 2 — normalised code.
            # Pasada 2 — código normalizado.
            try:
                veh_asset = MachineAsset.objects.get(
                    codigo__iexact=veh_norm, company=company
                )
            except (MachineAsset.DoesNotExist, MachineAsset.MultipleObjectsReturned):
                veh_asset = MachineAsset.objects.filter(
                    codigo__iexact=veh_norm, company=company
                ).first()

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
            "entry_idx":     entry_idx,
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
            return MachineAsset.objects.get(codigo__iexact=norm, company=company)
        except MachineAsset.DoesNotExist:
            return None
        except MachineAsset.MultipleObjectsReturned:
            return MachineAsset.objects.filter(
                codigo__iexact=norm, company=company
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
            raw_code     = entrada.get("maquina_raw") or ""
            machine_asset = self._resolve_machine(company, raw_code)
            entradas_enriched.append({
                "idx":            idx,
                "maquina_raw":    raw_code,
                "machine_asset":  machine_asset,
                "descripcion_averia": entrada.get("descripcion_averia") or "",
                "reparacion":     entrada.get("reparacion") or "",
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
            MachineAsset.objects.filter(company=company, es_activo=True)
            .order_by("codigo")
            .values("codigo", "marca_modelo")
        )

        context = self._get_context_base(request)
        context.update({
            "extraction":          extraction,
            "fecha":               extraction.get("fecha") or "",
            "fecha_incierta":      extraction.get("fecha_incierta", False),
            "confidence":          extraction.get("extraction_confidence", ""),
            "entradas_enriched":   entradas_enriched,
            "repuestos_enriched":  repuestos_enriched,
            "assets":              assets,
            "num_entradas":        len(entradas_enriched),
            "num_repuestos":       len(repuestos_enriched),
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
            _compute_delta_horas,
        )

        cu      = self._get_company_user(request)
        company = cu.company
        POST    = request.POST

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
        spare_parts_data = _parse_spare_parts_from_post(POST, company)


        # ------------------------------------------------------------------
        # Integrity validation (sine qua non gate).
        # Validación de integridad (barrera sine qua non).
        #
        # Every submitted work order must be 100 % complete before it can
        # be persisted. The following checks are performed in order:
        #   1. Work date must be present and parseable.
        #   2. Every work block must have: a non-empty raw machine code that
        #      resolves to a known MachineAsset, both H.C. and H.F. present
        #      and yielding a positive delta_horas, and a non-empty fault
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
        #      generando un delta_horas positivo, y descripción de avería no vacía.
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
            if not ld["maquina_raw"]:
                integrity_errors.append(
                    f"{blk}: el código de máquina es obligatorio."
                )
            elif ld["machine_asset"] is None:
                integrity_errors.append(
                    f"{blk}: el código '{ld['maquina_raw']}' no se ha podido "
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
            if ld["hc"] and ld["hf"] and ld["delta_horas"] is not None:
                if ld["delta_horas"] <= 0:
                    integrity_errors.append(
                        f"{blk}: la H.F. debe ser posterior a la H.C. "
                        f"(Δ horas calculado: {ld['delta_horas']})."
                    )
            if not ld["descripcion_averia"]:
                integrity_errors.append(
                    f"{blk}: la descripción de la avería es obligatoria."
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
                    "maquina_raw":       ld["maquina_raw"],
                    "machine_asset":     ld["machine_asset"],
                    "descripcion_averia": ld["descripcion_averia"],
                    "reparacion":        ld["reparacion"],
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
                "fecha_incierta":      False,
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
                    fecha_incierta      = False,
                    extraction_confidence = WorkOrderEntry.Confidence.HIGH,
                    raw_gemini_response = None,
                )

                # WorkOrderEntryLine records / Registros WorkOrderEntryLine.
                created_lines = {}
                for ld in entry_lines_data:
                    line = WorkOrderEntryLine.objects.create(
                        entry             = entry,
                        line_number       = ld["line_number"],
                        machine_asset     = ld["machine_asset"],
                        maquina_raw       = ld["maquina_raw"],
                        maquina_norm      = ld["maquina_norm"],
                        descripcion_averia = ld["descripcion_averia"],
                        reparacion        = ld["reparacion"],
                        hc                = ld["hc"],
                        hf                = ld["hf"],
                        or_val            = ld["or_val"],
                        delta_horas       = ld["delta_horas"],
                        flags             = ld["flags"],
                    )
                    created_lines[ld["line_number"]] = line

                # SparePartLine records linked to their entry line.
                # Registros SparePartLine vinculados a su línea de entrada.
                for spd in spare_parts_data:
                    target_line = created_lines.get(spd["entry_idx"])
                    if target_line is None:
                        # Fallback: link to first line if index is invalid.
                        # Fallback: vincular a la primera línea si el índice no es válido.
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

            logger.info(
                "# [Confirm] WorkOrder #%d creado correctamente. "
                "Entradas: %d | Repuestos: %d.",
                work_order.pk,
                len(entry_lines_data),
                len(spare_parts_data),
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

        # Clear session extraction data / Limpiar datos de extracción de sesión.
        request.session.pop("operator_upload_extraction", None)
        request.session.modified = True

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
            MachineAsset.objects.filter(company=company, es_activo=True)
            .order_by("codigo")
            .values("codigo", "marca_modelo")
        )
        return {
            "company":      company,
            "company_user": cu,
            "active_nav":   "operator_dashboard",
            "assets":       assets,
        }

    def get(self, request, *args, **kwargs):
        """
        Renders the empty structured form with one default work block.
        ---
        Renderiza el formulario vacio con un bloque de trabajo por defecto.
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
            _compute_delta_horas,
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
        spare_parts_data = _parse_spare_parts_from_post(POST, company)

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
            if not ld["maquina_raw"]:
                integrity_errors.append(f"{blk}: el codigo de maquina es obligatorio.")
            elif ld["machine_asset"] is None:
                integrity_errors.append(
                    f"{blk}: el codigo '{ld['maquina_raw']}' no se ha podido "
                    f"identificar en el catalogo de flota. Corrigelo antes de guardar."
                )
            if not ld["hc"]:
                integrity_errors.append(f"{blk}: la hora de inicio (H.C.) es obligatoria.")
            if not ld["hf"]:
                integrity_errors.append(f"{blk}: la hora de fin (H.F.) es obligatoria.")
            if ld["hc"] and ld["hf"] and ld["delta_horas"] is not None:
                if ld["delta_horas"] <= 0:
                    integrity_errors.append(
                        f"{blk}: la H.F. debe ser posterior a la H.C. "
                        f"(Delta horas calculado: {ld['delta_horas']})."
                    )
            if not ld["descripcion_averia"]:
                integrity_errors.append(
                    f"{blk}: la descripcion de la averia es obligatoria."
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
                    "maquina_raw":       ld["maquina_raw"],
                    "machine_asset":     ld["machine_asset"],
                    "descripcion_averia": ld["descripcion_averia"],
                    "reparacion":        ld["reparacion"],
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
        # Atomic persistence / Persistencia atomica.
        # ------------------------------------------------------------------
        try:
            with transaction.atomic():
                worker_name = (
                    cu.user.get_full_name() or cu.user.username
                ).upper()

                work_order = WorkOrder(
                    company         = company,
                    uploaded_by     = cu,
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
                    fecha_incierta        = False,
                    extraction_confidence = WorkOrderEntry.Confidence.HIGH,
                    raw_gemini_response   = None,
                )

                created_lines = {}
                for ld in entry_lines_data:
                    line = WorkOrderEntryLine.objects.create(
                        entry              = entry,
                        line_number        = ld["line_number"],
                        machine_asset      = ld["machine_asset"],
                        maquina_raw        = ld["maquina_raw"],
                        maquina_norm       = ld["maquina_norm"],
                        descripcion_averia = ld["descripcion_averia"],
                        reparacion         = ld["reparacion"],
                        hc                 = ld["hc"],
                        hf                 = ld["hf"],
                        or_val             = ld["or_val"],
                        delta_horas        = ld["delta_horas"],
                        flags              = ld["flags"],
                    )
                    created_lines[ld["line_number"]] = line

                for spd in spare_parts_data:
                    target_line = created_lines.get(spd["entry_idx"])
                    if target_line is None:
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

            logger.info(
                "# [FormView] WorkOrder #%d creado correctamente (Via A). "
                "Bloques: %d | Repuestos: %d.",
                work_order.pk,
                len(entry_lines_data),
                len(spare_parts_data),
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

        django_messages.success(
            request,
            f"Parte de trabajo registrado correctamente (#{work_order.pk}). "
            f"El informe Excel esta disponible en la lista de partes."
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
            MachineAsset.objects.filter(company=company, es_activo=True)
            .order_by("codigo")
            .values("codigo", "marca_modelo")
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
             "maquina_raw":        "<code>" | "",
             "hc":                 "HH:MM" | "",
             "hf":                 "HH:MM" | "",
             "descripcion_averia": "<text>" | "",
             "reparacion":         "<text>" | "",
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
- maquina_raw: código alfanumérico de la máquina. Puede aparecer como "A-44",
  "A44", "vehículo A 44", "maquina JD5090R", etc. Devuelve solo el código,
  sin la keyword. Si el reconocedor de voz separa letras y números con espacio
  (ej: "a 44"), reconstruye el código sin espacio ("A44").
- hc: hora de inicio en formato HH:MM. Acepta "de 8 a 14", "hora de inicio 8",
  "desde las ocho", "8:00", etc. Si no puedes determinarla, devuelve cadena vacía.
- hf: hora de fin en formato HH:MM. Mismas variantes que hc.
- descripcion_averia: descripción de la avería o tarea. Texto limpio en español,
  sin keywords ni relleno (elimina frases como "descripción de la avería",
  "parte de reparaciones", "orden de reparación", "ahora", etc.).
- reparacion: descripción de la reparación realizada. Texto limpio. Si no se
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
5. maquina_raw siempre en MAYÚSCULAS.

Formato de respuesta exacto:
{
  "fecha": "",
  "maquina_raw": "",
  "hc": "",
  "hf": "",
  "descripcion_averia": "",
  "reparacion": "",
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
                 "maquina_raw":        "<codigo>" | "",
                 "hc":                 "HH:MM" | "",
                 "hf":                 "HH:MM" | "",
                 "descripcion_averia": "<texto>" | "",
                 "reparacion":         "<texto>" | "",
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
            "fecha": "", "maquina_raw": "", "hc": "", "hf": "",
            "descripcion_averia": "", "reparacion": "", "or_val": "",
        }

        # JSON schema for structured output — guarantees field presence and types.
        # Esquema JSON para salida estructurada — garantiza presencia y tipo de campos.
        _RESPONSE_SCHEMA = {
            "type": "object",
            "properties": {
                "fecha":              {"type": "string"},
                "maquina_raw":        {"type": "string"},
                "hc":                 {"type": "string"},
                "hf":                 {"type": "string"},
                "descripcion_averia": {"type": "string"},
                "reparacion":         {"type": "string"},
                "or_val":             {"type": "string"},
            },
            "required": [
                "fecha", "maquina_raw", "hc", "hf",
                "descripcion_averia", "reparacion", "or_val",
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
                result["maquina_raw"], result["fecha"],
                result["hc"], result["hf"],
            )
            return JsonResponse(result)

        except Exception as exc:
            logger.error(
                "# [STTExtract] Error en extracción Gemini texto: %s", exc, exc_info=True
            )
            return JsonResponse(_EMPTY)


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
