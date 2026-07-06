# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_ivr.py


from django.contrib import messages as django_messages
from django.views.generic import View, ListView, UpdateView, CreateView, DeleteView
from django.shortcuts import redirect, render
from django.db.models import Q
from django.utils.timezone import now
from django.forms import modelformset_factory

from panel.mixins import AdminRoleRequiredMixin
from panel.forms import (
    SectionForm,
    SectionScheduleForm,
    ContactForm,
    CallFlowForm,
    CorporateVoiceProfileForm,
    BlockedCallerForm,
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
    InboundCallLog,
)
import logging

logger = logging.getLogger(__name__)

class SectionListView (AdminRoleRequiredMixin ,ListView ):
    """
    Lists all Section records belonging to the authenticated user's company.
    Annotates each Section with two filtered counts:
      - ivr_contact_count: contacts whose linked CompanyUser is None or has a
        role other than WORKSHOP/DRIVER (true IVR contacts).
      - worker_count: contacts whose linked CompanyUser has role WORKSHOP or DRIVER.
    Accessible only to users with the ADMIN role.
    ---
    Lista todos los registros Section pertenecientes a la empresa del usuario autenticado.
    Anota cada Section con dos contadores filtrados:
      - ivr_contact_count: contactos cuyo CompanyUser vinculado es None o tiene un rol
        distinto de WORKSHOP/DRIVER (contactos IVR reales).
      - worker_count: contactos cuyo CompanyUser vinculado tiene rol WORKSHOP o DRIVER.
    Solo accesible para usuarios con rol ADMIN.
    """

    model =Section 
    template_name ="panel/sections/list.html"
    context_object_name ="sections"

    def get_queryset (self ):
        """
        Returns Section records scoped to the authenticated user's company,
        annotated with ivr_contact_count and worker_count.
        ivr_contact_count excludes contacts linked to WORKSHOP or DRIVER users.
        worker_count counts only contacts linked to WORKSHOP or DRIVER users.
        ---
        Retorna los registros Section acotados a la empresa del usuario autenticado,
        anotados con ivr_contact_count y worker_count.
        ivr_contact_count excluye contactos vinculados a usuarios WORKSHOP o DRIVER.
        worker_count cuenta solo los contactos vinculados a usuarios WORKSHOP o DRIVER.
        """
        from django .db .models import Count ,Q as _Q 
        return Section .objects .filter (
        company =self .request .user .company_user .company 
        ).annotate (


        ivr_contact_count =Count (
        "contacts",
        filter =_Q (
        _Q (contacts__company_user__isnull =True )
        |~_Q (contacts__company_user__role__in =["WORKSHOP","DRIVER"])
        ),
        distinct =True ,
        ),


        worker_count =Count (
        "contacts",
        filter =_Q (contacts__company_user__role__in =["WORKSHOP","DRIVER"]),
        distinct =True ,
        ),
        ).order_by ("name")

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
        context ["active_nav"]="sections"
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

