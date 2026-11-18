# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_ivr.py


from django.contrib import messages as django_messages
from django.views.generic import View, ListView, UpdateView, CreateView, DeleteView
from django.shortcuts import redirect, render
from django.db.models import Q
from django.utils.timezone import now

from panel.mixins import AdminRoleRequiredMixin
from panel.forms import (
    SectionForm,
    ContactForm,
    CallFlowForm,
    CorporateVoiceProfileForm,
    BlockedCallerForm,
    DataCaptureSetForm,
)
from ivr_config.models import (
    Section,
    Contact,
    PresenceStatus,
    CompanyUser,
    CallFlow,
    CorporateVoiceProfile,
    BlockedCaller,
    DataCaptureSet,
    InboundCallLog,
)
import logging

logger = logging.getLogger(__name__)

class SectionCreateView(AdminRoleRequiredMixin, CreateView):
    """
    Allows an ADMIN to create a new Section for their company.
    ---
    Permite a un ADMIN crear una nueva Section para su empresa. Desde S155
    lo de la centralita (casillas IVR, conjunto de captura, horario de
    atención) se configura en Telefonía → Secciones en la centralita.
    """

    model = Section
    form_class = SectionForm
    template_name = "panel/sections/form.html"

    def get_form(self, form_class=None):
        """
        Restricts contacts and workday schedules to the user's company.
        ---
        Restringe contactos y horarios de jornada a la empresa del usuario.
        """
        form = super().get_form(form_class)
        company = self.request.user.company_user.company
        form.fields["contacts"].queryset = Contact.objects.filter(
            company=company
        ).exclude(
            company_user__role__in=list(CompanyUser.WORKER_ROLES)
        )
        from ivr_config.models import WorkdaySchedule as _WorkdaySchedule
        form.fields["workday_schedule"].queryset = (
            _WorkdaySchedule.objects.filter(company=company).order_by("label")
        )
        form.fields["workday_schedule"].required = False
        return form

    def form_valid(self, form):
        """
        Assigns the company and saves the Section.
        ---
        Asigna la empresa y guarda la Section.
        """
        form.instance.company = self.request.user.company_user.company
        self.object = form.save()
        django_messages.success(
            self.request,
            f"Sección '{self.object.name}' creada correctamente."
        )
        return redirect("/panel/sections/")

    def get_context_data(self, **kwargs):
        """
        Adds company, company_user, own_presence and the action flag.
        ---
        Añade company, company_user, own_presence y el flag de acción.
        """
        context = super().get_context_data(**kwargs)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = _get_own_presence(self.request)
        context["active_nav"] = "sections"
        context["action"] = "Crear"
        context["section_workers"] = []
        return context


class SectionUpdateView(AdminRoleRequiredMixin, UpdateView):
    """
    Allows an ADMIN to update an existing Section of their company.
    ---
    Permite a un ADMIN editar una Section de su empresa. Desde S155 lo de la
    centralita se configura en Telefonía; aquí solo se muestra su estado con
    un enlace.
    """

    model = Section
    form_class = SectionForm
    template_name = "panel/sections/form.html"

    def get_queryset(self):
        """
        Restricts the queryset to the user's company.
        ---
        Restringe el queryset a la empresa del usuario.
        """
        return Section.objects.filter(
            company=self.request.user.company_user.company
        )

    def get_form(self, form_class=None):
        """
        Restricts contacts and workday schedules to the user's company.
        ---
        Restringe contactos y horarios de jornada a la empresa del usuario.
        """
        form = super().get_form(form_class)
        company = self.request.user.company_user.company
        form.fields["contacts"].queryset = Contact.objects.filter(
            company=company
        ).exclude(
            company_user__role__in=list(CompanyUser.WORKER_ROLES)
        )
        from ivr_config.models import WorkdaySchedule as _WorkdaySchedule
        form.fields["workday_schedule"].queryset = (
            _WorkdaySchedule.objects.filter(company=company).order_by("label")
        )
        form.fields["workday_schedule"].required = False
        return form

    def form_valid(self, form):
        """
        Saves the Section keeping the worker contacts in the M2M.
        ---
        Guarda la Section conservando en el M2M los contactos de trabajadores
        (WORKSHOP/DRIVER), que el selector de contactos no muestra.
        """
        worker_contacts = list(
            self.object.contacts.filter(
                company_user__role__in=list(CompanyUser.WORKER_ROLES)
            ).values_list("pk", flat=True)
        )
        self.object = form.save()
        if worker_contacts:
            self.object.contacts.add(*worker_contacts)
            logger.info(
                "# [SECTION UPDATE] %d contacto(s) WORKSHOP/DRIVER "
                "preservados en M2M de Section pk=%s.",
                len(worker_contacts),
                self.object.pk,
            )
        django_messages.success(
            self.request,
            f"Sección '{self.object.name}' actualizada correctamente."
        )
        return redirect("/panel/sections/")

    def get_context_data(self, **kwargs):
        """
        Adds company context, section workers, workday schedules and the
        phone switchboard status of the section.
        ---
        Añade el contexto de empresa, los trabajadores de la sección, los
        horarios de jornada y el estado de la sección en la centralita.
        """
        from panel.views_ivr_telephony import section_ivr_status
        from ivr_config.models import WorkdaySchedule as _WorkdaySchedule
        context = super().get_context_data(**kwargs)
        company = self.request.user.company_user.company
        context["company"] = company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = _get_own_presence(self.request)
        context["active_nav"] = "sections"
        context["action"] = "Guardar"
        workers = []
        for contact in (
            self.object.contacts.filter(company_user__isnull=False)
            .select_related("company_user__user")
            .order_by("company_user__user__username")
        ):
            cu = contact.company_user
            cu.contact_phone = contact.phone_number or ""
            cu.is_ivr_active = contact.is_internal
            workers.append(cu)
        context["section_workers"] = workers
        context["workday_schedules"] = list(
            _WorkdaySchedule.objects.filter(company=company).order_by("label")
        )
        context["ivr_status"] = section_ivr_status(self.object)
        return context


