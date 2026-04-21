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

from panel.mixins import CompanyUserRequiredMixin, AdminRoleRequiredMixin
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
)
from whatsapp.models import WhatsAppTemplate, WhatsAppSession


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
        ---
        Restringe el queryset de contactos a la empresa del usuario autenticado.
        Restringe el queryset de call_flow a los CallFlows activos de la empresa
        (Estrategia B — Paso 37.C). call_flow es opcional.
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
        ---
        Guarda la Section y todas las entradas SectionSchedule válidas.
        """
        from django.contrib import messages as django_messages
        form.instance.company = self.request.user.company_user.company
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
        ---
        Restringe el queryset de contactos a la empresa del usuario autenticado.
        Restringe el queryset de call_flow a los CallFlows activos de la empresa
        (Estrategia B — Paso 37.C). call_flow es opcional.
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
        ---
        Guarda la Section y todas las entradas SectionSchedule válidas.
        Gestiona la eliminación de las franjas horarias eliminadas.
        """
        from django.contrib import messages as django_messages
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
        context["action"] = "Editar"
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
        ---
        Guarda un snapshot de backup de los valores actuales antes de aplicar los nuevos.
        Los campos backup almacenan el estado ANTERIOR a este guardado para que el ADMIN
        pueda restaurar.
        """
        instance = self.get_object()
        # Snapshot current (pre-save) values into backup fields.
        # Capturar valores actuales (pre-guardado) en los campos de backup.
        form.instance.backup_system_instruction  = instance.system_instruction
        form.instance.backup_initial_greeting    = instance.initial_greeting
        form.instance.backup_notification_contact = instance.notification_contact
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
        context["action"] = "Editar"
        # has_backup is True if a restorable snapshot exists in backup fields.
        # has_backup es True si existe un snapshot restaurable en los campos de backup.
        obj = self.get_object()
        context["has_backup"] = bool(
            obj.backup_system_instruction or obj.backup_initial_greeting
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
            "company": company,
            "company_user": company_user,
            "own_presence": own_presence,
            "profile": profile,
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

        if not flow.backup_system_instruction and not flow.backup_initial_greeting:
            django_messages.warning(
                request,
                "No existe versión anterior para restaurar en este flujo IVR."
            )
            return redirect(f"/panel/callflows/{pk}/edit/")

        # Swap active ↔ backup so both directions remain available.
        # Intercambiar activo ↔ backup para que ambas direcciones permanezcan disponibles.
        (
            flow.system_instruction,      flow.backup_system_instruction,
        ) = (
            flow.backup_system_instruction, flow.system_instruction,
        )
        (
            flow.initial_greeting,        flow.backup_initial_greeting,
        ) = (
            flow.backup_initial_greeting,  flow.initial_greeting,
        )
        (
            flow.notification_contact,        flow.backup_notification_contact,
        ) = (
            flow.backup_notification_contact, flow.notification_contact,
        )
        flow.save(update_fields=[
            "system_instruction",
            "backup_system_instruction",
            "initial_greeting",
            "backup_initial_greeting",
            "notification_contact",
            "backup_notification_contact",
        ])
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
            "company": company_user.company,
            "company_user": company_user,
            "own_presence": active_presence,
            "form": form,
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
            "company": company_user.company,
            "company_user": company_user,
            "own_presence": active_presence,
            "form": form,
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