class SectionCreateView (AdminRoleRequiredMixin ,CreateView ):
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

    model =Section 
    form_class =SectionForm 
    template_name ="panel/sections/form.html"

    def _get_schedule_formset_class (self ):
        """
        Returns the SectionSchedule inline formset class with 5 empty extra forms.
        ---
        Retorna la clase de formset inline de SectionSchedule con 5 formularios extra vacíos.
        """
        return modelformset_factory (
        SectionSchedule ,
        form =SectionScheduleForm ,
        extra =5 ,
        can_delete =True ,
        )

    def get_form (self ,form_class =None ):
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
        form =super ().get_form (form_class )
        company =self .request .user .company_user .company 




        form .fields ["contacts"].queryset =Contact .objects .filter (
        company =company 
        ).exclude (
        company_user__role__in =["WORKSHOP","DRIVER"]
        )
        form .fields ["call_flow"].queryset =CallFlow .objects .filter (
        company =company ,
        is_active =True ,
        ).order_by ("name")
        form .fields ["call_flow"].required =False 
        form .fields ["data_capture_set"].queryset =DataCaptureSet .objects .filter (
        company =company ,
        ).order_by ("name")
        form .fields ["data_capture_set"].required =False 


        from ivr_config .models import WorkdaySchedule as _WorkdaySchedule 
        form .fields ["workday_schedule"].queryset =_WorkdaySchedule .objects .filter (
        company =company ,
        ).order_by ("label")
        form .fields ["workday_schedule"].required =False 
        return form 

    def get (self ,request ,*args ,**kwargs ):
        """
        Renders the section form with an empty schedule formset.
        ---
        Renderiza el formulario de sección con un formset de horarios vacío.
        """
        self .object =None 
        form =self .get_form ()
        ScheduleFormSet =self ._get_schedule_formset_class ()
        schedule_formset =ScheduleFormSet (
        queryset =SectionSchedule .objects .none (),
        prefix ="schedules",
        )
        return self .render_to_response (
        self .get_context_data (form =form ,schedule_formset =schedule_formset )
        )

    def post (self ,request ,*args ,**kwargs ):
        """
        Validates and saves both the section form and the schedule formset.
        ---
        Valida y guarda tanto el formulario de sección como el formset de horarios.
        """
        self .object =None 
        form =self .get_form ()
        ScheduleFormSet =self ._get_schedule_formset_class ()
        schedule_formset =ScheduleFormSet (
        request .POST ,
        queryset =SectionSchedule .objects .none (),
        prefix ="schedules",
        )
        if form .is_valid ()and schedule_formset .is_valid ():
            return self ._form_valid (form ,schedule_formset )
        return self .render_to_response (
        self .get_context_data (form =form ,schedule_formset =schedule_formset )
        )

    def _form_valid (self ,form ,schedule_formset ):
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
        from django .contrib import messages as django_messages 
        company =self .request .user .company_user .company 
        form .instance .company =company 



        raw_json =self .request .POST .get ("capture_fields_json","").strip ()
        capture_name =self .request .POST .get ("capture_set_name","").strip ()
        if raw_json and raw_json !="[]":


            try :
                parsed_fields =json .loads (raw_json )
            except (ValueError ,TypeError ):
                parsed_fields =[]
            dcs_name =capture_name or f"Captura — {form.cleaned_data.get('name', 'Sección')}"
            new_dcs =DataCaptureSet .objects .create (
            company =company ,
            name =dcs_name ,
            fields =parsed_fields ,
            )
            form .instance .data_capture_set =new_dcs 

        self .object =form .save ()
        schedules =schedule_formset .save (commit =False )
        for schedule in schedules :
            schedule .section =self .object 
            schedule .save ()
        for deleted in schedule_formset .deleted_objects :
            deleted .delete ()
        django_messages .success (
        self .request ,
        f"Sección '{self.object.name}' creada correctamente."
        )
        return redirect ("/panel/sections/")

    def get_context_data (self ,**kwargs ):
        """
        Adds company, company_user, own_presence, action flag and schedule_formset.
        ---
        Añade company, company_user, own_presence, flag de acción y schedule_formset.
        """
        context =super ().get_context_data (**kwargs )
        context ["company"]=self .request .user .company_user .company 
        context ["company_user"]=self .request .user .company_user 
        context ["own_presence"]=self ._get_own_presence ()
        context ["active_nav"]="sections"
        context ["action"]="Crear"
        context ["section_workers"]=[]
        if "schedule_formset"not in context :
            ScheduleFormSet =self ._get_schedule_formset_class ()
            context ["schedule_formset"]=ScheduleFormSet (
            queryset =SectionSchedule .objects .none (),
            prefix ="schedules",
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

class SectionUpdateView (AdminRoleRequiredMixin ,UpdateView ):
    """
    Allows an ADMIN to update an existing Section belonging to their company.
    Prevents editing sections from other companies.
    Manages an inline SectionSchedule formset pre-populated with existing time slots.
    ---
    Permite a un ADMIN actualizar una Section existente de su empresa.
    Impide editar secciones de otras empresas.
    Gestiona un formset inline de SectionSchedule prerellenado con las franjas existentes.
    """

    model =Section 
    form_class =SectionForm 
    template_name ="panel/sections/form.html"

    def _get_schedule_formset_class (self ):
        """
        Returns the SectionSchedule inline formset class with 3 extra empty forms.
        ---
        Retorna la clase de formset inline de SectionSchedule con 3 formularios extra vacíos.
        """
        return modelformset_factory (
        SectionSchedule ,
        form =SectionScheduleForm ,
        extra =3 ,
        can_delete =True ,
        )

    def get_queryset (self ):
        """
        Restricts the queryset to Section records of the authenticated user's company.
        ---
        Restringe el queryset a los registros Section de la empresa del usuario autenticado.
        """
        return Section .objects .filter (
        company =self .request .user .company_user .company 
        )

    def get_form (self ,form_class =None ):
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
        form =super ().get_form (form_class )
        company =self .request .user .company_user .company 




        form .fields ["contacts"].queryset =Contact .objects .filter (
        company =company 
        ).exclude (
        company_user__role__in =["WORKSHOP","DRIVER"]
        )
        form .fields ["call_flow"].queryset =CallFlow .objects .filter (
        company =company ,
        is_active =True ,
        ).order_by ("name")
        form .fields ["call_flow"].required =False 
        form .fields ["data_capture_set"].queryset =DataCaptureSet .objects .filter (
        company =company ,
        ).order_by ("name")
        form .fields ["data_capture_set"].required =False 


        from ivr_config .models import WorkdaySchedule as _WorkdaySchedule 
        form .fields ["workday_schedule"].queryset =_WorkdaySchedule .objects .filter (
        company =company ,
        ).order_by ("label")
        form .fields ["workday_schedule"].required =False 
        return form 

    def get (self ,request ,*args ,**kwargs ):
        """
        Renders the section form pre-populated with existing schedules.
        ---
        Renderiza el formulario de sección prerellenado con los horarios existentes.
        """
        self .object =self .get_object ()
        form =self .get_form ()
        ScheduleFormSet =self ._get_schedule_formset_class ()
        schedule_formset =ScheduleFormSet (
        queryset =SectionSchedule .objects .filter (section =self .object ).order_by ("weekday","time_open"),
        prefix ="schedules",
        )
        return self .render_to_response (
        self .get_context_data (form =form ,schedule_formset =schedule_formset )
        )

    def post (self ,request ,*args ,**kwargs ):
        """
        Validates and saves both the section form and the schedule formset.
        ---
        Valida y guarda tanto el formulario de sección como el formset de horarios.
        """
        self .object =self .get_object ()
        form =self .get_form ()
        ScheduleFormSet =self ._get_schedule_formset_class ()
        schedule_formset =ScheduleFormSet (
        request .POST ,
        queryset =SectionSchedule .objects .filter (section =self .object ).order_by ("weekday","time_open"),
        prefix ="schedules",
        )
        if form .is_valid ()and schedule_formset .is_valid ():
            return self ._form_valid (form ,schedule_formset )
        return self .render_to_response (
        self .get_context_data (form =form ,schedule_formset =schedule_formset )
        )

    def _form_valid (self ,form ,schedule_formset ):
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
        from django .contrib import messages as django_messages 
        company =self .request .user .company_user .company 



        raw_json =self .request .POST .get ("capture_fields_json","").strip ()
        capture_name =self .request .POST .get ("capture_set_name","").strip ()
        if raw_json and raw_json !="[]":


            try :
                parsed_fields =json .loads (raw_json )
            except (ValueError ,TypeError ):
                parsed_fields =[]
            existing_dcs =self .object .data_capture_set if self .object .data_capture_set_id else None 
            if existing_dcs is not None :


                if capture_name :
                    existing_dcs .name =capture_name 
                existing_dcs .fields =parsed_fields 
                existing_dcs .save (update_fields =["name","fields","updated_at"])
            else :


                dcs_name =capture_name or f"Captura — {form.cleaned_data.get('name', 'Sección')}"
                new_dcs =DataCaptureSet .objects .create (
                company =company ,
                name =dcs_name ,
                fields =parsed_fields ,
                )
                form .instance .data_capture_set =new_dcs 











        _worker_contacts =list (
        self .object .contacts .filter (
        company_user__role__in =["WORKSHOP","DRIVER"]
        ).values_list ("pk",flat =True )
        )

        self .object =form .save ()



        if _worker_contacts :
            self .object .contacts .add (*_worker_contacts )
            logger .info (
            "# [SECTION UPDATE] %d contacto(s) WORKSHOP/DRIVER preservados en M2M de Section pk=%s.",
            len (_worker_contacts ),
            self .object .pk ,
            )

        schedules =schedule_formset .save (commit =False )
        for schedule in schedules :
            schedule .section =self .object 
            schedule .save ()
        for deleted in schedule_formset .deleted_objects :
            deleted .delete ()
        django_messages .success (
        self .request ,
        f"Sección '{self.object.name}' actualizada correctamente."
        )
        return redirect ("/panel/sections/")

    def get_context_data (self ,**kwargs ):
        """
        Adds company, company_user, own_presence, action flag and schedule_formset.
        ---
        Añade company, company_user, own_presence, flag de acción y schedule_formset.
        """
        context =super ().get_context_data (**kwargs )
        context ["company"]=self .request .user .company_user .company 
        context ["company_user"]=self .request .user .company_user 
        context ["own_presence"]=self ._get_own_presence ()
        context ["active_nav"]="sections"
        context ["action"]="Guardar"


        _section_contacts =(
        self .object .contacts 
        .filter (company_user__isnull =False )
        .select_related ("company_user__user")
        .order_by ("company_user__user__username")
        )
        _workers =[]
        for _contact in _section_contacts :
            _cu =_contact .company_user 
            _cu .contact_phone =_contact .phone_number or ""
            _cu .is_ivr_active =_contact .is_internal 
            _workers .append (_cu )
        context ["section_workers"]=_workers 


        from ivr_config .models import WorkdaySchedule as _WorkdaySchedule 
        context ["workday_schedules"]=list (
        _WorkdaySchedule .objects .filter (company =self .request .user .company_user .company )
        .order_by ("label")
        )
        if "schedule_formset"not in context :
            ScheduleFormSet =self ._get_schedule_formset_class ()
            context ["schedule_formset"]=ScheduleFormSet (
            queryset =SectionSchedule .objects .filter (section =self .object ).order_by ("weekday","time_open"),
            prefix ="schedules",
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

class CallFlowListView (AdminRoleRequiredMixin ,ListView ):
    """
    Lists all CallFlow records belonging to the authenticated user's company.
    Accessible only to users with the ADMIN role.
    ---
    Lista todos los registros CallFlow pertenecientes a la empresa del usuario autenticado.
    Solo accesible para usuarios con rol ADMIN.
    """

    model =CallFlow 
    template_name ="panel/callflows/list.html"
    context_object_name ="call_flows"

    def get_queryset (self ):
        """
        Returns CallFlow records scoped to the authenticated user's company.
        ---
        Retorna los registros CallFlow acotados a la empresa del usuario autenticado.
        """
        return CallFlow .objects .filter (
        company =self .request .user .company_user .company 
        ).order_by ("name")

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
        context ["active_nav"]="callflows"
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
        company_user__role__in =["WORKSHOP","DRIVER"]
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
        company_user__role__in =["WORKSHOP","DRIVER"]
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

class PhoneNumberListView (AdminRoleRequiredMixin ,ListView ):
    """
    Lists all PhoneNumber records belonging to the authenticated user's company.
    Read-only view: Twilio number assignment is managed by the superuser.
    Accessible only to users with the ADMIN role.
    ---
    Lista todos los registros PhoneNumber pertenecientes a la empresa del usuario autenticado.
    Vista de solo lectura: la asignación de números Twilio la gestiona el superusuario.
    Solo accesible para usuarios con rol ADMIN.
    """

    model =PhoneNumber 
    template_name ="panel/phonenumbers/list.html"
    context_object_name ="phone_numbers"

    def get_queryset (self ):
        """
        Returns PhoneNumber records scoped to the authenticated user's company.
        ---
        Retorna los registros PhoneNumber acotados a la empresa del usuario autenticado.
        """
        return PhoneNumber .objects .filter (
        company =self .request .user .company_user .company 
        ).select_related ("call_flow").order_by ("number")

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
        context ["active_nav"]="phonenumbers"
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

class BlockedCallerListView (AdminRoleRequiredMixin ,ListView ):
    """
    Lists all BlockedCaller records for the authenticated user's company.
    Shows active blocks (blocked_until > now) and expired history separately.
    Accessible only to users with the ADMIN role.
    ---
    Lista todos los registros BlockedCaller de la empresa del usuario autenticado.
    Muestra los bloqueos activos (blocked_until > now) e historial expirado por separado.
    Solo accesible para usuarios con rol ADMIN.
    """

    model =BlockedCaller 
    template_name ="panel/blockedcallers/list.html"
    context_object_name ="blocked_callers"

    def get_queryset (self ):
        """
        Returns all BlockedCaller records for the company, ordered by most recent first.
        ---
        Retorna todos los registros BlockedCaller de la empresa, ordenados por más reciente primero.
        """
        return BlockedCaller .objects .filter (
        company =self .request .user .company_user .company 
        ).select_related ("blocked_by").order_by ("-blocked_at")

    def get_context_data (self ,**kwargs ):
        """
        Adds active/expired partition, company, company_user and own_presence to context.
        ---
        Añade la partición activos/expirados, company, company_user y own_presence al contexto.
        """
        context =super ().get_context_data (**kwargs )
        company_user =self .request .user .company_user 
        all_records =context ["blocked_callers"]
        context ["active_blocks"]=[b for b in all_records if b .is_active ]
        context ["expired_blocks"]=[b for b in all_records if not b .is_active ]
        context ["company"]=company_user .company 
        context ["company_user"]=company_user 
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

class DataCaptureSetListView (AdminRoleRequiredMixin ,ListView ):
    """
    Lists all DataCaptureSet records belonging to the authenticated user's company.
    Accessible only to users with the ADMIN role.
    ---
    Lista todos los registros DataCaptureSet pertenecientes a la empresa del usuario autenticado.
    Solo accesible para usuarios con rol ADMIN.
    """

    model =DataCaptureSet 
    template_name ="panel/datacapturesets/list.html"
    context_object_name ="capture_sets"

    def get_queryset (self ):
        """
        Returns DataCaptureSet records scoped to the authenticated user's company,
        ordered alphabetically by name.
        ---
        Retorna los registros DataCaptureSet acotados a la empresa del usuario autenticado,
        ordenados alfabéticamente por nombre.
        """
        return DataCaptureSet .objects .filter (
        company =self .request .user .company_user .company 
        ).order_by ("name")

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
        context ["active_nav"]="datacapturesets"
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
        context ["section_workers"]=list (
        CompanyUser .objects .filter (
        company =self .request .user .company_user .company ,
        user__isnull =False ,
        contact_profile__section =self .object ,
        ).select_related ("user","contact").order_by ("user__username")
        )
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


# ---------------------------------------------------------------------------
# Fleet views — re-exported from fleet.views (H12/H21 split)
# Vistas de flota — re-exportadas desde fleet.views (split H12/H21)
# ---------------------------------------------------------------------------
from fleet.views import (
    MachineAssetListView,
    MachineAssetCreateView,
    MachineAssetUpdateView,
    MachineAssetDeactivateView,
    MachineAssetReactivateView,
    MachineAssetDeleteView,
    MachineAssetAnalyticsView,
)

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