def _get_own_presence(request):
    """
    Returns the current active PresenceStatus of the authenticated user.
    ---
    Retorna el PresenceStatus activo actual del usuario autenticado.
    """
    return PresenceStatus.objects.filter(
        company_user=request.user.company_user,
        starts_at__lte=now(),
    ).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=now())
    ).order_by("-starts_at").first()


class ContactListView (AdminRoleRequiredMixin ,ListView ):
    """
    Lists all Contact records belonging to the authenticated user's company.
    Accessible only to users with the ADMIN role.
    ---
    Lista todos los registros Contact pertenecientes a la empresa del usuario autenticado.
    Solo accesible para usuarios con rol ADMIN.
    """

    model =Contact 
    template_name ="panel/contacts/list.html"
    context_object_name ="contacts"

    def get_queryset (self ):
        """
        Returns Contact records scoped to the authenticated user's company.
        ---
        Retorna los registros Contact acotados a la empresa del usuario autenticado.
        """
        return Contact .objects .filter (
        company =self .request .user .company_user .company 
        ).select_related ("company_user__user").order_by ("name")

    def get_context_data (self ,**kwargs ):
        """
        Adds company, company_user and own_presence to template context.
        ---
        Añade company, company_user y own_presence al contexto de la plantilla.
        """
        context =super ().get_context_data (**kwargs )
        context ["company"]=self .request .user .company_user .company 
        context ["company_user"]=self .request .user .company_user 
        context ["own_presence"]=self ._get_own_presence ()
        context ["active_nav"]="contacts"
        return context 

    def _get_own_presence (self ):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django .utils .timezone import now 
        from django .db .models import Q 
        company_user =self .request .user .company_user 
        return PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first ()

class ContactCreateView (AdminRoleRequiredMixin ,CreateView ):
    """
    Allows an ADMIN to create a new Contact for their company.
    Automatically assigns the company from the authenticated user's CompanyUser.
    Restricts the company_user field to users belonging to the same company.
    ---
    Permite a un ADMIN crear un nuevo Contact para su empresa.
    Asigna automáticamente la empresa desde el CompanyUser del usuario autenticado.
    Restringe el campo company_user a usuarios de la misma empresa.
    """

    model =Contact 
    form_class =ContactForm 
    template_name ="panel/contacts/form.html"

    def get_form (self ,form_class =None ):
        """
        Restricts the company_user queryset in the form to the authenticated user's company.
        ---
        Restringe el queryset de company_user del formulario a la empresa del usuario autenticado.
        """
        form =super ().get_form (form_class )
        form .fields ["company_user"].queryset =CompanyUser .objects .filter (
        company =self .request .user .company_user .company 
        ).select_related ("user")
        form .fields ["company_user"].required =False 
        return form 

    def form_valid (self ,form ):
        """
        Assigns the company before saving the new Contact.
        ---
        Asigna la empresa antes de guardar el nuevo Contact.
        """
        form .instance .company =self .request .user .company_user .company 
        return super ().form_valid (form )

    def get_success_url (self ):
        """
        Redirects to the contact list after a successful creation.
        ---
        Redirige a la lista de contactos tras una creación correcta.
        """
        from django .contrib import messages as django_messages 
        django_messages .success (
        self .request ,
        f"Contacto '{self.object.name}' creado correctamente."
        )
        return "/panel/contacts/"

    def get_context_data (self ,**kwargs ):
        """
        Adds company, company_user, own_presence and action flag to template context.
        ---
        Añade company, company_user, own_presence y flag de acción al contexto de la plantilla.
        """
        context =super ().get_context_data (**kwargs )
        context ["company"]=self .request .user .company_user .company 
        context ["company_user"]=self .request .user .company_user 
        context ["own_presence"]=self ._get_own_presence ()
        context ["active_nav"]="contacts"
        context ["action"]="Crear"
        context ["section_workers"]=[]
        return context 

    def _get_own_presence (self ):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django .utils .timezone import now 
        from django .db .models import Q 
        company_user =self .request .user .company_user 
        return PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first ()

