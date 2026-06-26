



from django .contrib .auth import update_session_auth_hash 
from django .contrib .auth .views import LoginView ,LogoutView 
from django .contrib import messages as django_messages 
from django .views .generic import TemplateView ,View ,ListView ,UpdateView ,CreateView ,DeleteView 
from django .shortcuts import redirect ,render 
from django .db import models as django_models 
from django .db .models import Q ,Prefetch 
from django .utils .timezone import now 
from django .forms import modelformset_factory 
from django .views .decorators .csrf import csrf_exempt 
from django .utils .decorators import method_decorator 

from panel .mixins import CompanyUserRequiredMixin ,AdminRoleRequiredMixin ,WorkshopRequiredMixin ,SupervisorAccessMixin 
from panel .models import AnalyticsProfile 
from panel .forms import (
PanelAuthenticationForm ,
PresenceStatusForm ,
SectionForm ,
SectionScheduleForm ,
ContactForm ,
CallFlowForm ,
CorporateVoiceProfileForm ,
BlockedCallerForm ,
CompanyUserCreateForm ,
PanelPasswordChangeForm ,
PanelSetPasswordForm ,
DataCaptureSetForm ,
)
from ivr_config .models import (
Section ,
SectionSchedule ,
Contact ,
PresenceStatus ,
CompanyUser ,
CallFlow ,
PhoneNumber ,
CorporateVoiceProfile ,
BlockedCaller ,
DataCaptureSet ,
InboundCallLog ,
)
from whatsapp .models import WhatsAppTemplate ,WhatsAppSession 
from work_order_processor .models import WorkOrder ,WorkOrderEntry ,WorkOrderEntryLine 
from work_order_processor .services import find_cached_classification 
from work_order_processor .tasks import classify_fault_line ,generate_period_excel ,process_work_order_pdf 
from fleet .models import MachineAsset 
import logging 
import plotly .graph_objects as go 
import plotly .io as pio 

logger =logging .getLogger (__name__ )

# --- Re-exports Fase B: views_operator ---
from panel.views_operator import (
    OperatorDashboardView,
    WorkerSignupView,
    WorkshopAssetAutocompleteView,
    WorkOrderEntryUploadView,
    WorkOrderEntryConfirmView,
    WorkOrderEntryFormView,
    WorkOrderEntryHistoryView,
    WorkshopAssetDetailView,
    WorkOrderDescriptionAutocompleteView,
    WorkshopIntensiveToggleView,
)

# --- Re-exports Fase C: views_workorders ---
from panel.views_workorders import (
    WorkOrderListView,
    DigitalWorkOrderListView,
    WorkOrderUploadView,
    WorkOrderEditView,
    WorkOrderStatusFragmentView,
    WorkOrderLineSaveView,
    WorkOrderEntrySaveDateView,
    MachineAssetAutocompleteView,
    WorkOrderEntryAddView,
    WorkOrderLineInsertView,
    WorkOrderLineReorderView,
    WorkOrderLineRestoreView,
    WorkOrderLineDeleteView,
    WorkOrderDeleteView,
    WorkOrderMarkReviewedView,
    WorkOrderExportView,
    WorkOrderDuplicateSearchView,
    WorkOrderDuplicateDeleteView,
    WorkerAbsenceCreateView,
    WorkerAbsenceUpdateView,
    WorkerAbsenceDeleteView,
    WorkdayScheduleView,
    AbsenceCategoryListView,
    AbsenceCategoryCreateView,
    AbsenceCategoryUpdateView,
    AbsenceCategoryToggleView,
    WorkOrderAdminHistoryView,
    WorkPeriodListView,
    WorkPeriodCreateView,
    WorkPeriodCloseView,
    WorkPeriodLockView,
    WorkOrderAdminExportView,
    WorkOrderMachineFilterView,
    ExportTemplateListView,
    ExportTemplateCreateView,
    ExportTemplateUpdateView,
    ExportTemplateDeleteView,
    WorkOrderAdminExportByTemplateView,
)





