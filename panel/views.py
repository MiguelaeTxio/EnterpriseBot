# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views.py
"""
View definitions for the panel application.
Implements class-based views for authentication and the main dashboard.
---
Definiciones de vistas para la aplicación panel.
Implementa vistas basadas en clases para autenticación y el panel principal.
"""

from django.contrib.auth.views import LoginView, LogoutView
from django.views.generic import TemplateView, View, ListView, UpdateView, CreateView
from django.shortcuts import redirect
from django.db.models import Q
from django.utils.timezone import now

from panel.mixins import CompanyUserRequiredMixin, AdminRoleRequiredMixin
from panel.forms import PanelAuthenticationForm, PresenceStatusForm, SectionForm, ContactForm, CallFlowForm, CorporateVoiceProfileForm
from ivr_config.models import Section, Contact, PresenceStatus, CompanyUser, CallFlow, PhoneNumber, CorporateVoiceProfile


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

    def get_success_url(self):
        """
        Redirects to the user list after a successful update.
        ---
        Redirige a la lista de usuarios tras una actualización correcta.
        """
        from django.contrib import messages as django_messages
        django_messages.success(
            self.request,
            f"Usuario {self.object.user.username} actualizado correctamente."
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
    ---
    Permite a un ADMIN crear una nueva Section para su empresa.
    Asigna automáticamente la empresa desde el CompanyUser del usuario autenticado.
    """

    model = Section
    form_class = SectionForm
    template_name = "panel/sections/form.html"

    def get_form(self, form_class=None):
        """
        Restricts the contacts queryset in the form to the authenticated user's company.
        ---
        Restringe el queryset de contactos del formulario a la empresa del usuario autenticado.
        """
        form = super().get_form(form_class)
        form.fields["contacts"].queryset = Contact.objects.filter(
            company=self.request.user.company_user.company
        )
        return form

    def form_valid(self, form):
        """
        Assigns the company before saving the new Section.
        ---
        Asigna la empresa antes de guardar la nueva Section.
        """
        form.instance.company = self.request.user.company_user.company
        return super().form_valid(form)

    def get_success_url(self):
        """
        Redirects to the section list after a successful creation.
        ---
        Redirige a la lista de secciones tras una creación correcta.
        """
        from django.contrib import messages as django_messages
        django_messages.success(
            self.request,
            f"Sección '{self.object.name}' creada correctamente."
        )
        return "/panel/sections/"

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


class SectionUpdateView(AdminRoleRequiredMixin, UpdateView):
    """
    Allows an ADMIN to update an existing Section belonging to their company.
    Prevents editing sections from other companies.
    ---
    Permite a un ADMIN actualizar una Section existente de su empresa.
    Impide editar secciones de otras empresas.
    """

    model = Section
    form_class = SectionForm
    template_name = "panel/sections/form.html"

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
        Restricts the contacts queryset in the form to the authenticated user's company.
        ---
        Restringe el queryset de contactos del formulario a la empresa del usuario autenticado.
        """
        form = super().get_form(form_class)
        form.fields["contacts"].queryset = Contact.objects.filter(
            company=self.request.user.company_user.company
        )
        return form

    def get_success_url(self):
        """
        Redirects to the section list after a successful update.
        ---
        Redirige a la lista de secciones tras una actualización correcta.
        """
        from django.contrib import messages as django_messages
        django_messages.success(
            self.request,
            f"Sección '{self.object.name}' actualizada correctamente."
        )
        return "/panel/sections/"

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
    ---
    Permite a un ADMIN crear un nuevo CallFlow para su empresa.
    Asigna automáticamente la empresa desde el CompanyUser del usuario autenticado.
    """

    model = CallFlow
    form_class = CallFlowForm
    template_name = "panel/callflows/form.html"

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
    ---
    Permite a un ADMIN actualizar un CallFlow existente de su empresa.
    Impide editar flujos IVR de otras empresas.
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

    def get_success_url(self):
        """
        Redirects to the callflow list after a successful update.
        ---
        Redirige a la lista de flujos IVR tras una actualización correcta.
        """
        from django.contrib import messages as django_messages
        django_messages.success(
            self.request,
            f"Flujo IVR '{self.object.name}' actualizado correctamente."
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
            form.save()
            django_messages.success(
                request,
                "Perfil de voz corporativa actualizado correctamente."
            )
            return redirect("panel:voiceprofile_detail")

        ctx["form"] = form
        return render(request, self.template_name, ctx)


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
    ---
    Vista de logout para la aplicación panel.
    Redirige a la página de login del panel tras la terminación de sesión.
    """

    next_page = "/panel/login/"


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