class ContactUpdateView (AdminRoleRequiredMixin ,UpdateView ):
    """
    Allows an ADMIN to update an existing Contact belonging to their company.
    Prevents editing contacts from other companies.
    Restricts the company_user field to users belonging to the same company.
    ---
    Permite a un ADMIN actualizar un Contact existente de su empresa.
    Impide editar contactos de otras empresas.
    Restringe el campo company_user a usuarios de la misma empresa.
    """

    model =Contact 
    form_class =ContactForm 
    template_name ="panel/contacts/form.html"

    def get_queryset (self ):
        """
        Restricts the queryset to Contact records of the authenticated user's company.
        ---
        Restringe el queryset a los registros Contact de la empresa del usuario autenticado.
        """
        return Contact .objects .filter (
        company =self .request .user .company_user .company 
        )

    def get_form (self ,form_class =None ):
        """
        Restricts the company_user queryset in the form to the authenticated user's company.
        ---
        Restringe el queryset de company_user del formulario a la empresa del usuario autenticado.
        """
        form =super ().get_form (form_class )
        form .fields ["company_user"].queryset =CompanyUser .objects .filter (
        company =self .request .user .company_user .company 
        ).select_related ("user")
        form .fields ["company_user"].required =False 
        return form 

    def get_success_url (self ):
        """
        Redirects to the contact list after a successful update.
        ---
        Redirige a la lista de contactos tras una actualización correcta.
        """
        from django .contrib import messages as django_messages 
        django_messages .success (
        self .request ,
        f"Contacto '{self.object.name}' actualizado correctamente."
        )
        return "/panel/contacts/"

    def get_context_data (self ,**kwargs ):
        """
        Adds company, company_user, own_presence and action flag to template context.
        ---
        Añade company, company_user, own_presence y flag de acción al contexto de la plantilla.
        """
        context =super ().get_context_data (**kwargs )
        context ["company"]=self .request .user .company_user .company 
        context ["company_user"]=self .request .user .company_user 
        context ["own_presence"]=self ._get_own_presence ()
        context ["active_nav"]="contacts"
        context ["action"]="Editar"
        return context 

    def _get_own_presence (self ):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django .utils .timezone import now 
        from django .db .models import Q 
        company_user =self .request .user .company_user 
        return PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first ()

class ContactDeleteView (AdminRoleRequiredMixin ,View ):
    """
    Allows an ADMIN to delete a Contact belonging to their company.
    Scoped to the authenticated user's company — cross-company deletions
    are rejected silently via get_object_or_404.
    Renders a confirmation page on GET; deletes on POST.
    ---
    Permite a un ADMIN eliminar un Contact de su empresa.
    Acotado a la empresa del usuario autenticado — los intentos entre
    empresas son rechazados silenciosamente via get_object_or_404.
    Renderiza una página de confirmación en GET; elimina en POST.
    """

    template_name ="panel/contacts/confirm_delete.html"

    def _get_contact (self ,request ,pk ):
        """
        Returns the Contact scoped to the authenticated user's company
        or raises Http404.
        ---
        Retorna el Contact acotado a la empresa del usuario autenticado
        o lanza Http404.
        """
        from django .shortcuts import get_object_or_404 
        return get_object_or_404 (
        Contact ,
        pk =pk ,
        company =request .user .company_user .company ,
        )

    def _get_own_presence (self ,request ):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        company_user =request .user .company_user 
        return PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first ()

    def get (self ,request ,pk ,*args ,**kwargs ):
        """
        Renders the confirmation page for the given Contact.
        ---
        Renderiza la página de confirmación para el Contact indicado.
        """
        contact =self ._get_contact (request ,pk )
        context ={
        "company":request .user .company_user .company ,
        "company_user":request .user .company_user ,
        "own_presence":self ._get_own_presence (request ),
        "active_nav":"contacts",
        "contact":contact ,
        }
        return render (request ,self .template_name ,context )

    def post (self ,request ,pk ,*args ,**kwargs ):
        """
        Deletes the Contact and redirects to the contact list.
        ---
        Elimina el Contact y redirige a la lista de contactos.
        """
        contact =self ._get_contact (request ,pk )
        name =contact .name 
        contact .delete ()
        logger .info (
        "# [CONTACT DELETE] Contact '%s' eliminado por %s.",
        name ,
        request .user .username ,
        )
        django_messages .success (
        request ,
        f"Contacto '{name}' eliminado correctamente.",
        )
        return redirect ("/panel/contacts/")