class CompanyUserCreateView (SupervisorAccessMixin ,View ):
    """
    Allows a SUPERVISOR or ADMIN to create a new CompanyUser for their company.
    Creates the underlying auth.User with password '1234' and sets
    must_change_password=True so the new user must change it on first login.
    Optionally links the new user to a Section and creates or retrieves the
    associated Contact record if a phone number is provided.
    Updated H13: mixin changed to SupervisorAccessMixin; section, phone_number
    and is_ivr_active fields added; Contact auto-creation/linking logic added.
    ---
    Permite a un SUPERVISOR o ADMIN crear un nuevo CompanyUser para su empresa.
    Crea el auth.User subyacente con contraseña '1234' y establece
    must_change_password=True para forzar el cambio en el primer acceso.
    Opcionalmente vincula el nuevo usuario a una Section y crea o recupera
    el Contact asociado si se indica un número de teléfono.
    Actualización H13: mixin cambiado a SupervisorAccessMixin; campos section,
    phone_number e is_ivr_active añadidos; lógica de auto-creación/vinculación
    de Contact incorporada.
    """

    template_name ="panel/users/create.html"

    def _get_own_presence (self ,company_user ):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        return PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first ()

    def _get_context (self ,request ,form =None ):
        """
        Builds base template context with company, company_user, own_presence
        and sections queryset for the section selector JS pre-fill.
        ---
        Construye el contexto base con company, company_user, own_presence
        y el queryset de secciones para el pre-relleno JS del selector de sección.
        """
        cu =request .user .company_user 
        company =cu .company 
        if form is None :
            form =CompanyUserCreateForm ()
            form .fields ["section"].queryset =Section .objects .filter (
            company =company 
            ).order_by ("name")
        return {
        "company":company ,
        "company_user":cu ,
        "own_presence":self ._get_own_presence (cu ),
        "active_nav":"users",
        "form":form ,
        "sections_data":list (
        Section .objects .filter (company =company ).values (
        "id","default_role"
        )
        ),
        }

    def get (self ,request ,*args ,**kwargs ):
        """
        Renders the user creation form with section queryset scoped to company.
        ---
        Renderiza el formulario de creación de usuario con el queryset de secciones
        acotado a la empresa.
        """
        return render (request ,self .template_name ,self ._get_context (request ))

    def post (self ,request ,*args ,**kwargs ):
        """
        Validates the form, creates auth.User and CompanyUser, optionally creates
        or retrieves the Contact record and links it to the new CompanyUser,
        then optionally assigns the new user to the selected Section.
        Redirects to user list on success.
        ---
        Valida el formulario, crea auth.User y CompanyUser, opcionalmente crea
        o recupera el Contact y lo vincula al nuevo CompanyUser, y opcionalmente
        asigna el nuevo usuario a la Section seleccionada.
        Redirige a la lista de usuarios en caso de éxito.
        """
        from django .contrib .auth .models import User as AuthUser 

        cu =request .user .company_user 
        company =cu .company 

        form =CompanyUserCreateForm (request .POST )
        form .fields ["section"].queryset =Section .objects .filter (
        company =company 
        ).order_by ("name")

        if not form .is_valid ():
            context =self ._get_context (request ,form )
            return render (request ,self .template_name ,context )



        # Password and must_change_password depend on role.
        # Contraseña y must_change_password dependen del rol.
        _workshop_roles = (
            CompanyUser.ROLE_WORKSHOP,
            CompanyUser.ROLE_WORKSHOPBOSS,
        )
        _role = form.cleaned_data["role"]
        _must_change = _role not in _workshop_roles

        auth_user =AuthUser .objects .create_user (
        username =form .cleaned_data ["username"],
        first_name =form .cleaned_data .get ("first_name",""),
        last_name =form .cleaned_data .get ("last_name",""),
        password =form .get_initial_password (),
        is_staff =False ,
        is_superuser =False ,
        )



        new_cu =CompanyUser .objects .create (
        user =auth_user ,
        company =company ,
        role =_role ,
        is_active =True ,
        must_change_password =_must_change ,
        dni =form .cleaned_data .get ("dni", "").strip(),
        )
        logger .info (
        "# [USER CREATE] CompanyUser pk=%s (username='%s') creado por %s.",
        new_cu .pk ,
        auth_user .username ,
        request .user .username ,
        )







        _schedule_pk =request .POST .get ("workday_schedule_pk","").strip ()
        if _schedule_pk :
            try :
                from ivr_config .models import WorkdaySchedule as _WorkdaySchedule 
                _schedule =_WorkdaySchedule .objects .get (pk =int (_schedule_pk ),company =company )
                new_cu .workday_schedule =_schedule 
                new_cu .save (update_fields =["workday_schedule"])
                logger .info (
                "# [USER CREATE] WorkdaySchedule pk=%s asignado a CompanyUser pk=%s.",
                _schedule .pk ,
                new_cu .pk ,
                )
            except (ValueError ,TypeError ):
                logger .warning (
                "# [USER CREATE] workday_schedule_pk='%s' no es un entero valido — ignorado.",
                _schedule_pk ,
                )
            except _WorkdaySchedule .DoesNotExist :
                logger .warning (
                "# [USER CREATE] WorkdaySchedule pk=%s no pertenece a la empresa pk=%s — ignorado.",
                _schedule_pk ,
                company .pk ,
                )










        phone_number =form .cleaned_data .get ("phone_number","")
        is_ivr_active =form .cleaned_data .get ("is_ivr_active",True )
        section =form .cleaned_data .get ("section")



        _display_name =(
        f"{form.cleaned_data.get('first_name', '')} "
        f"{form.cleaned_data.get('last_name', '')}".strip ()
        or auth_user .username 
        )

        contact =None 

        if phone_number :


            contact ,created =Contact .objects .get_or_create (
            company =company ,
            phone_number =phone_number ,
            defaults ={
            "name":_display_name ,
            "is_internal":is_ivr_active ,
            "company_user":new_cu ,
            },
            )
            if not created :


                contact .company_user =new_cu 
                contact .is_internal =is_ivr_active 
                contact .save (update_fields =["company_user","is_internal"])
                logger .info (
                "# [USER CREATE] Contact existente pk=%s vinculado a CompanyUser pk=%s.",
                contact .pk ,
                new_cu .pk ,
                )
            else :
                logger .info (
                "# [USER CREATE] Contact nuevo pk=%s creado y vinculado a CompanyUser pk=%s.",
                contact .pk ,
                new_cu .pk ,
                )
        elif section is not None :




            contact =Contact .objects .create (
            company =company ,
            phone_number ="",
            name =_display_name ,
            is_internal =is_ivr_active ,
            company_user =new_cu ,
            )
            logger .info (
            "# [USER CREATE] Contact sin telefono pk=%s creado para CompanyUser pk=%s.",
            contact .pk ,
            new_cu .pk ,
            )



        if section is not None and contact is not None :
            section .contacts .add (contact )
            logger .info (
            "# [USER CREATE] Contact pk=%s añadido a Section pk=%s.",
            contact .pk ,
            section .pk ,
            )

        django_messages .success (
        request ,
        f"Usuario '{auth_user.username}' creado correctamente. "
        f"Deberá cambiar su contraseña en el primer acceso."
        )
        return redirect ("/panel/users/")



class CompanyUserListView (SupervisorAccessMixin ,ListView ):
    """
    Lists all CompanyUser accounts belonging to the authenticated user's company.
    Accessible only to users with the ADMIN role.
    Supports optional filtering by section via GET parameter ?section=<pk>.
    ---
    Lista todas las cuentas CompanyUser pertenecientes a la empresa del usuario autenticado.
    Solo accesible para usuarios con rol ADMIN.
    Soporta filtrado opcional por sección mediante el parámetro GET ?section=<pk>.
    """

    model =CompanyUser 
    template_name ="panel/users/list.html"
    context_object_name ="company_users"

    # Valid sort fields mapped to ORM expressions.
    # Campos de ordenamiento válidos mapeados a expresiones ORM.
    _SORT_FIELDS = {
        "username":  "user__username",
        "fullname":  "user__last_name",
        "role":      "role",
        "status":    "is_active",
    }
    _DEFAULT_SORT = "username"

    def get_queryset(self):
        """
        Returns CompanyUser records scoped to the authenticated user's company.
        Supports optional filtering by section (?section=<pk>) and server-side
        column sorting via ?sort=<field>&dir=<asc|desc>.
        Valid sort fields: username, fullname, role, status.
        ---
        Retorna los registros CompanyUser acotados a la empresa del usuario
        autenticado. Soporta filtrado por sección (?section=<pk>) y ordenamiento
        server-side por columna mediante ?sort=<campo>&dir=<asc|desc>.
        Campos válidos: username, fullname, role, status.
        """
        company = self.request.user.company_user.company
        qs = CompanyUser.objects.filter(
            company=company,
        ).select_related("user")

        # --- Section filter / Filtro por sección ---
        section_pk = self.request.GET.get("section", "").strip()
        if section_pk:
            try:
                from ivr_config.models import Section as _Section
                section_obj = _Section.objects.get(
                    pk=int(section_pk), company=company
                )
                qs = qs.filter(contact_profile__sections=section_obj)
            except (ValueError, TypeError, _Section.DoesNotExist):
                pass

        # --- Column sort / Ordenamiento por columna ---
        sort_key = self.request.GET.get("sort", self._DEFAULT_SORT)
        if sort_key not in self._SORT_FIELDS:
            sort_key = self._DEFAULT_SORT
        sort_dir = self.request.GET.get("dir", "asc")
        orm_field = self._SORT_FIELDS[sort_key]
        if sort_dir == "desc":
            orm_field = f"-{orm_field}"
        # Secondary sort by username for stable ordering.
        # Ordenamiento secundario por username para estabilidad.
        qs = qs.order_by(orm_field, "user__username")

        return qs

    def get_context_data (self ,**kwargs ):
        """
        Adds company, company_user and sections list to template context.
        Passes the currently selected section pk for filter persistence.
        ---
        Añade company, company_user y lista de secciones al contexto de la plantilla.
        Pasa el pk de sección seleccionado actualmente para persistencia del filtro.
        """
        context =super ().get_context_data (**kwargs )
        company =self .request .user .company_user .company 
        context ["company"]=company 
        context ["company_user"]=self .request .user .company_user 
        context ["own_presence"]=self ._get_own_presence ()
        context ["active_nav"]="users"
        context ["sections"]=Section .objects .filter (
        company =company 
        ).order_by ("name")
        context["selected_section"] = self.request.GET.get("section", "")
        context["sort_key"] = self.request.GET.get(
            "sort", self._DEFAULT_SORT
        )
        context["sort_dir"] = self.request.GET.get("dir", "asc")
        # Column definitions for sort header rendering in template.
        # Definiciones de columnas para renderizar cabeceras de sort en plantilla.
        context["sort_columns"] = [
            ("username", "Usuario"),
            ("fullname", "Nombre completo"),
            ("role",     "Rol"),
            ("status",   "Estado"),
        ]
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


