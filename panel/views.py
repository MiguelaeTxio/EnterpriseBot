# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views.py
"""
View definitions for the panel application.
Implements class-based views for authentication and the main dashboard.
---
Definiciones de vistas para la aplicación panel.
Implementa vistas basadas en clases para autenticación y el panel principal.
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

from panel.mixins import CompanyUserRequiredMixin, AdminRoleRequiredMixin, WorkshopRequiredMixin
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
import plotly.graph_objects as go
import plotly.io as pio


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

    def _get_context(self, request, form=None):
        """
        Builds template context including is_forced flag for UI messaging.
        ---
        Construye el contexto de plantilla incluyendo el flag is_forced para la UI.
        """
        cu = request.user.company_user
        return {
            "company":      cu.company,
            "company_user": cu,
            "own_presence": self._get_own_presence(cu),
            "active_nav":   "",
            "form":         form or PanelPasswordChangeForm(user=request.user),
            "is_forced":    cu.must_change_password,
        }

    def get(self, request, *args, **kwargs):
        """
        Renders the password change form.
        ---
        Renderiza el formulario de cambio de contraseña.
        """
        return render(request, self.template_name, self._get_context(request))

    def post(self, request, *args, **kwargs):
        """
        Validates and saves the new password. On success clears must_change_password,
        updates session auth hash and redirects to the dashboard.
        ---
        Valida y guarda la nueva contraseña. En caso de éxito limpia must_change_password,
        actualiza el hash de sesión y redirige al dashboard.
        """
        form = PanelPasswordChangeForm(user=request.user, data=request.POST)
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


class WorkOrderListView(AdminRoleRequiredMixin, View):
    """
    Lists all WorkOrder records belonging to the authenticated user's company.
    Shows upload date, status, page progress and Excel download link when done.
    Restricted to ADMIN role.
    ---
    Lista todos los registros WorkOrder de la empresa del usuario autenticado.
    Muestra fecha de carga, estado, progreso de páginas y enlace de descarga
    del Excel cuando el estado es DONE. Restringido al rol ADMIN.
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
        Renders the work order list filtered by the authenticated user's company.
        ---
        Renderiza la lista de partes de trabajo filtrada por la empresa del
        usuario autenticado.
        """
        company_user = request.user.company_user
        work_orders  = WorkOrder.objects.filter(
            company=company_user.company
        ).order_by("-upload_date")

        return render(request, self.template_name, {
            "company":      company_user.company,
            "company_user": company_user,
            "own_presence":  self._get_own_presence(company_user),
            "active_nav":    "work_orders",
            "work_orders":   work_orders,
        })


class WorkOrderUploadView(AdminRoleRequiredMixin, View):
    """
    Handles PDF upload for work order processing.
    On POST: creates a WorkOrder record, enqueues the Celery processing task
    immediately via process_work_order_pdf.delay() and redirects to the list.
    Restricted to ADMIN role.
    ---
    Gestiona la carga de PDF para el procesamiento de partes de trabajo.
    En POST: crea un registro WorkOrder, encola inmediatamente la tarea Celery
    de procesamiento mediante process_work_order_pdf.delay() y redirige a la lista.
    Restringido al rol ADMIN.
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
        Processes the uploaded PDF: validates presence of the file, creates
        a WorkOrder and enqueues the Celery task for immediate processing.
        On validation error, re-renders the form with an error message.
        ---
        Procesa el PDF cargado: valida la presencia del archivo, crea un
        WorkOrder y encola la tarea Celery para procesamiento inmediato.
        En caso de error de validación, vuelve a renderizar el formulario
        con un mensaje de error.
        """
        from django.contrib import messages as django_messages
        from django.db import transaction

        company_user = request.user.company_user
        pdf_file     = request.FILES.get("source_pdf")

        if not pdf_file:
            django_messages.error(request, "Debes seleccionar un archivo PDF.")
            return render(request, self.template_name, {
                "company":      company_user.company,
                "company_user": company_user,
                "own_presence":  self._get_own_presence(company_user),
                "active_nav":    "work_orders",
            })

        if not pdf_file.name.lower().endswith(".pdf"):
            django_messages.error(request, "El archivo debe tener extensión .pdf.")
            return render(request, self.template_name, {
                "company":      company_user.company,
                "company_user": company_user,
                "own_presence":  self._get_own_presence(company_user),
                "active_nav":    "work_orders",
            })

        # Create WorkOrder and enqueue Celery task after DB commit.
        # Crear WorkOrder y encolar la tarea Celery tras el commit de BD.
        work_order = WorkOrder.objects.create(
            company     = company_user.company,
            uploaded_by = company_user,
            source_pdf  = pdf_file,
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
            groups.append({
                "entry": entry,
                "lines": list(entry.lines.order_by("line_number")),
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
            asset    = _resolve_machine_asset(norm) if norm else None

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