class CallFlowCreateView (AdminRoleRequiredMixin ,CreateView ):
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

    model =CallFlow 
    form_class =CallFlowForm 
    template_name ="panel/callflows/form.html"

    def get_form (self ,form_class =None ):
        """
        Restricts notification_contact queryset to the authenticated user's company.
        Restricts fallback_section queryset to the company's own active Sections
        (Estrategia B — Step 37.C). Both fields are optional.
        ---
        Restringe el queryset de notification_contact a la empresa del usuario autenticado.
        Restringe el queryset de fallback_section a las Sections activas de la empresa
        (Estrategia B — Paso 37.C). Ambos campos son opcionales.
        """
        form =super ().get_form (form_class )
        company =self .request .user .company_user .company 


        form .fields ["notification_contact"].queryset =Contact .objects .filter (
        company =company 
        ).exclude (
        company_user__role__in =list (CompanyUser .WORKER_ROLES )
        ).order_by ("name")
        form .fields ["notification_contact"].required =False 
        form .fields ["fallback_section"].queryset =Section .objects .filter (
        company =company ,
        is_active =True ,
        ).order_by ("name")
        form .fields ["fallback_section"].required =False 
        return form 

    def form_valid (self ,form ):
        """
        Assigns the company before saving the new CallFlow.
        ---
        Asigna la empresa antes de guardar el nuevo CallFlow.
        """
        form .instance .company =self .request .user .company_user .company 
        return super ().form_valid (form )

    def get_success_url (self ):
        """
        Redirects to the callflow list after a successful creation.
        ---
        Redirige a la lista de flujos IVR tras una creación correcta.
        """
        from django .contrib import messages as django_messages 
        django_messages .success (
        self .request ,
        f"Flujo IVR '{self.object.name}' creado correctamente."
        )
        return "/panel/callflows/"

    def get_context_data (self ,**kwargs ):
        """
        Adds company, company_user, own_presence and action flag to template context.
        ---
        Añade company, company_user, own_presence y flag de acción al contexto de la plantilla.
        """
        context =super ().get_context_data (**kwargs )
        context ["company"]=self .request .user .company_user .company 
        context ["company_user"]=self .request .user .company_user 
        context ["own_presence"]=self ._get_own_presence ()
        context ["active_nav"]="callflows"
        context ["action"]="Crear"
        context ["section_workers"]=[]
        return context 

    def _get_own_presence (self ):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django .utils .timezone import now 
        from django .db .models import Q 
        company_user =self .request .user .company_user 
        return PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first ()

class CallFlowUpdateView (AdminRoleRequiredMixin ,UpdateView ):
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

    model =CallFlow 
    form_class =CallFlowForm 
    template_name ="panel/callflows/form.html"

    def get_queryset (self ):
        """
        Restricts the queryset to CallFlow records of the authenticated user's company.
        ---
        Restringe el queryset a los registros CallFlow de la empresa del usuario autenticado.
        """
        return CallFlow .objects .filter (
        company =self .request .user .company_user .company 
        )

    def get_form (self ,form_class =None ):
        """
        Restricts notification_contact queryset to the authenticated user's company.
        Restricts fallback_section queryset to the company's own active Sections
        (Estrategia B — Step 37.C). Both fields are optional.
        ---
        Restringe el queryset de notification_contact a la empresa del usuario autenticado.
        Restringe el queryset de fallback_section a las Sections activas de la empresa
        (Estrategia B — Paso 37.C). Ambos campos son opcionales.
        """
        form =super ().get_form (form_class )
        company =self .request .user .company_user .company 


        form .fields ["notification_contact"].queryset =Contact .objects .filter (
        company =company 
        ).exclude (
        company_user__role__in =list (CompanyUser .WORKER_ROLES )
        ).order_by ("name")
        form .fields ["notification_contact"].required =False 
        form .fields ["fallback_section"].queryset =Section .objects .filter (
        company =company ,
        is_active =True ,
        ).order_by ("name")
        form .fields ["fallback_section"].required =False 
        return form 

    def form_valid (self ,form ):
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


        pre_save =CallFlow .objects .filter (pk =form .instance .pk ).values (
        "name",
        "system_instruction",
        "initial_greeting",
        "notification_contact_id",
        ).first ()

        if pre_save :
            form .instance .backup_name =pre_save ["name"]
            form .instance .backup_system_instruction =pre_save ["system_instruction"]
            form .instance .backup_initial_greeting =pre_save ["initial_greeting"]
            form .instance .backup_notification_contact_id =pre_save ["notification_contact_id"]

        return super ().form_valid (form )

    def get_success_url (self ):
        """
        Redirects to the callflow list after a successful update.
        ---
        Redirige a la lista de flujos IVR tras una actualización correcta.
        """
        from django .contrib import messages as django_messages 
        django_messages .success (
        self .request ,
        f"Flujo IVR '{self.object.name}' actualizado correctamente. "
        "Puedes restaurar la versión anterior desde el formulario de edición."
        )
        return "/panel/callflows/"

    def get_context_data (self ,**kwargs ):
        """
        Adds company, company_user, own_presence, action flag and has_backup to context.
        ---
        Añade company, company_user, own_presence, flag de acción y has_backup al contexto.
        """
        context =super ().get_context_data (**kwargs )
        context ["company"]=self .request .user .company_user .company 
        context ["company_user"]=self .request .user .company_user 
        context ["own_presence"]=self ._get_own_presence ()
        context ["active_nav"]="callflows"
        context ["action"]="Editar"


        obj =self .get_object ()
        context ["has_backup"]=bool (
        obj .backup_name 
        or obj .backup_system_instruction 
        or obj .backup_initial_greeting 
        )
        return context 

    def _get_own_presence (self ):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        from django .utils .timezone import now 
        from django .db .models import Q 
        company_user =self .request .user .company_user 
        return PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first ()