class CompanyUserUpdateView (SupervisorAccessMixin ,UpdateView ):
    """
    Allows an ADMIN to update the role, active status and workday schedule
    of a CompanyUser belonging to the same company.
    Prevents editing users from other companies.
    The workday_schedule queryset is restricted to the authenticated
    company's own schedules via get_form() — no schedule from another
    company can be selected.
    ---
    Permite a un ADMIN actualizar el rol, el estado activo y el horario de
    jornada de un CompanyUser de la misma empresa.
    Impide editar usuarios de otras empresas.
    El queryset de workday_schedule se restringe a los horarios de la empresa
    autenticada mediante get_form() — ningún horario de otra empresa puede
    ser seleccionado.
    """

    model =CompanyUser 
    template_name ="panel/users/form.html"
    fields =["role","is_active","workday_schedule","dni"]

    def get_queryset (self ):
        """
        Restricts the queryset to CompanyUser records of the authenticated user's company.
        ---
        Restringe el queryset a los registros CompanyUser de la empresa del usuario autenticado.
        """
        return CompanyUser .objects .filter (
        company =self .request .user .company_user .company 
        )

    def get_form (self ,form_class =None ):
        """
        Restricts the workday_schedule queryset to the authenticated user's
        company so that no foreign schedule can be selected from the dropdown.
        Marks workday_schedule as optional (blank allowed).
        Adds Bootstrap CSS class to the dni field.
        ---
        Restringe el queryset de workday_schedule a la empresa del usuario
        autenticado para que ningún horario externo pueda seleccionarse.
        Marca workday_schedule como opcional (blank permitido).
        Añade clase CSS Bootstrap al campo dni.
        """
        from ivr_config .models import WorkdaySchedule 
        form =super ().get_form (form_class )
        company =self .request .user .company_user .company 
        form .fields ["workday_schedule"].queryset =WorkdaySchedule .objects .filter (
        company =company 
        ).order_by ("label")
        form .fields ["workday_schedule"].required =False 
        form .fields ["workday_schedule"].widget .attrs .update ({"class":"form-select"})
        form .fields ["dni"].required =False 
        form .fields ["dni"].widget .attrs .update ({
            "class": "form-control",
            "placeholder": "12345678A",
        })
        return form 

    def post (self ,request ,*args ,**kwargs ):
        """
        Handles standard update and the force-reset action.
        Persists the phone_number field by updating or creating the linked
        Contact record. Respects the 'next' POST parameter for redirect.
        If POST contains 'force_reset', sets must_change_password=True and redirects.
        ---
        Gestiona la actualización estándar y la acción de forzar reset.
        Persiste el campo phone_number actualizando o creando el registro
        Contact vinculado. Respeta el parámetro POST 'next' para la redirección.
        Si el POST contiene 'force_reset', establece must_change_password=True y redirige.
        """
        self .object =self .get_object ()
        next_url =request .POST .get ("next","").strip ()or "/panel/users/"






        if self .object .role in ("WORKSHOP","WORKSHOPBOSS","DRIVER"):
            self .object .is_active =True 
            self .object .save (update_fields =["is_active"])
        if "force_reset"in request .POST :
            self .object .must_change_password =True 
            self .object .save (update_fields =["must_change_password"])
            django_messages .success (
            request ,
            f"Se ha forzado el cambio de contraseña para "
            f"'{self.object.user.username}'."
            )
            return redirect (next_url )




        request .session ["_cu_update_next"]=next_url 


        phone_number =request .POST .get ("phone_number","").strip ()
        if phone_number :
            from ivr_config .models import Contact as _Contact 
            company =self .object .company 
            _contact =_Contact .objects .filter (
            company =company ,company_user =self .object 
            ).first ()
            if _contact is not None :


                if _contact .phone_number !=phone_number :
                    _contact .phone_number =phone_number 
                    _contact .save (update_fields =["phone_number"])
                    logger .info (
                    "# [USER UPDATE] Contact pk=%s phone_number actualizado a '%s'.",
                    _contact .pk ,phone_number ,
                    )
            else :


                _display =(
                self .object .user .get_full_name ()or self .object .user .username 
                )
                _Contact .objects .create (
                company =company ,
                phone_number =phone_number ,
                name =_display ,
                is_internal =True ,
                company_user =self .object ,
                )
                logger .info (
                "# [USER UPDATE] Contact nuevo creado para CompanyUser pk=%s con phone '%s'.",
                self .object .pk ,phone_number ,
                )








        _section_pk_raw =request .POST .get ("section_pk","").strip ()
        if _section_pk_raw is not None :
            from ivr_config .models import Contact as _Contact2 
            from ivr_config .models import Section as _Section 
            _cu_contact =_Contact2 .objects .filter (
            company =self .object .company ,
            company_user =self .object ,
            ).first ()
            if _cu_contact is not None :


                _current_sections =_Section .objects .filter (
                company =self .object .company ,
                contacts =_cu_contact ,
                )
                for _sec in _current_sections :
                    _sec .contacts .remove (_cu_contact )
                    logger .info (
                    "# [USER UPDATE] Contact pk=%s desvinculado de Section pk=%s.",
                    _cu_contact .pk ,_sec .pk ,
                    )


                if _section_pk_raw :
                    try :
                        _new_section =_Section .objects .get (
                        pk =int (_section_pk_raw ),
                        company =self .object .company ,
                        )
                        _new_section .contacts .add (_cu_contact )
                        logger .info (
                        "# [USER UPDATE] Contact pk=%s vinculado a Section pk=%s.",
                        _cu_contact .pk ,_new_section .pk ,
                        )
                    except (ValueError ,TypeError ,_Section .DoesNotExist ):
                        logger .warning (
                        "# [USER UPDATE] section_pk='%s' inválido o no pertenece a la empresa — ignorado.",
                        _section_pk_raw ,
                        )
        return super ().post (request ,*args ,**kwargs )

    def get_success_url (self ):
        """
        Redirects to the 'next' URL stored in session, or falls back to user list.
        ---
        Redirige a la URL 'next' almacenada en sesión, o a la lista de usuarios
        como fallback.
        """
        django_messages .success (
        self .request ,
        f"Usuario '{self.object.user.username}' actualizado correctamente."
        )
        next_url =self .request .session .pop ("_cu_update_next","/panel/users/")
        return next_url 

    def get_context_data (self ,**kwargs ):
        """
        Adds company, company_user, own_presence, contact_phone and next_url
        to context.
        next_url resolution order: POST['next'] → GET['next'] → HTTP_REFERER → /panel/users/.
        Using POST['next'] first ensures the origin is preserved across
        validation re-renders (when the form is re-POSTed after an error,
        HTTP_REFERER would already point to the edit page itself).
        ---
        Añade company, company_user, own_presence, contact_phone y next_url
        al contexto.
        Orden de resolución de next_url: POST['next'] → GET['next'] →
        HTTP_REFERER → /panel/users/.
        Priorizar POST['next'] garantiza que el origen se preserva en
        re-renders de validación (cuando el formulario se re-envía tras error,
        HTTP_REFERER ya apunta a la propia página de edición).
        """
        if not hasattr (self ,'object')or self .object is None :
            self .object =self .get_object ()
        context =super ().get_context_data (**kwargs )
        context ["company"]=self .request .user .company_user .company 
        context ["company_user"]=self .request .user .company_user 
        context ["own_presence"]=self ._get_own_presence ()
        context ["active_nav"]="users"
        from ivr_config .models import Contact as _Contact 
        _contact =_Contact .objects .filter (
        company =self .object .company ,
        company_user =self .object ,
        ).first ()
        context ["contact_phone"]=_contact .phone_number if _contact else ""


        context ["sections"]=Section .objects .filter (
        company =self .object .company 
        ).order_by ("name")


        context ["current_section_pk"]=(
        _contact .sections .values_list ("pk",flat =True ).first ()
        if _contact else None 
        )


        context ["next_url"]=(
        self .request .POST .get ("next","").strip ()
        or self .request .GET .get ("next","").strip ()
        or self .request .META .get ("HTTP_REFERER","")
        or "/panel/users/"
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



class CompanyUserBulkDeleteView (SupervisorAccessMixin ,View ):
    """
    Allows a SUPERVISOR or ADMIN to delete one or more CompanyUser accounts
    belonging to their company in a single operation.

    Flow:
      1. First POST (confirmed not set): evaluate selected pks.
         - Verify all pks belong to the authenticated user's company.
         - Detect IVR-risk users: those whose linked Contact is a member
           of at least one active Section (is_active=True).
         - If no IVR-risk users: delete immediately and redirect.
         - If IVR-risk users exist: render confirmation page with a warning
           listing the at-risk users and their affected sections.
      2. Second POST (confirmed=1): delete all selected users including
         IVR-risk ones. Contact.company_user is SET_NULL by the DB cascade;
         auth.User is deleted explicitly to ensure full cleanup.

    POST /panel/users/bulk-delete/
         Body: selected_users (list of pks)
               confirmed       (optional, '1' to bypass risk warning)
    ---
    Permite a un SUPERVISOR o ADMIN eliminar una o varias cuentas CompanyUser
    de su empresa en una única operación.

    Flujo:
      1. Primer POST (sin confirmed): evaluar pks seleccionados.
         - Verificar que todos los pks pertenecen a la empresa autenticada.
         - Detectar usuarios en riesgo IVR: aquellos cuyo Contact vinculado
           es miembro de al menos una Section activa (is_active=True).
         - Sin usuarios en riesgo: eliminar directamente y redirigir.
         - Con usuarios en riesgo: renderizar página de confirmación con
           aviso listando los usuarios en riesgo y sus secciones afectadas.
      2. Segundo POST (confirmed=1): eliminar todos los seleccionados
         incluidos los en riesgo. Contact.company_user queda a NULL por
         el cascade de la BD; auth.User se elimina explícitamente.

    POST /panel/users/bulk-delete/
         Body: selected_users (lista de pks)
               confirmed       (opcional, '1' para saltarse el aviso de riesgo)
    """

    template_name ="panel/users/bulk_delete_confirm.html"

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

    def _resolve_users (self ,pks_raw ,company ):
        """
        Returns a queryset of CompanyUser records for the given pk list,
        scoped to the provided company. Silently drops invalid or
        cross-company pks.
        ---
        Retorna un queryset de CompanyUser para la lista de pks dada,
        acotado a la empresa proporcionada. Descarta silenciosamente los
        pks inválidos o de otras empresas.
        """
        valid_pks =[]
        for raw in pks_raw :
            try :
                valid_pks .append (int (raw ))
            except (ValueError ,TypeError ):
                pass 
        return CompanyUser .objects .filter (
        pk__in =valid_pks ,
        company =company ,
        ).select_related ("user")

    def _classify_risk (self ,users_qs ):
        """
        Splits the given queryset into two lists:
          - safe_users: CompanyUser records with no active IVR contact.
          - risk_users: CompanyUser records whose linked Contact belongs
            to at least one active Section (is_active=True). Each entry is
            a dict with keys 'cu' and 'sections' (list of Section names).
        A CompanyUser is IVR-risk if:
            contact = Contact.objects.filter(company_user=cu).first()
            contact is not None AND contact.sections.filter(is_active=True).exists()
        ---
        Divide el queryset en dos listas:
          - safe_users: CompanyUser sin contacto IVR activo.
          - risk_users: CompanyUser cuyo Contact vinculado pertenece
            a al menos una Section activa (is_active=True). Cada entrada
            es un dict con claves 'cu' y 'sections' (lista de nombres).
        Un CompanyUser es riesgo IVR si:
            contact = Contact.objects.filter(company_user=cu).first()
            contact is not None AND contact.sections.filter(is_active=True).exists()
        """
        safe_users =[]
        risk_users =[]
        for cu in users_qs :
            contact =Contact .objects .filter (company_user =cu ).first ()
            if contact is not None and contact .sections .filter (is_active =True ).exists ():
                active_sections =list (
                contact .sections .filter (is_active =True ).values_list ("name",flat =True )
                )
                risk_users .append ({"cu":cu ,"sections":active_sections })
            else :
                safe_users .append (cu )
        return safe_users ,risk_users 

    def _delete_users (self ,cu_list ):
        """
        Deletes all CompanyUser records in the given list together with
        their underlying auth.User. The DB cascade sets Contact.company_user
        to NULL automatically (SET_NULL). auth.User is deleted explicitly
        to guarantee full cleanup regardless of cascade configuration.
        Returns the count of deleted CompanyUser records.
        ---
        Elimina todos los registros CompanyUser de la lista junto con su
        auth.User subyacente. El cascade de BD pone Contact.company_user
        a NULL automáticamente (SET_NULL). auth.User se elimina de forma
        explícita para garantizar la limpieza total independientemente
        de la configuración del cascade.
        Retorna el contador de CompanyUser eliminados.
        """
        from django .contrib .auth .models import User as AuthUser 
        count =0 
        for cu in cu_list :
            auth_user_pk =cu .user .pk 
            username =cu .user .username 
            cu .delete ()
            AuthUser .objects .filter (pk =auth_user_pk ).delete ()
            logger .info (
            "# [USER BULK DELETE] CompanyUser '%s' eliminado.",
            username ,
            )
            count +=1 
        return count 

    def post (self ,request ,*args ,**kwargs ):
        """
        Handles both the initial evaluation POST and the confirmed deletion POST.
        On the first POST without 'confirmed': resolves users, classifies IVR risk
        and either deletes immediately (no risk) or renders the confirmation page.
        On the second POST with confirmed='1': deletes all selected users including
        those previously flagged as IVR-risk.
        ---
        Gestiona tanto el POST de evaluación inicial como el POST de confirmación.
        En el primer POST sin 'confirmed': resuelve usuarios, clasifica riesgo IVR
        y elimina directamente (sin riesgo) o renderiza la página de confirmación.
        En el segundo POST con confirmed='1': elimina todos los seleccionados
        incluidos los marcados como riesgo IVR.
        """
        company =request .user .company_user .company 
        company_user =request .user .company_user 
        pks_raw =request .POST .getlist ("selected_users")
        confirmed =request .POST .get ("confirmed","")=="1"



        if not pks_raw :
            django_messages .warning (request ,"No se seleccionó ningún usuario.")
            return redirect ("/panel/users/")

        users_qs =self ._resolve_users (pks_raw ,company )



        users_qs =users_qs .exclude (pk =company_user .pk )

        if not users_qs .exists ():
            django_messages .warning (request ,"No se seleccionó ningún usuario válido.")
            return redirect ("/panel/users/")

        if confirmed :


            count =self ._delete_users (list (users_qs ))
            django_messages .success (
            request ,
            f"{count} usuario{'s' if count != 1 else ''} eliminado"
            f"{'s' if count != 1 else ''} correctamente.",
            )
            return redirect ("/panel/users/")



        safe_users ,risk_users =self ._classify_risk (users_qs )

        if not risk_users :


            count =self ._delete_users (safe_users )
            django_messages .success (
            request ,
            f"{count} usuario{'s' if count != 1 else ''} eliminado"
            f"{'s' if count != 1 else ''} correctamente.",
            )
            return redirect ("/panel/users/")



        all_users =[entry ["cu"]for entry in risk_users ]+safe_users 
        context ={
        "company":company ,
        "company_user":company_user ,
        "own_presence":self ._get_own_presence (request ),
        "active_nav":"users",
        "risk_users":risk_users ,
        "safe_users":safe_users ,
        "selected_pks":[cu .pk for cu in all_users ],
        }
        return render (request ,self .template_name ,context )


class CompanyUserSectionUnlinkView (SupervisorAccessMixin ,View ):
    """
    Unlinks a CompanyUser from a Section by removing their associated Contact
    from the section's contacts M2M relation.
    Redirects back to the section edit form on success.
    Only affects the M2M membership — the CompanyUser account is preserved.
    Scoped to the authenticated user's company; rejects cross-company attempts.

    POST /panel/users/<pk>/unlink-section/
         Body: section_pk (required) — pk of the section to unlink from.
               next (optional)       — URL to redirect to after unlinking.
    ---
    Desvincula un CompanyUser de una Section eliminando su Contact asociado
    de la relación M2M de contactos de la sección.
    Redirige de vuelta al formulario de edición de sección en caso de éxito.
    Solo afecta a la membresía M2M — la cuenta CompanyUser se conserva.
    Acotado a la empresa del usuario autenticado; rechaza intentos entre empresas.

    POST /panel/users/<pk>/unlink-section/
         Body: section_pk (requerido) — pk de la sección de la que desvincular.
               next (opcional)        — URL a la que redirigir tras desvincular.
    """

    def post (self ,request ,pk ,*args ,**kwargs ):
        """
        Removes the Contact associated with the CompanyUser from the given section.
        ---
        Elimina el Contact asociado al CompanyUser de la sección indicada.
        """
        company =request .user .company_user .company 
        section_pk =request .POST .get ("section_pk","").strip ()
        next_url =request .POST .get ("next","/panel/sections/")



        try :
            cu =CompanyUser .objects .get (pk =pk ,company =company )
        except CompanyUser .DoesNotExist :
            django_messages .error (request ,"Usuario no encontrado.")
            return redirect (next_url )



        try :
            section =Section .objects .get (pk =int (section_pk ),company =company )
        except (ValueError ,TypeError ,Section .DoesNotExist ):
            django_messages .error (request ,"Sección no encontrada.")
            return redirect (next_url )



        contact =getattr (cu ,"contact",None )
        if contact is None :
            try :
                from ivr_config .models import Contact as _Contact 
                contact =_Contact .objects .filter (
                company =company ,
                company_user =cu ,
                ).first ()
            except Exception :
                contact =None 

        if contact and section .contacts .filter (pk =contact .pk ).exists ():
            section .contacts .remove (contact )
            django_messages .success (
            request ,
            f"Trabajador '{cu.user.get_full_name() or cu.user.username}' "
            f"desvinculado de la sección '{section.name}'."
            )
        else :
            django_messages .warning (
            request ,
            f"El trabajador no estaba vinculado a la sección '{section.name}'."
            )

        return redirect (next_url )



class WorkerScheduleUpdateView (SupervisorAccessMixin ,View ):
    """
    Updates the workday_schedule FK of a single CompanyUser belonging to
    the authenticated user's company. Designed for AJAX calls from the
    section edit form worker table.
    Returns JSON {"ok": true} on success or {"ok": false, "error": "..."}
    on failure.

    POST /panel/users/<pk>/schedule/
         Body: schedule_pk — pk of the WorkdaySchedule to assign,
                             or empty string to clear the assignment.
    ---
    Actualiza la FK workday_schedule de un CompanyUser perteneciente a la
    empresa del usuario autenticado. Diseñado para llamadas AJAX desde la
    tabla de trabajadores del formulario de edición de sección.
    Devuelve JSON {"ok": true} en éxito o {"ok": false, "error": "..."}
    en caso de fallo.

    POST /panel/users/<pk>/schedule/
         Body: schedule_pk — pk del WorkdaySchedule a asignar,
                             o cadena vacía para limpiar la asignación.
    """

    def post (self ,request ,pk ,*args ,**kwargs ):
        """
        Resolves the CompanyUser and the WorkdaySchedule (if provided),
        validates company ownership for both, and updates the FK.
        ---
        Resuelve el CompanyUser y el WorkdaySchedule (si se proporciona),
        valida la propiedad de empresa en ambos y actualiza la FK.
        """
        import json as _json 
        from django .http import JsonResponse 
        from ivr_config .models import WorkdaySchedule as _WorkdaySchedule 

        company =request .user .company_user .company 



        try :
            cu =CompanyUser .objects .get (pk =pk ,company =company )
        except CompanyUser .DoesNotExist :
            return JsonResponse ({"ok":False ,"error":"Usuario no encontrado."},status =404 )

        schedule_pk =request .POST .get ("schedule_pk","").strip ()

        if schedule_pk :


            try :
                schedule =_WorkdaySchedule .objects .get (pk =int (schedule_pk ),company =company )
            except (ValueError ,TypeError ,_WorkdaySchedule .DoesNotExist ):
                return JsonResponse ({"ok":False ,"error":"Horario no encontrado."},status =404 )
            cu .workday_schedule =schedule 
        else :


            cu .workday_schedule =None 

        cu .save (update_fields =["workday_schedule"])
        logger .info (
        "# [WORKER SCHEDULE] CompanyUser pk=%s — workday_schedule -> %s (por %s).",
        cu .pk ,
        cu .workday_schedule_id ,
        request .user .username ,
        )
        return JsonResponse ({"ok":True })


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


class PanelLoginView (LoginView ):
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

    template_name ="panel/login.html"
    authentication_form =PanelAuthenticationForm 
    next_page ="/panel/"

    def dispatch (self ,request ,*args ,**kwargs ):
        """
        Redirect authenticated CompanyUser accounts directly to the dashboard.
        If the user carries a valid trusted-device cookie, authenticate them
        directly without showing the login form.
        Superusers and users without CompanyUser proceed to the login form normally.
        ---
        Redirige las cuentas CompanyUser autenticadas directamente al dashboard.
        Si el usuario porta una cookie de dispositivo de confianza válida, lo
        autentica directamente sin mostrar el formulario de login.
        Los superusuarios y usuarios sin CompanyUser acceden al formulario normalmente.
        """


        if request .user .is_authenticated :
            company_user =getattr (request .user ,"company_user",None )
            if company_user is not None and company_user .is_active :
                from django .shortcuts import redirect 
                return redirect (self .next_page )
        return super ().dispatch (request ,*args ,**kwargs )

    def get_context_data (self ,**kwargs ):
        """
        Injects trusted_device_user into the template context when a valid
        trusted-device cookie is present, so the template can render the
        quick-access mode.
        ---
        Inyecta trusted_device_user en el contexto del template cuando hay
        una cookie de dispositivo de confianza válida, para que el template
        pueda renderizar el modo de acceso rápido.
        """
        from django .core import signing 
        from django .contrib .auth import get_user_model 
        context =super ().get_context_data (**kwargs )
        _raw =self .request .COOKIES .get ("eb_trusted_device","")
        if _raw and not self .request .GET .get ("force_form"):
            try :
                _payload =signing .loads (_raw ,max_age =365 *24 *3600 )
                _user_id =_payload .get ("uid")
                _device_token =_payload .get ("tok")
                User =get_user_model ()
                _user =User .objects .select_related ("company_user").get (pk =_user_id )
                _cu =getattr (_user ,"company_user",None )
                if (
                _cu is not None 
                and _cu .is_active 
                and _cu .trusted_device_token is not None 
                and str (_cu .trusted_device_token )==_device_token 
                ):
                    context ["trusted_device_user"]=_user 
            except Exception as _exc :
                logger .debug ("# [TRUSTED DEVICE] Cookie inválida en login: %s",_exc )
        return context 

    def form_valid (self ,form ):
        """
        After a successful login, redirect to trust_device if the device
        is not yet trusted. Otherwise redirect to the dashboard.
        ---
        Tras un login exitoso, redirige a trust_device si el dispositivo
        no es de confianza todavía. En caso contrario redirige al dashboard.
        """
        response =super ().form_valid (form )
        if not self .request .COOKIES .get ("eb_trusted_device",""):
            from django .shortcuts import redirect 
            return redirect ("panel:trust_device")
        return response 


@method_decorator (csrf_exempt ,name ="dispatch")
class TrustDeviceQuickLoginView (View ):
    """
    Handles the quick-login POST from the login page when a trusted-device
    cookie is present. Authenticates the cookie owner without a password
    and redirects to the dashboard.
    Security is provided by the signed cookie (django.core.signing), not CSRF.
    ---
    Gestiona el POST de acceso rápido desde la página de login cuando hay
    cookie de dispositivo de confianza. Autentica al propietario de la cookie
    sin contraseña y redirige al dashboard.
    La seguridad la proporciona la cookie firmada (django.core.signing), no el CSRF.
    """

    def post (self ,request ,*args ,**kwargs ):
        """
        Validates the trusted-device cookie and authenticates the user.
        ---
        Valida la cookie de dispositivo de confianza y autentica al usuario.
        """
        from django .core import signing 
        from django .contrib .auth import get_user_model ,login as auth_login 

        _raw =request .COOKIES .get ("eb_trusted_device","")
        if not _raw :
            return redirect ("panel:login")
        try :
            _payload =signing .loads (_raw ,max_age =365 *24 *3600 )
            _user_id =_payload .get ("uid")
            _device_token =_payload .get ("tok")
            User =get_user_model ()
            _user =User .objects .select_related ("company_user").get (pk =_user_id )
            _cu =getattr (_user ,"company_user",None )
            if (
            _cu is not None 
            and _cu .is_active 
            and not _cu .must_change_password 
            and _cu .trusted_device_token is not None 
            and str (_cu .trusted_device_token )==_device_token 
            ):
                auth_login (
                request ,
                _user ,
                backend ="django.contrib.auth.backends.ModelBackend",
                )
                logger .info (
                "# [TRUSTED DEVICE] Acceso rápido concedido a usuario pk=%s.",
                _user .pk ,
                )
                return redirect ("/panel/")
        except Exception as _exc :
            logger .warning ("# [TRUSTED DEVICE] Cookie inválida en quick-login: %s",_exc )
        return redirect ("panel:login")


class TrustDeviceView (View ):
    """
    Shown after a successful login on an untrusted device.
    GET:  Renders the trust-device question page.
    POST: If 'trust=yes', generates a UUID4 token, persists it in
          CompanyUser.trusted_device_token and emits the signed HttpOnly
          cookie 'eb_trusted_device' (max_age=365 days).
          If 'trust=no', redirects to dashboard without emitting the cookie.
    ---
    Se muestra tras un login exitoso en un dispositivo no conocido.
    GET:  Renderiza la página de pregunta de confianza de dispositivo.
    POST: Si 'trust=yes', genera un UUID4, lo persiste en
          CompanyUser.trusted_device_token y emite la cookie HttpOnly firmada
          'eb_trusted_device' (max_age=365 días).
          Si 'trust=no', redirige al dashboard sin emitir la cookie.
    """

    template_name ="panel/trust_device.html"

    def get (self ,request ,*args ,**kwargs ):
        """
        Renders the trust-device question page.
        ---
        Renderiza la página de pregunta de confianza de dispositivo.
        """
        if not request .user .is_authenticated :
            return redirect ("panel:login")
        cu =request .user .company_user 
        return render (request ,self .template_name ,{
        "company":cu .company ,
        "company_user":cu ,
        "active_nav":"",
        })

    def post (self ,request ,*args ,**kwargs ):
        """
        Processes the trust-device decision.
        'trust=yes' -> emit cookie and redirect to dashboard.
        'trust=no'  -> redirect to dashboard without cookie.
        ---
        Procesa la decisión de confianza de dispositivo.
        'trust=yes' -> emite cookie y redirige al dashboard.
        'trust=no'  -> redirige al dashboard sin cookie.
        """
        import uuid as _uuid 
        from django .core import signing as _signing 

        response =redirect ("/panel/")
        if request .POST .get ("trust")=="yes":
            cu =request .user .company_user 
            _token =_uuid .uuid4 ()
            cu .trusted_device_token =_token 
            cu .save (update_fields =["trusted_device_token"])
            _payload ={"uid":request .user .pk ,"tok":str (_token )}
            _signed =_signing .dumps (_payload )
            response .set_cookie (
            key ="eb_trusted_device",
            value =_signed ,
            max_age =365 *24 *3600 ,
            httponly =True ,
            secure =True ,
            samesite ="Lax",
            )
            logger .info (
            "# [TRUSTED DEVICE] Cookie emitida para usuario pk=%s.",
            request .user .pk ,
            )
        return response 


class TrustDeviceToggleView (CompanyUserRequiredMixin ,View ):
    """
    Toggles the trusted-device status of the current device from the profile page.
    POST 'action=trust'   -> generates token + emits cookie.
    POST 'action=revoke'  -> clears token + deletes cookie.
    ---
    Alterna el estado de dispositivo de confianza del dispositivo actual desde el perfil.
    POST 'action=trust'   -> genera token + emite cookie.
    POST 'action=revoke'  -> limpia token + borra cookie.
    """

    def post (self ,request ,*args ,**kwargs ):
        """
        Processes trust/revoke action.
        ---
        Procesa la acción trust/revoke.
        """
        import uuid as _uuid 
        from django .core import signing as _signing 

        cu =request .user .company_user 
        action =request .POST .get ("action","")
        response =redirect ("panel:own_profile")

        if action =="trust":
            _token =_uuid .uuid4 ()
            cu .trusted_device_token =_token 
            cu .save (update_fields =["trusted_device_token"])
            _payload ={"uid":request .user .pk ,"tok":str (_token )}
            _signed =_signing .dumps (_payload )
            response .set_cookie (
            key ="eb_trusted_device",
            value =_signed ,
            max_age =365 *24 *3600 ,
            httponly =True ,
            secure =True ,
            samesite ="Lax",
            )
            django_messages .success (request ,"Este dispositivo ha sido marcado como de confianza.")
            logger .info (
            "# [TRUSTED DEVICE] Cookie emitida desde perfil para usuario pk=%s.",
            request .user .pk ,
            )

        elif action =="revoke":
            cu .trusted_device_token =None 
            cu .save (update_fields =["trusted_device_token"])
            response .delete_cookie ("eb_trusted_device")
            django_messages .success (request ,"La confianza de este dispositivo ha sido revocada.")
            logger .info (
            "# [TRUSTED DEVICE] Cookie revocada desde perfil para usuario pk=%s.",
            request .user .pk ,
            )

        return response 


class PresenceStatusUpdateView (CompanyUserRequiredMixin ,View ):
    """
    View for displaying and updating the authenticated user's own presence status.
    GET:  Renders the presence status form pre-populated with the current active state.
    POST: Closes the current active PresenceStatus and creates a new one.
    ---
    Vista para mostrar y actualizar el estado de presencia del usuario autenticado.
    GET:  Renderiza el formulario de presencia prerellenado con el estado activo actual.
    POST: Cierra el PresenceStatus activo actual y crea uno nuevo.
    """

    template_name ="panel/presence/status.html"

    def _get_active_presence (self ,company_user ):
        """
        Returns the current active PresenceStatus for the given CompanyUser, or None.
        ---
        Retorna el PresenceStatus activo actual para el CompanyUser dado, o None.
        """
        return PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first ()

    def get (self ,request ,*args ,**kwargs ):
        """
        Renders the presence status page with the current active status and the form.
        ---
        Renderiza la página de estado de presencia con el estado activo actual y el formulario.
        """
        from django .shortcuts import render 
        company_user =request .user .company_user 
        active_presence =self ._get_active_presence (company_user )
        form =PresenceStatusForm (instance =active_presence )

        return render (request ,self .template_name ,{
        "company":company_user .company ,
        "company_user":company_user ,
        "own_presence":active_presence ,
        "active_nav":"presence",
        "form":form ,
        })

    def post (self ,request ,*args ,**kwargs ):
        """
        Closes the current active PresenceStatus and creates a new one with
        the submitted status and optional ends_at.
        ---
        Cierra el PresenceStatus activo actual y crea uno nuevo con el estado
        enviado y el ends_at opcional.
        """
        from django .shortcuts import render 
        from django .contrib import messages as django_messages 

        company_user =request .user .company_user 
        form =PresenceStatusForm (request .POST )

        if form .is_valid ():


            PresenceStatus .objects .filter (
            company_user =company_user ,
            starts_at__lte =now (),
            ).filter (
            Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
            ).update (ends_at =now ())



            new_status =form .save (commit =False )
            new_status .company_user =company_user 
            new_status .save ()

            django_messages .success (
            request ,
            f"Estado de presencia actualizado a: {new_status.get_status_display()}"
            )
            return redirect ("panel:presence_status")



        active_presence =self ._get_active_presence (company_user )
        return render (request ,self .template_name ,{
        "company":company_user .company ,
        "company_user":company_user ,
        "own_presence":active_presence ,
        "active_nav":"presence",
        "form":form ,
        })


class PanelLogoutView (LogoutView ):
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

    http_method_names =['get','post','head','options']
    next_page ="/panel/login/"

    def get (self ,request ,*args ,**kwargs ):
        """
        Handles GET logout requests from the panel sidebar link.
        Delegates to post() to execute standard Django session termination.
        ---
        Gestiona las peticiones GET de logout desde el enlace del sidebar del panel.
        Delega en post() para ejecutar la terminación de sesión estándar de Django.
        """
        return self .post (request ,*args ,**kwargs )


class PanelDashboardView (CompanyUserRequiredMixin ,TemplateView ):
    """
    Main dashboard view for authenticated CompanyUser accounts.
    Provides a summary of the company's active sections, total contacts,
    and the current presence status of the authenticated user.
    ---
    Vista principal del dashboard para cuentas CompanyUser autenticadas.
    Proporciona un resumen de las secciones activas de la empresa, el total
    de contactos y el estado de presencia actual del usuario autenticado.
    """

    template_name ="panel/dashboard.html"

    def dispatch (self ,request ,*args ,**kwargs ):
        """
        Redirect WORKSHOP users to the operator dashboard immediately.
        ADMIN and OPERATOR users proceed to the standard dashboard.
        ---
        Redirige a los usuarios WORKSHOP al dashboard de operario inmediatamente.
        Los usuarios ADMIN y OPERATOR continúan al dashboard estándar.
        """


        response =super ().dispatch (request ,*args ,**kwargs )
        if not request .user .is_authenticated :
            return response 

        company_user =getattr (request .user ,"company_user",None )
        if company_user and company_user .role ==CompanyUser .ROLE_WORKSHOP :
            return redirect ("/panel/operator/")

        return response 

    def get_context_data (self ,**kwargs ):
        """
        Build dashboard context with company summary and own presence status.
        ---
        Construye el contexto del dashboard con el resumen de empresa y el
        estado de presencia propio.
        """
        context =super ().get_context_data (**kwargs )



        company_user =self .request .user .company_user 
        company =company_user .company 



        active_sections =Section .objects .filter (
        company =company ,
        is_active =True ,
        )



        total_contacts =Contact .objects .filter (company =company ).count ()



        from django .utils .timezone import now 
        from django .db .models import Q 

        own_presence =PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first ()

        context ["company"]=company 
        context ["company_user"]=company_user 
        context ["active_sections"]=active_sections 
        context ["active_sections_count"]=active_sections .count ()
        context ["total_contacts"]=total_contacts 
        context ["own_presence"]=own_presence 
        context ["active_nav"]="dashboard"

        return context 


class PanelPasswordChangeView (CompanyUserRequiredMixin ,View ):
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

    template_name ="panel/password/change.html"

    def _get_own_presence (self ,company_user ):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        return PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first ()

    def _build_form (self ,request ,data =None ):
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
        cu =request .user .company_user 
        if cu .must_change_password :


            return PanelSetPasswordForm (user =request .user ,data =data )


        return PanelPasswordChangeForm (user =request .user ,data =data )

    def _get_context (self ,request ,form =None ):
        """
        Builds template context including is_forced flag for UI messaging.
        When is_forced=True the template hides the old_password block, since
        PanelSetPasswordForm does not expose that field.
        ---
        Construye el contexto de plantilla incluyendo el flag is_forced para la UI.
        Cuando is_forced=True el template oculta el bloque old_password, ya que
        PanelSetPasswordForm no expone ese campo.
        """
        cu =request .user .company_user 
        return {
        "company":cu .company ,
        "company_user":cu ,
        "own_presence":self ._get_own_presence (cu ),
        "active_nav":"",
        "form":form or self ._build_form (request ),
        "is_forced":cu .must_change_password ,
        }

    def get (self ,request ,*args ,**kwargs ):
        """
        Renders the password change form (forced or voluntary depending on context).
        ---
        Renderiza el formulario de cambio de contraseña (forzado o voluntario
        según el contexto).
        """
        return render (request ,self .template_name ,self ._get_context (request ))

    def post (self ,request ,*args ,**kwargs ):
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
        form =self ._build_form (request ,data =request .POST )
        if form .is_valid ():
            form .save ()
            update_session_auth_hash (request ,form .user )
            cu =request .user .company_user 
            _was_forced =cu .must_change_password 
            if cu .must_change_password :
                cu .must_change_password =False 
                cu .save (update_fields =["must_change_password"])
            django_messages .success (request ,"Contraseña actualizada correctamente.")









            response =redirect ("/panel/")
            if _was_forced :
                import uuid as _uuid 
                from django .core import signing as _signing 
                _token =_uuid .uuid4 ()
                cu .trusted_device_token =_token 
                cu .save (update_fields =["trusted_device_token"])
                _payload ={"uid":request .user .pk ,"tok":str (_token )}
                _signed =_signing .dumps (_payload )
                _max_age =365 *24 *3600 
                response .set_cookie (
                key ="eb_trusted_device",
                value =_signed ,
                max_age =_max_age ,
                httponly =True ,
                secure =True ,
                samesite ="Lax",
                )
                logger .info (
                "# [TRUSTED DEVICE] Cookie emitida para usuario pk=%s — "
                "token=%s.",
                request .user .pk ,
                _token ,
                )
            return response 
        return render (request ,self .template_name ,self ._get_context (request ,form ))








class WhatsAppTemplateListView (AdminRoleRequiredMixin ,ListView ):
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

    model =WhatsAppTemplate 
    template_name ="panel/whatsapp/template_list.html"
    context_object_name ="templates"

    def get_queryset (self ):
        """
        Returns active WhatsAppTemplate records scoped to the authenticated
        user's company, ordered alphabetically by name.
        ---
        Retorna los registros WhatsAppTemplate activos acotados a la empresa
        del usuario autenticado, ordenados alfabéticamente por nombre.
        """
        return WhatsAppTemplate .objects .filter (
        company =self .request .user .company_user .company ,
        is_active =True ,
        ).order_by ("name")

    def get_context_data (self ,**kwargs ):
        """
        Adds company, company_user and own_presence to the template context,
        following the same pattern as all other panel ListViews.
        ---
        Añade company, company_user y own_presence al contexto de la plantilla,
        siguiendo el mismo patrón que el resto de ListViews del panel.
        """
        context =super ().get_context_data (**kwargs )
        context ["company"]=self .request .user .company_user .company 
        context ["company_user"]=self .request .user .company_user 
        context ["own_presence"]=self ._get_own_presence ()
        context ["active_nav"]="whatsapp_templates"
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







class WhatsAppActiveSessionListView (AdminRoleRequiredMixin ,ListView ):
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

    model =WhatsAppSession 
    template_name ="panel/whatsapp/active_session_list.html"
    context_object_name ="active_sessions"

    def get_queryset (self ):
        """
        Returns active WhatsAppSession records scoped to the authenticated
        user's company, with last inbound message prefetched for excerpt display.
        ---
        Retorna los registros WhatsAppSession activos acotados a la empresa
        del usuario autenticado, con el ultimo mensaje entrante precargado
        para mostrar el extracto.
        """
        from whatsapp .models import WhatsAppMessage 
        return (
        WhatsAppSession .objects .filter (
        company =self .request .user .company_user .company ,
        is_active =True ,
        )
        .prefetch_related (
        Prefetch (
        "messages",
        queryset =WhatsAppMessage .objects .filter (
        direction ="IN"
        ).order_by ("-timestamp")[:1 ],
        to_attr ="last_inbound",
        )
        )
        .order_by ("-last_message_at")
        )

    def get_context_data (self ,**kwargs ):
        """
        Adds company, company_user and own_presence to the template context.
        ---
        Anade company, company_user y own_presence al contexto de la plantilla.
        """
        context =super ().get_context_data (**kwargs )
        context ["company"]=self .request .user .company_user .company 
        context ["company_user"]=self .request .user .company_user 
        context ["own_presence"]=self ._get_own_presence ()
        context ["active_nav"]="whatsapp_sessions"
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


class OwnProfileView (CompanyUserRequiredMixin ,View ):
    """
    Allows any authenticated CompanyUser to view and edit their own profile.
    Currently exposes only the alias field (chat IRC nick).
    Alias uniqueness within the company is enforced by OwnProfileForm.

    GET  — renders the profile form pre-populated with the current alias.
    POST — validates and saves the new alias, redirects back to the form.

    URL: GET/POST /panel/profile/
    ---
    Permite a cualquier CompanyUser autenticado ver y editar su propio perfil.
    Actualmente expone únicamente el campo alias (nick de chat IRC).
    La unicidad del alias dentro de la empresa la impone OwnProfileForm.

    GET  — renderiza el formulario de perfil prerellenado con el alias actual.
    POST — valida y guarda el nuevo alias, redirige de vuelta al formulario.

    URL: GET/POST /panel/profile/
    """

    template_name ="panel/profile/own_profile.html"

    def _get_own_presence (self ,company_user ):
        """
        Returns the current active PresenceStatus for the authenticated user.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado.
        """
        return PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first ()

    def get (self ,request ,*args ,**kwargs ):
        """
        Renders the own-profile form pre-populated with the current alias.
        ---
        Renderiza el formulario de perfil propio prerellenado con el alias actual.
        """
        from panel .forms import OwnProfileForm 
        company_user =request .user .company_user 
        form =OwnProfileForm (company_user =company_user )
        return render (request ,self .template_name ,{
        "form":form ,
        "company_user":company_user ,
        "own_presence":self ._get_own_presence (company_user ),
        "active_nav":"own_profile",
        })






class CompanySettingsView (AdminRoleRequiredMixin ,View ):
    """
    Allows ADMIN users to edit the company-level text fields
    operation_bases and labor_calendar on the Company model.
    GET: renders the settings form pre-populated with the current values.
    POST: validates and saves both fields, then redirects back with a
    success message.
    ---
    Permite a los usuarios ADMIN editar los campos de texto de nivel empresa
    operation_bases y labor_calendar del modelo Company.
    GET: renderiza el formulario de configuración con los valores actuales.
    POST: valida y guarda ambos campos, luego redirige con mensaje de éxito.
    """

    template_name ="panel/company/settings.html"

    def get (self ,request ):
        """
        Render the company settings page with bases, schedules and night
        shift fields. The obsolete operation_bases and labor_calendar text
        fields have been replaced by live querysets from the database.
        ---
        Renderiza la página de configuración de empresa con bases, horarios
        y franja nocturna. Los campos de texto obsoletos operation_bases y
        labor_calendar han sido sustituidos por querysets en vivo desde BD.
        """
        import json as _json 
        from ivr_config .models import Company ,WorkdaySchedule 
        from budgets .models import Base 
        company_user =request .user .company_user 
        company =company_user .company 
        bases =Base .objects .filter (company =company ).order_by ("name")


        bases_data =[]
        for base in bases :
            holiday_count =0 
            if base .labor_calendar :
                try :
                    holiday_count =len (_json .loads (base .labor_calendar ))
                except (ValueError ,TypeError ):
                    holiday_count =0 
            bases_data .append ({
            "base":base ,
            "holiday_count":holiday_count ,
            })
        schedules =WorkdaySchedule .objects .filter (
        company =company 
        ).order_by ("label")
        ctx ={
        "company":company ,
        "company_user":company_user ,
        "own_presence":PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first (),
        "active_nav":"company_settings",
        "bases_data":bases_data ,
        "schedules":schedules ,
        }
        return render (request ,self .template_name ,ctx )

    def post (self ,request ):
        """
        Save night_start and night_end fields to the Company instance.
        The obsolete operation_bases and labor_calendar fields are no longer
        persisted from this form — they are managed via Base model and the
        sync_base_calendars command.
        ---
        Guarda los campos night_start y night_end en la instancia Company.
        Los campos obsoletos operation_bases y labor_calendar ya no se
        persisten desde este formulario — se gestionan via modelo Base y
        el comando sync_base_calendars.
        """
        import datetime as _dt 
        company_user =request .user .company_user 
        company =company_user .company 



        night_start_raw =request .POST .get ("night_start","").strip ()
        night_end_raw =request .POST .get ("night_end","").strip ()
        try :
            company .night_start =(
            _dt .time .fromisoformat (night_start_raw )
            if night_start_raw else _dt .time (22 ,0 )
            )
        except ValueError :
            company .night_start =_dt .time (22 ,0 )
        try :
            company .night_end =(
            _dt .time .fromisoformat (night_end_raw )
            if night_end_raw else _dt .time (6 ,0 )
            )
        except ValueError :
            company .night_end =_dt .time (6 ,0 )

        company .save (update_fields =[
        "night_start",
        "night_end",
        ])
        django_messages .success (request ,"Configuración de empresa guardada correctamente.")
        return redirect ("panel:company_settings")

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