class CorporateVoiceProfileUpdateView (AdminRoleRequiredMixin ,View ):
    """
    Allows an ADMIN to view and update the CorporateVoiceProfile of their company.
    If no profile exists yet, it is created on first POST submission.
    Uses View instead of UpdateView to handle the get-or-create pattern cleanly.
    ---
    Permite a un ADMIN ver y actualizar el CorporateVoiceProfile de su empresa.
    Si no existe perfil todavía, se crea en el primer envío POST.
    Usa View en lugar de UpdateView para gestionar el patrón get-or-create limpiamente.
    """

    template_name ="panel/voiceprofile/detail.html"

    def _get_profile_and_context (self ,request ):
        """
        Retrieves or initialises the CorporateVoiceProfile for the company.
        Returns a dict with company, company_user, own_presence and profile.
        ---
        Obtiene o inicializa el CorporateVoiceProfile de la empresa.
        Retorna un dict con company, company_user, own_presence y profile.
        """
        from django .utils .timezone import now 
        from django .db .models import Q 

        company_user =request .user .company_user 
        company =company_user .company 

        profile ,_ =CorporateVoiceProfile .objects .get_or_create (
        company =company ,
        defaults ={
        "tone_guidelines":"",
        "sample_responses":[],
        "forbidden_phrases":[],
        "is_active":True ,
        }
        )

        own_presence =PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first ()

        return {
        "company":company ,
        "company_user":company_user ,
        "own_presence":own_presence ,
        "active_nav":"voiceprofile",
        "profile":profile ,
        }

    def get (self ,request ,*args ,**kwargs ):
        """
        Renders the voice profile form pre-populated with the current profile data.
        ---
        Renderiza el formulario del perfil de voz prerellenado con los datos actuales.
        """
        from django .shortcuts import render 
        ctx =self ._get_profile_and_context (request )
        ctx ["form"]=CorporateVoiceProfileForm (instance =ctx ["profile"])
        return render (request ,self .template_name ,ctx )

    def post (self ,request ,*args ,**kwargs ):
        """
        Updates the CorporateVoiceProfile with the submitted data.
        ---
        Actualiza el CorporateVoiceProfile con los datos enviados.
        """
        from django .shortcuts import render ,redirect 
        from django .contrib import messages as django_messages 

        ctx =self ._get_profile_and_context (request )
        form =CorporateVoiceProfileForm (request .POST ,instance =ctx ["profile"])

        if form .is_valid ():
            profile =ctx ["profile"]


            instance =form .save (commit =False )
            instance .backup_voice_name =profile .voice_name 
            instance .backup_tone_guidelines =profile .tone_guidelines 
            instance .backup_sample_responses =profile .sample_responses 
            instance .backup_forbidden_phrases =profile .forbidden_phrases 
            instance .save ()
            django_messages .success (
            request ,
            "Perfil de voz corporativa actualizado correctamente. "
            "Puedes restaurar la versión anterior desde este mismo formulario."
            )
            return redirect ("panel:voiceprofile_detail")

        ctx ["form"]=form 
        return render (request ,self .template_name ,ctx )

class CallFlowRestoreView (AdminRoleRequiredMixin ,View ):
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

    def post (self ,request ,pk ,*args ,**kwargs ):
        """
        Performs the active ↔ backup field swap and redirects to the edit form.
        ---
        Realiza el intercambio activo ↔ backup y redirige al formulario de edición.
        """
        try :
            flow =CallFlow .objects .get (
            pk =pk ,
            company =request .user .company_user .company 
            )
        except CallFlow .DoesNotExist :
            django_messages .error (request ,"Flujo IVR no encontrado.")
            return redirect ("/panel/callflows/")

        if (
        not flow .backup_name 
        and not flow .backup_system_instruction 
        and not flow .backup_initial_greeting 
        ):
            django_messages .warning (
            request ,
            "No existe versión anterior para restaurar en este flujo IVR."
            )
            return redirect (f"/panel/callflows/{pk}/edit/")







        active_name =flow .name 
        active_system =flow .system_instruction 
        active_greeting =flow .initial_greeting 
        active_notification =flow .notification_contact_id 
        backup_name =flow .backup_name 
        backup_system =flow .backup_system_instruction 
        backup_greeting =flow .backup_initial_greeting 
        backup_notification =flow .backup_notification_contact_id 

        CallFlow .objects .filter (pk =flow .pk ).update (
        name =backup_name or active_name ,
        backup_name =active_name ,
        system_instruction =backup_system ,
        backup_system_instruction =active_system ,
        initial_greeting =backup_greeting ,
        backup_initial_greeting =active_greeting ,
        notification_contact_id =backup_notification ,
        backup_notification_contact_id =active_notification ,
        )
        django_messages .success (
        request ,
        f"Flujo IVR '{flow.name}' restaurado a la versión anterior correctamente."
        )
        return redirect (f"/panel/callflows/{pk}/edit/")

class VoiceProfileRestoreView (AdminRoleRequiredMixin ,View ):
    """
    Restores the CorporateVoiceProfile to its previous backup snapshot with a single POST.
    Swaps active fields ↔ backup fields to allow bidirectional restore.
    Restricted to the profile of the authenticated user's company.
    ---
    Restaura el CorporateVoiceProfile a su snapshot de backup anterior con un solo POST.
    Intercambia los campos activos ↔ backup para permitir restauración bidireccional.
    Restringido al perfil de la empresa del usuario autenticado.
    """

    def post (self ,request ,*args ,**kwargs ):
        """
        Performs the active ↔ backup field swap and redirects to the voice profile form.
        ---
        Realiza el intercambio activo ↔ backup y redirige al formulario del perfil de voz.
        """
        try :
            profile =CorporateVoiceProfile .objects .get (
            company =request .user .company_user .company 
            )
        except CorporateVoiceProfile .DoesNotExist :
            django_messages .error (request ,"Perfil de voz no encontrado.")
            return redirect ("panel:voiceprofile_detail")

        if not profile .backup_tone_guidelines and not profile .backup_voice_name :
            django_messages .warning (
            request ,
            "No existe versión anterior para restaurar en el perfil de voz."
            )
            return redirect ("panel:voiceprofile_detail")



        (
        profile .voice_name ,profile .backup_voice_name ,
        )=(
        profile .backup_voice_name ,profile .voice_name ,
        )
        (
        profile .tone_guidelines ,profile .backup_tone_guidelines ,
        )=(
        profile .backup_tone_guidelines ,profile .tone_guidelines ,
        )
        (
        profile .sample_responses ,profile .backup_sample_responses ,
        )=(
        profile .backup_sample_responses ,profile .sample_responses ,
        )
        (
        profile .forbidden_phrases ,profile .backup_forbidden_phrases ,
        )=(
        profile .backup_forbidden_phrases ,profile .forbidden_phrases ,
        )
        profile .save (update_fields =[
        "voice_name",
        "backup_voice_name",
        "tone_guidelines",
        "backup_tone_guidelines",
        "sample_responses",
        "backup_sample_responses",
        "forbidden_phrases",
        "backup_forbidden_phrases",
        ])
        django_messages .success (
        request ,
        "Perfil de voz restaurado a la versión anterior correctamente."
        )
        return redirect ("panel:voiceprofile_detail")

class BlockedCallerCreateView (AdminRoleRequiredMixin ,CreateView ):
    """
    Allows an ADMIN to manually block a phone number for their company.
    Automatically assigns the company and blocked_by from the authenticated user.
    ---
    Permite a un ADMIN bloquear manualmente un número de teléfono para su empresa.
    Asigna automáticamente la empresa y blocked_by desde el usuario autenticado.
    """

    model =BlockedCaller 
    form_class =BlockedCallerForm 
    template_name ="panel/blockedcallers/form.html"

    def form_valid (self ,form ):
        """
        Assigns company and blocked_by before saving the new BlockedCaller.
        ---
        Asigna company y blocked_by antes de guardar el nuevo BlockedCaller.
        """
        from django .contrib import messages as django_messages 
        form .instance .company =self .request .user .company_user .company 
        form .instance .blocked_by =self .request .user 
        response =super ().form_valid (form )
        django_messages .success (
        self .request ,
        f"Número {self.object.phone_number} bloqueado hasta {self.object.blocked_until:%d/%m/%Y %H:%M}."
        )
        return response 

    def get_success_url (self ):
        """
        Redirects to the blocked callers list after a successful creation.
        ---
        Redirige a la lista de bloqueados tras una creación correcta.
        """
        return "/panel/blockedcallers/"

    def get_context_data (self ,**kwargs ):
        """
        Adds company, company_user, own_presence and action flag to template context.
        ---
        Añade company, company_user, own_presence y flag de acción al contexto de la plantilla.
        """
        context =super ().get_context_data (**kwargs )
        context ["company"]=self .request .user .company_user .company 
        context ["company_user"]=self .request .user .company_user 
        context ["own_presence"]=self ._get_own_presence ()
        context ["active_nav"]="blockedcallers"
        context ["action"]="Bloquear número"
        return context 

    def _get_own_presence (self ):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        company_user =self .request .user .company_user 
        return PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first ()

class BlockedCallerDeleteView (AdminRoleRequiredMixin ,DeleteView ):
    """
    Allows an ADMIN to manually unblock a phone number before its expiry.
    Restricted to BlockedCaller records belonging to the authenticated user's company.
    Uses DELETE method via a confirmation form in the template.
    ---
    Permite a un ADMIN desbloquear manualmente un número antes de su vencimiento.
    Restringido a registros BlockedCaller de la empresa del usuario autenticado.
    Usa el método DELETE mediante un formulario de confirmación en la plantilla.
    """

    model =BlockedCaller 
    template_name ="panel/blockedcallers/confirm_delete.html"

    def get_queryset (self ):
        """
        Restricts deletion to BlockedCaller records of the authenticated user's company.
        ---
        Restringe la eliminación a registros BlockedCaller de la empresa del usuario autenticado.
        """
        return BlockedCaller .objects .filter (
        company =self .request .user .company_user .company 
        )

    def get_success_url (self ):
        """
        Redirects to the blocked callers list after successful deletion.
        ---
        Redirige a la lista de bloqueados tras la eliminación correcta.
        """
        from django .contrib import messages as django_messages 
        django_messages .success (
        self .request ,
        f"Número {self.object.phone_number} desbloqueado correctamente."
        )
        return "/panel/blockedcallers/"

    def get_context_data (self ,**kwargs ):
        """
        Adds company, company_user and own_presence to template context.
        ---
        Añade company, company_user y own_presence al contexto de la plantilla.
        """
        context =super ().get_context_data (**kwargs )
        context ["company"]=self .request .user .company_user .company 
        context ["company_user"]=self .request .user .company_user 
        context ["own_presence"]=self ._get_own_presence ()
        context ["active_nav"]="blockedcallers"
        return context 

    def _get_own_presence (self ):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        company_user =self .request .user .company_user 
        return PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first ()

class DataCaptureSetCreateView (AdminRoleRequiredMixin ,CreateView ):
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

    model =DataCaptureSet 
    form_class =DataCaptureSetForm 
    template_name ="panel/datacapturesets/form.html"

    def form_valid (self ,form ):
        """
        Assigns the company before saving the new DataCaptureSet.
        Deserialises the 'fields_json' hidden input into the model's JSONField.
        ---
        Asigna la empresa antes de guardar el nuevo DataCaptureSet.
        Deserializa el campo oculto 'fields_json' en el JSONField del modelo.
        """
        import json 
        form .instance .company =self .request .user .company_user .company 
        raw_json =self .request .POST .get ("fields_json","[]")
        try :
            form .instance .fields =json .loads (raw_json )
        except (ValueError ,TypeError ):
            form .instance .fields =[]
        return super ().form_valid (form )

    def get_success_url (self ):
        """
        Redirects to the DataCaptureSet list after a successful creation.
        ---
        Redirige a la lista de conjuntos de captura tras una creación correcta.
        """
        django_messages .success (
        self .request ,
        f"Conjunto de captura '{self.object.name}' creado correctamente."
        )
        return "/panel/datacapturesets/"

    def get_context_data (self ,**kwargs ):
        """
        Adds company, company_user, own_presence and action flag to template context.
        Adds existing_fields_json for pre-population on edit (empty list on create).
        ---
        Añade company, company_user, own_presence y flag de acción al contexto de la plantilla.
        Añade existing_fields_json para prerellenar en edición (lista vacía en creación).
        """
        import json 
        context =super ().get_context_data (**kwargs )
        context ["company"]=self .request .user .company_user .company 
        context ["company_user"]=self .request .user .company_user 
        context ["own_presence"]=self ._get_own_presence ()
        context ["active_nav"]="datacapturesets"
        context ["action"]="Crear"
        context ["section_workers"]=[]
        context ["existing_fields_json"]=json .dumps ([])
        return context 

    def _get_own_presence (self ):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        company_user =self .request .user .company_user 
        return PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first ()

class DataCaptureSetUpdateView (AdminRoleRequiredMixin ,UpdateView ):
    """
    Allows an ADMIN to update an existing DataCaptureSet belonging to their company.
    Prevents editing DataCaptureSets from other companies.
    The 'fields' JSONField is updated by the JS dynamic row builder in the template.
    ---
    Permite a un ADMIN actualizar un DataCaptureSet existente de su empresa.
    Impide editar conjuntos de captura de otras empresas.
    El JSONField 'fields' se actualiza por el constructor de filas JS dinámico del template.
    """

    model =DataCaptureSet 
    form_class =DataCaptureSetForm 
    template_name ="panel/datacapturesets/form.html"

    def get_queryset (self ):
        """
        Restricts the queryset to DataCaptureSet records of the authenticated user's company.
        ---
        Restringe el queryset a los registros DataCaptureSet de la empresa del usuario autenticado.
        """
        return DataCaptureSet .objects .filter (
        company =self .request .user .company_user .company 
        )

    def form_valid (self ,form ):
        """
        Deserialises the 'fields_json' hidden input into the model's JSONField before saving.
        ---
        Deserializa el campo oculto 'fields_json' en el JSONField del modelo antes de guardar.
        """
        import json 
        raw_json =self .request .POST .get ("fields_json","[]")
        try :
            form .instance .fields =json .loads (raw_json )
        except (ValueError ,TypeError ):
            form .instance .fields =[]
        return super ().form_valid (form )

    def get_success_url (self ):
        """
        Redirects to the DataCaptureSet list after a successful update.
        ---
        Redirige a la lista de conjuntos de captura tras una actualización correcta.
        """
        django_messages .success (
        self .request ,
        f"Conjunto de captura '{self.object.name}' actualizado correctamente."
        )
        return "/panel/datacapturesets/"

    def get_context_data (self ,**kwargs ):
        """
        Adds company, company_user, own_presence and action flag to template context.
        Serialises the existing fields JSONField for pre-population of the JS row builder.
        ---
        Añade company, company_user, own_presence y flag de acción al contexto de la plantilla.
        Serializa el JSONField fields existente para prerellenar el constructor de filas JS.
        """
        import json 
        context =super ().get_context_data (**kwargs )
        context ["company"]=self .request .user .company_user .company 
        context ["company_user"]=self .request .user .company_user 
        context ["own_presence"]=self ._get_own_presence ()
        context ["active_nav"]="datacapturesets"
        context ["action"]="Guardar"
        # S155: la lista de trabajadores de sección se había copiado aquí
        # filtrando por este conjunto de captura como si fuera una sección
        # (ValueError al editar cualquier conjunto). Esta página no la usa.
        context ["section_workers"]=[]
        context ["existing_fields_json"]=json .dumps (self .object .fields or [])
        return context 

    def _get_own_presence (self ):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        company_user =self .request .user .company_user 
        return PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first ()


class SectionDefaultRoleView (AdminRoleRequiredMixin ,View ):
    """
    AJAX endpoint that returns the default_role of a Section as JSON.
    Used by the user creation form to pre-fill the role selector when
    a section is chosen from the dropdown.
    ---
    Endpoint AJAX que devuelve el default_role de una Section como JSON.
    Usado por el formulario de creación de usuario para pre-rellenar el
    selector de rol cuando se elige una sección del desplegable.
    """

    def get (self ,request ,pk ,*args ,**kwargs ):
        """
        Returns JSON {"default_role": "<ROLE>"} for the requested section pk,
        restricted to the authenticated user's company.
        Returns HTTP 404 if the section does not exist or belongs to another company.
        ---
        Retorna JSON {"default_role": "<ROLE>"} para el pk de sección solicitado,
        restringido a la empresa del usuario autenticado.
        Retorna HTTP 404 si la sección no existe o pertenece a otra empresa.
        """
        from django .http import JsonResponse 
        try :
            section =Section .objects .get (
            pk =pk ,
            company =request .user .company_user .company ,
            )
        except Section .DoesNotExist :
            return JsonResponse ({"error":"Sección no encontrada."},status =404 )
        return JsonResponse ({"default_role":section .default_role })

# ---------------------------------------------------------------------------
# InboundCallLog — Registro de llamadas IVR entrantes (H03)
# ---------------------------------------------------------------------------

class InboundCallLogListView(AdminRoleRequiredMixin, ListView):
    """
    Lists InboundCallLog records for the current company, newest first.
    Allows filtering by call_type and outcome via GET params.
    ---
    Lista registros InboundCallLog de la empresa actual, más recientes primero.
    Permite filtrar por call_type y outcome mediante parámetros GET.
    """
    model = InboundCallLog
    template_name = "panel/ivr/inbound_call_log_list.html"
    context_object_name = "logs"
    paginate_by = 30

    def get_queryset(self):
        qs = (
            InboundCallLog.objects
            .filter(company=self.request.company)
            .select_related("section", "breakdown_ticket")
            .order_by("-started_at")
        )
        call_type = self.request.GET.get("call_type")
        outcome = self.request.GET.get("outcome")
        if call_type:
            qs = qs.filter(call_type=call_type)
        if outcome:
            qs = qs.filter(outcome=outcome)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["type_choices"] = InboundCallLog.TYPE_CHOICES
        ctx["outcome_choices"] = InboundCallLog.OUTCOME_CHOICES
        ctx["selected_type"] = self.request.GET.get("call_type", "")
        ctx["selected_outcome"] = self.request.GET.get("outcome", "")
        return ctx

class InboundCallLogDetailView(AdminRoleRequiredMixin, View):
    """
    Shows the detail of a single InboundCallLog record.
    Read-only — no editing from the panel.
    ---
    Muestra el detalle de un registro InboundCallLog.
    Solo lectura — sin edición desde el panel.
    """
    template_name = "panel/ivr/inbound_call_log_detail.html"

    def get(self, request, pk):
        from django.shortcuts import get_object_or_404
        log = get_object_or_404(InboundCallLog, pk=pk, company=request.company)
        return render(request, self.template_name, {"log": log})

class InboundCallLogDeleteView(AdminRoleRequiredMixin, View):
    """
    Deletes a single InboundCallLog record (ADMIN only).
    ---
    Elimina un registro InboundCallLog (solo ADMIN).
    """

    def post(self, request, pk):
        from django.shortcuts import get_object_or_404
        from django.contrib import messages
        log = get_object_or_404(InboundCallLog, pk=pk, company=request.company)
        log.delete()
        messages.success(request, "Registro de llamada eliminado.")
        return redirect("panel:inbound_call_log_list")
