from django.contrib import messages as django_messages
from django.views.generic import TemplateView, View
from django.shortcuts import redirect, render
from django.db import models as django_models
from django.db.models import Q, Prefetch
from django.utils.timezone import now

from panel.mixins import WorkshopRequiredMixin, SupervisorAccessMixin
from ivr_config.models import (
    PresenceStatus,
    CompanyUser,
    Contact,
)
from work_order_processor.models import (
    WorkOrder,
    WorkOrderEntry,
    WorkOrderEntryLine,
)
from work_order_processor.services import find_cached_classification
from work_order_processor.tasks import classify_fault_line
import logging

logger = logging.getLogger(__name__)

class OperatorDashboardView (WorkshopRequiredMixin ,TemplateView ):
    """
    Landing view for CompanyUsers with the WORKSHOP role.
    Displays a selector with the two remaining work-order entry paths:
    Form (structured web form) and Upload (photo or PDF with Gemini Vision
    extraction). Via B (STT) was removed in Hito 7 / S023.
    Accessible to WORKSHOP and ADMIN roles (WorkshopRequiredMixin).
    ---
    Vista de aterrizaje para CompanyUsers con rol WORKSHOP.
    Muestra un selector con las dos vías de entrada de partes disponibles:
    Form (formulario web estructurado) y Upload (foto o PDF con extracción
    Gemini Vision). La Vía B (STT) fue eliminada en Hito 7 / S023.
    Accesible para los roles WORKSHOP y ADMIN (WorkshopRequiredMixin).
    """

    template_name ="panel/operator/dashboard.html"

    def get_context_data (self ,**kwargs ):
        """
        Build context with company, company_user and own_presence for the operator dashboard.
        Clears any residual error messages left in the session by access-control mixins
        when the authenticated user has the WORKSHOP role — these messages are artefacts
        of prior failed access attempts and are not meaningful to the operator.
        ---
        Construye el contexto con company, company_user y own_presence para el dashboard
        del operario de taller.
        Limpia los mensajes de error residuales dejados en la sesión por los mixins de
        control de acceso cuando el usuario autenticado tiene rol WORKSHOP — estos mensajes
        son artefactos de intentos de acceso previos fallidos y no son significativos
        para el operario.
        """
        context =super ().get_context_data (**kwargs )



        company_user =self .request .user .company_user 










        if company_user .role =="WORKSHOP":
            from django .contrib .messages import get_messages as _get_messages 
            storage =_get_messages (self .request )
            storage .used =True 
        company =company_user .company 



        own_presence =PresenceStatus .objects .filter (
        company_user =company_user ,
        starts_at__lte =now (),
        ).filter (
        Q (ends_at__isnull =True )|Q (ends_at__gt =now ())
        ).order_by ("-starts_at").first ()

        context ["company"]=company 
        context ["company_user"]=company_user 
        context ["own_presence"]=own_presence 
        context ["active_nav"]="operator_dashboard"

        return context 


class WorkerSignupView (View ):
    """
    Worker self-registration view — DEACTIVATED (H13 redesign).
    Registration is now exclusively managed by Supervisors from the panel.
    Both GET and POST redirect to login with an informative message.
    The URL is preserved to avoid breaking existing links.
    ---
    Vista de auto-registro de operarios — DESACTIVADA (rediseño H13).
    El registro es ahora gestionado exclusivamente por los Supervisores
    desde el panel. GET y POST redirigen al login con un mensaje informativo.
    La URL se preserva para no romper enlaces existentes.
    """

    def get (self ,request ,*args ,**kwargs ):
        """
        Redirects to login with an informative message.
        ---
        Redirige al login con un mensaje informativo.
        """
        django_messages .info (
        request ,
        "El registro de trabajadores lo gestiona el supervisor desde el panel.",
        )
        return redirect ("/panel/login/")

    def post (self ,request ,*args ,**kwargs ):
        """
        Redirects to login with an informative message.
        ---
        Redirige al login con un mensaje informativo.
        """
        django_messages .info (
        request ,
        "El registro de trabajadores lo gestiona el supervisor desde el panel.",
        )
        return redirect ("/panel/login/")


class WorkshopAssetAutocompleteView (WorkshopRequiredMixin ,View ):
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

    def get (self ,request ,*args ,**kwargs ):
        """
        Returns a filtered list of active MachineAsset records as JSON.
        ---
        Devuelve una lista filtrada de registros MachineAsset activos como JSON.
        """
        from django .http import JsonResponse 
        from fleet .models import MachineAsset 

        try :
            company =request .user .company_user .company 
        except AttributeError :
            return JsonResponse ({"error":"Sin perfil de empresa."},status =403 )

        q =request .GET .get ("q","").strip ()
        qs =MachineAsset .objects .filter (company =company ,is_active =True )

        if q :


            qs =qs .filter (
            django_models .Q (code__icontains =q )|
            django_models .Q (brand_model__icontains =q )|
            django_models .Q (plate__icontains =q )
            )

        assets =list (
        qs .order_by ("code")
        .values ("code","brand_model","plate")[:20 ]
        )
        return JsonResponse ({"assets":assets })

class WorkOrderEntryUploadView (WorkshopRequiredMixin ,View ):
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

    template_name ="panel/operator/upload_entry.html"

    def _get_context (self ,request ,error =None ):
        """
        Builds base template context for the upload view.
        ---
        Construye el contexto base para la vista de subida.
        """
        cu =request .user .company_user 
        return {
        "company":cu .company ,
        "company_user":cu ,
        "active_nav":"operator_dashboard",
        "error":error ,
        }

    def get (self ,request ,*args ,**kwargs ):
        """
        Renders the upload form.
        ---
        Renderiza el formulario de subida.
        """
        return render (request ,self .template_name ,self ._get_context (request ))

    def post (self ,request ,*args ,**kwargs ):
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
        from work_order_processor .services import extract_work_order_page_full 

        uploaded_file =request .FILES .get ("work_order_file")
        if not uploaded_file :
            return render (
            request ,self .template_name ,
            self ._get_context (request ,error ="Debes seleccionar un archivo.")
            )

        file_bytes =uploaded_file .read ()
        content_type =uploaded_file .content_type or ""

        try :


            if "pdf"in content_type or uploaded_file .name .lower ().endswith (".pdf"):


                pages =convert_from_bytes (file_bytes ,dpi =200 ,first_page =1 ,last_page =1 )
                if not pages :
                    raise ValueError ("# No se pudieron extraer páginas del PDF.")
                buf =io .BytesIO ()
                pages [0 ].save (buf ,format ="PNG")
                image_bytes =buf .getvalue ()
            else :


                img =Image .open (io .BytesIO (file_bytes )).convert ("RGB")
                buf =io .BytesIO ()
                img .save (buf ,format ="PNG")
                image_bytes =buf .getvalue ()

        except Exception as exc :
            logger .error (
            "# [Upload] Error al rasterizar archivo: %s",exc ,exc_info =True 
            )
            return render (
            request ,self .template_name ,
            self ._get_context (
            request ,
            error =(
            "No se pudo procesar el archivo. "
            "Asegúrate de que es una imagen o PDF válido."
            ),
            )
            )



        extraction =extract_work_order_page_full (image_bytes )

        if extraction .get ("extraction_confidence")=="FAILED":
            return render (
            request ,self .template_name ,
            self ._get_context (
            request ,
            error =(
            "Gemini no pudo extraer datos del archivo. "
            "Comprueba que la imagen sea legible y corresponda "
            "a un parte de trabajo."
            ),
            )
            )



        request .session ["operator_upload_extraction"]=extraction 
        request .session .modified =True 

        logger .info (
        "# [Upload] Extracción completada. Confianza: %s | "
        "Entradas: %d | Repuestos: %d. Redirigiendo a confirmación.",
        extraction .get ("extraction_confidence"),
        len (extraction .get ("entradas",[])),
        len (extraction .get ("repuestos",[])),
        )

        return redirect ("/panel/operator/confirm/")











def _resolve_operator_schedule (cu ,company ):
    """
    Resolves the effective WorkdaySchedule for a CompanyUser following
    the Gate 4 priority chain:
      0. If cu.is_intensive_override=True, returns the company's intensive
         WorkdaySchedule (is_intensive=True) when one exists. Falls through
         to the normal chain if no intensive schedule is configured.
      1. CompanyUser.workday_schedule (individual assignment).
      2. First active Section of the operator's Contact that has a
         workday_schedule assigned.
      3. Company-level default WorkdaySchedule (is_default=True).
      4. None — no schedule available.
    Returns the resolved WorkdaySchedule instance or None.
    ---
    Resuelve el WorkdaySchedule efectivo para un CompanyUser siguiendo
    la cadena de prioridad de Gate 4:
      0. Si cu.is_intensive_override=True, devuelve el WorkdaySchedule
         intensivo de la empresa (is_intensive=True) si existe. Si no
         existe horario intensivo configurado, continua con la cadena normal.
      1. CompanyUser.workday_schedule (asignacion individual).
      2. Primera Section activa del Contact del operario que tenga
         workday_schedule asignado.
      3. WorkdaySchedule por defecto de empresa (is_default=True).
      4. None — no hay horario disponible.
    Devuelve la instancia WorkdaySchedule resuelta o None.
    """
    from ivr_config .models import WorkdaySchedule as _WDS_R 
    from ivr_config .models import Contact as _Contact_R 

    if getattr (cu ,"is_intensive_override",False ):
        _intensive =_WDS_R .objects .filter (
            company =company ,
            is_intensive =True ,
        ).first ()
        if _intensive is not None :
            return _intensive 

    # Gate 1 — individual schedule assignment.
    # Only apply if the assigned schedule is coherent with
    # is_intensive_override:
    #   - override=True  + intensive schedule  -> Gate 0 already
    #     returned; reaching here means no intensive schedule
    #     exists, so Gate 1 applies normally.
    #   - override=False + intensive schedule  -> incoherent;
    #     skip Gate 1 and fall through to Gate 2/3.
    #   - override=False + non-intensive schedule -> coherent;
    #     Gate 1 applies normally.
    # ---
    # Gate 1 — asignacion individual de horario.
    # Solo aplica si el horario asignado es coherente con
    # is_intensive_override:
    #   - override=True  + horario intensivo  -> Gate 0 ya retorno;
    #     llegar aqui significa que no existe horario intensivo,
    #     Gate 1 aplica normalmente.
    #   - override=False + horario intensivo  -> incoherente;
    #     se ignora Gate 1 y se continua a Gate 2/3.
    #   - override=False + horario no intensivo -> coherente;
    #     Gate 1 aplica normalmente.
    if cu.workday_schedule_id:
        _cu_sched = cu.workday_schedule
        _override_active = getattr(cu, 'is_intensive_override', False)
        _sched_is_intensive = getattr(
            _cu_sched, 'is_intensive', False
        )
        _gate1_coherent = not (
            not _override_active and _sched_is_intensive
        )
        if _gate1_coherent:
            return _cu_sched

    contact =(
    _Contact_R .objects 
    .filter (company_user =cu )
    .prefetch_related ("sections__workday_schedule")
    .first ()
    )
    if contact is not None :
        section_schedule =next (
        (
        sec .workday_schedule 
        for sec in contact .sections .filter (
        is_active =True ,workday_schedule__isnull =False 
        ).select_related ("workday_schedule").order_by ("name")
        ),
        None ,
        )
        if section_schedule is not None :
            return section_schedule 

    return _WDS_R .objects .filter (company =company ,is_default =True ).first ()


def _parse_entry_lines_from_post (POST ,company ):
    """
    Parses and resolves work-block entry lines submitted via POST.

    Resolution strategy for machine_asset (two-pass):
      Pass 1 — direct iexact on machine_raw: covers autocomplete selections
               where the field contains the exact asset.code string.
      Pass 2 — iexact on _normalise_machine_code(machine_raw): covers OCR
               and handwritten input where normalisation is required.

    Absence (PERSONAL asset) handling:
      When the selected machine_asset matches the PERSONAL asset code,
      the backend reads entrada_{i}_absence_category from POST, resolves
      the AbsenceCategory, and overrides fault_description with its label.
      If requires_note=True the operator must supply repair_notes (validated
      in Gate 1). The resolved AbsenceCategory instance is stored in the
      'absence_category' key of the dict so that save_blocks and close_order
      can create the synthetic WorkdayGap record.

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

    Gestión de ausencias (activo PERSONAL):
      Cuando el machine_asset seleccionado coincide con el código PERSONAL,
      el backend lee entrada_{i}_absence_category del POST, resuelve la
      AbsenceCategory y sobreescribe fault_description con su label.
      Si requires_note=True el operario debe proporcionar repair_notes
      (validado en Gate 1). La instancia AbsenceCategory resuelta se
      almacena en la clave 'absence_category' del dict para que save_blocks
      y close_order puedan crear el registro WorkdayGap sintético.

    Devuelve una lista de dicts lista para la barrera de integridad y el
    bloque de persistencia atómica.
    """
    import json as _json 
    from datetime import time as _dt_time 
    from fleet .models import MachineAsset 
    from work_order_processor .services import (
    _normalise_machine_code ,
    _compute_delta_hours ,
    )
    from work_order_processor .management .commands .seed_personal_asset import (
    PERSONAL_ASSET_CODE as _PERSONAL_CODE ,
    )

    num_entradas =int (POST .get ("num_entradas","1")or "1")
    entry_lines_data =[]

    for i in range (1 ,num_entradas +1 ):
        pfx =f"entrada_{i}_"
        machine_raw =POST .get (f"{pfx}machine_raw","").strip ()
        desc_averia =POST .get (f"{pfx}fault_description","").strip ()
        repair_notes =POST .get (f"{pfx}repair_notes","").strip ()
        hc_str =POST .get (f"{pfx}hc","").strip ()
        hf_str =POST .get (f"{pfx}hf","").strip ()
        or_val =POST .get (f"{pfx}or_val","").strip ()
        flags_raw =POST .get (f"{pfx}flags","[]")

        def _parse_t (s ):
            """
            Parses HH:MM string into time object, returns None on failure.
            ---
            Parsea cadena HH:MM a objeto time, devuelve None en fallo.
            """
            if not s :
                return None 
            try :
                parts =s .split (":")
                return _dt_time (int (parts [0 ]),int (parts [1 ]))
            except (ValueError ,IndexError ):
                return None 

        hc =_parse_t (hc_str )
        hf =_parse_t (hf_str )

        machine_norm =_normalise_machine_code (machine_raw )
        machine_asset =None 

        if machine_raw :


            try :
                machine_asset =MachineAsset .objects .get (
                code__iexact =machine_raw ,company =company 
                )
            except (MachineAsset .DoesNotExist ,MachineAsset .MultipleObjectsReturned ):
                machine_asset =MachineAsset .objects .filter (
                code__iexact =machine_raw ,company =company 
                ).first ()

        if machine_asset is None and machine_norm :


            try :
                machine_asset =MachineAsset .objects .get (
                code__iexact =machine_norm ,company =company 
                )
            except (MachineAsset .DoesNotExist ,MachineAsset .MultipleObjectsReturned ):
                machine_asset =MachineAsset .objects .filter (
                code__iexact =machine_norm ,company =company 
                ).first ()

        delta_hours =_compute_delta_hours (hc ,hf ,deduct_lunch =False )

        try :
            flags =_json .loads (flags_raw )if flags_raw else []
        except (ValueError ,TypeError ):
            flags =[]





        from decimal import Decimal ,InvalidOperation as _InvalidOp 

        def _parse_decimal (raw_val ):
            """
            Converts a POST string to Decimal or returns None on failure.
            ---
            Convierte una cadena POST a Decimal o devuelve None en caso de fallo.
            """
            v =(raw_val or "").strip ().replace (",",".")
            if not v :
                return None 
            try :
                return Decimal (v )
            except _InvalidOp :
                return None 

        odometer_reading =_parse_decimal (POST .get (f"entrada_{i}_odometer_reading",""))
        engine_hours_reading =_parse_decimal (POST .get (f"entrada_{i}_engine_hours_reading",""))
        crane_hours_reading =_parse_decimal (POST .get (f"entrada_{i}_crane_hours_reading",""))
























        absence_category_obj =None 
        _is_personal_block =(
        machine_asset is not None 
        and machine_asset .code .upper ()==_PERSONAL_CODE .upper ()
        )
        if _is_personal_block :
            _abs_cat_pk_raw =POST .get (f"{pfx}absence_category","").strip ()
            if _abs_cat_pk_raw :
                try :
                    from ivr_config .models import AbsenceCategory as _AbsCatParse 
                    absence_category_obj =_AbsCatParse .objects .get (
                    pk =int (_abs_cat_pk_raw ),
                    company =company ,
                    is_active =True ,
                    )





                    desc_averia =absence_category_obj .label 
                except (ValueError ,TypeError ):
                    logger .warning (
                    "# [_parse_entry_lines] absence_category pk=%r inválido "
                    "para entrada_%d — se omite.",
                    _abs_cat_pk_raw ,i ,
                    )
                except Exception as _abs_exc :
                    logger .warning (
                    "# [_parse_entry_lines] Error resolviendo AbsenceCategory "
                    "pk=%r para entrada_%d: %s",
                    _abs_cat_pk_raw ,i ,_abs_exc ,
                    )

        entry_lines_data .append ({
        "line_number":i ,
        "machine_raw":machine_raw ,
        "machine_norm":machine_norm or "",
        "machine_asset":machine_asset ,
        "fault_description":desc_averia ,
        "repair_notes":repair_notes ,
        "hc":hc ,
        "hf":hf ,
        "or_val":or_val ,
        "delta_hours":delta_hours ,
        "flags":flags ,
        "odometer_reading":odometer_reading ,
        "engine_hours_reading":engine_hours_reading ,
        "crane_hours_reading":crane_hours_reading ,
        "absence_category":absence_category_obj ,
        "is_personal":_is_personal_block ,
        })

    return entry_lines_data 


def _parse_spare_parts_from_post (POST ,company ,entry_lines_data =None ):
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
    from decimal import Decimal ,InvalidOperation 
    from fleet .models import MachineAsset as _MachineAsset 
    from work_order_processor .services import _normalise_machine_code as _norm_code 

    num_repuestos =int (POST .get ("num_repuestos","0")or "0")
    spare_parts_data =[]

    for r in range (1 ,num_repuestos +1 ):
        pfx =f"repuesto_{r}_"
        referencia =POST .get (f"{pfx}referencia","").strip ()
        material =POST .get (f"{pfx}material","").strip ()
        unidades_str =POST .get (f"{pfx}unidades","").strip ()
        origen =POST .get (f"{pfx}origen","WAREHOUSE").strip ()
        proveedor =POST .get (f"{pfx}proveedor","").strip ()






        _cdg_raw =POST .get (f"{pfx}vehiculo_raw","").strip ()
        if _cdg_raw =="__otro__":
            vehiculo_raw =POST .get (f"{pfx}cdg_free","").strip ()
        else :
            vehiculo_raw =_cdg_raw 

        quantity =None 
        if unidades_str :
            try :
                quantity =Decimal (unidades_str .replace (",","."))
            except InvalidOperation :
                quantity =None 

        if origen not in ("SUPPLIER","WAREHOUSE"):
            origen ="WAREHOUSE"









        veh_asset =None 
        cg_incident =False 

        if vehiculo_raw and company is not None :


            try :
                veh_asset =_MachineAsset .objects .get (
                code__iexact =vehiculo_raw ,company =company 
                )
            except (_MachineAsset .DoesNotExist ,_MachineAsset .MultipleObjectsReturned ):
                veh_asset =_MachineAsset .objects .filter (
                code__iexact =vehiculo_raw ,company =company 
                ).first ()

            if veh_asset is None :


                norm =_norm_code (vehiculo_raw )
                if norm :
                    try :
                        veh_asset =_MachineAsset .objects .get (
                        code__iexact =norm ,company =company 
                        )
                    except (_MachineAsset .DoesNotExist ,_MachineAsset .MultipleObjectsReturned ):
                        veh_asset =_MachineAsset .objects .filter (
                        code__iexact =norm ,company =company 
                        ).first ()

        if veh_asset is None and vehiculo_raw :


            cg_incident =True 

        spare_parts_data .append ({
        "line_number":r ,
        "referencia":referencia ,
        "vehiculo_raw":vehiculo_raw ,
        "vehicle_asset":veh_asset ,
        "material":material ,
        "quantity":quantity ,
        "source":origen ,
        "supplier":proveedor if origen =="SUPPLIER"else "",
        "flags":[],
        "cg_incident":cg_incident ,
        })

    return spare_parts_data 

class WorkOrderEntryConfirmView (WorkshopRequiredMixin ,View ):
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

    template_name ="panel/operator/confirm_entry.html"

    def _get_company_user (self ,request ):
        """
        Returns the CompanyUser for the authenticated request user.
        ---
        Devuelve el CompanyUser del usuario autenticado en la solicitud.
        """
        return request .user .company_user 

    def _get_context_base (self ,request ):
        """
        Returns the base template context with company and navigation data.
        ---
        Devuelve el contexto base con empresa y datos de navegación.
        """
        cu =self ._get_company_user (request )
        return {
        "company":cu .company ,
        "company_user":cu ,
        "active_nav":"operator_dashboard",
        }

    def _resolve_machine (self ,company ,raw_code ):
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
        from work_order_processor .services import _normalise_machine_code 
        from fleet .models import MachineAsset 

        if not raw_code :
            return None 
        norm =_normalise_machine_code (raw_code )
        if not norm :
            return None 
        try :
            return MachineAsset .objects .get (code__iexact =norm ,company =company )
        except MachineAsset .DoesNotExist :
            return None 
        except MachineAsset .MultipleObjectsReturned :
            return MachineAsset .objects .filter (
            code__iexact =norm ,company =company 
            ).first ()

    def get (self ,request ,*args ,**kwargs ):
        """
        Renders the confirmation form using extraction data from the session.
        Redirects to the upload view if the session contains no extraction data.
        ---
        Renderiza el formulario de confirmación usando los datos de extracción
        de la sesión. Redirige a la vista de subida si la sesión no contiene
        datos de extracción.
        """
        from fleet .models import MachineAsset 

        extraction =request .session .get ("operator_upload_extraction")
        if not extraction :
            logger .warning (
            "# [Confirm] No hay datos de extracción en sesión. "
            "Redirigiendo a la vista de subida."
            )
            return redirect ("/panel/operator/upload/")

        cu =self ._get_company_user (request )
        company =cu .company 



        entradas_enriched =[]
        for idx ,entrada in enumerate (extraction .get ("entradas",[]),start =1 ):
            raw_code =entrada .get ("machine_raw")or ""
            machine_asset =self ._resolve_machine (company ,raw_code )
            entradas_enriched .append ({
            "idx":idx ,
            "machine_raw":raw_code ,
            "machine_asset":machine_asset ,
            "fault_description":entrada .get ("fault_description")or "",
            "repair_notes":entrada .get ("repair_notes")or "",
            "hc":entrada .get ("hc")or "",
            "hf":entrada .get ("hf")or "",
            "or_val":entrada .get ("or_val")or "",
            "flags":entrada .get ("flags")or [],
            })



        repuestos_enriched =[]
        for ridx ,rep in enumerate (extraction .get ("repuestos",[]),start =1 ):
            veh_raw =rep .get ("vehiculo_raw")or ""
            vehicle_asset =self ._resolve_machine (company ,veh_raw )
            repuestos_enriched .append ({
            "ridx":ridx ,
            "referencia":rep .get ("referencia")or "",
            "vehiculo_raw":veh_raw ,
            "vehicle_asset":vehicle_asset ,
            "material":rep .get ("material")or "",
            "unidades":rep .get ("unidades"),
            "origen":rep .get ("origen")or "WAREHOUSE",
            "proveedor":rep .get ("proveedor")or "",
            "flags":rep .get ("flags")or [],
            })



        assets =list (
        MachineAsset .objects .filter (company =company ,is_active =True )
        .order_by ("code")
        .values ("code","brand_model")
        )

        _min_date_get =_get_min_allowed_date (cu )
        context =self ._get_context_base (request )
        context .update ({
        "extraction":extraction ,
        "fecha":extraction .get ("fecha")or "",
        "uncertain_date":extraction .get ("uncertain_date",False ),
        "confidence":extraction .get ("extraction_confidence",""),
        "entradas_enriched":entradas_enriched ,
        "repuestos_enriched":repuestos_enriched ,
        "assets":assets ,
        "num_entradas":len (entradas_enriched ),
        "num_repuestos":len (repuestos_enriched ),
        "min_date":_min_date_get .isoformat ()if _min_date_get else "",
        })
        return render (request ,self .template_name ,context )

    def post (self ,request ,*args ,**kwargs ):
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
        from datetime import date ,time as dt_time 
        from decimal import Decimal ,InvalidOperation 
        from django .db import transaction 
        from django .utils import timezone 
        from fleet .models import MachineAsset 
        from work_order_processor .models import (
        WorkOrder ,WorkOrderEntry ,WorkOrderEntryLine ,SparePartLine ,
        )
        from work_order_processor .services import (
        generate_work_order_excel ,
        _normalise_machine_code ,
        _compute_delta_hours ,
        )

        cu =self ._get_company_user (request )
        company =cu .company 
        POST =request .POST 















        _gate0_fecha_str =POST .get ("fecha","").strip ()
        _gate0_work_date =None 
        if _gate0_fecha_str :
            from datetime import datetime as _dt0 
            for _fmt0 in ("%d/%m/%Y","%Y-%m-%d"):
                try :
                    _gate0_work_date =_dt0 .strptime (_gate0_fecha_str ,_fmt0 ).date ()
                    break 
                except ValueError :
                    continue 

        if _gate0_work_date is not None :



            _min_date_c =_get_min_allowed_date (cu )
            if _min_date_c is not None and _gate0_work_date <_min_date_c :
                from datetime import timedelta as _td_c 
                _last_rev_c =_min_date_c -_td_c (days =1 )
                context =self ._get_context_base (request )
                context .update ({
                "error":(
                f"No puedes introducir un parte con fecha "
                f"{_gate0_work_date.strftime('%d/%m/%Y')}. "
                f"El ultimo parte revisado es del "
                f"{_last_rev_c.strftime('%d/%m/%Y')} y ya ha sido auditado. "
                f"La fecha minima permitida es "
                f"{_min_date_c.strftime('%d/%m/%Y')}."
                ),
                "fecha":_gate0_fecha_str ,
                "uncertain_date":False ,
                "confidence":"",
                "entradas_enriched":[],
                "repuestos_enriched":[],
                "num_entradas":0 ,
                "num_repuestos":0 ,
                "min_date":_min_date_c .isoformat (),
                })
                return render (request ,self .template_name ,context )

            from django .urls import reverse as _rev0 
            _existing_entry0 =WorkOrderEntry .objects .filter (
            work_order__company =company ,
            work_order__uploaded_by =cu ,
            work_order__source__in =[
            WorkOrder .Source .DIGITAL ,
            WorkOrder .Source .GENERATED ,
            ],
            work_order__reviewed =False ,
            work_date =_gate0_work_date ,
            ).select_related ("work_order").first ()

            if _existing_entry0 is not None :


                _gate0_lines =_parse_entry_lines_from_post (POST ,company )
                _gate0_spare =_parse_spare_parts_from_post (
                POST ,company ,entry_lines_data =_gate0_lines 
                )
                request .session ["pending_merge_lines"]=_serialize_pending_lines (
                _gate0_lines ,_gate0_spare ,_gate0_work_date 
                )
                return redirect (
                _rev0 (
                "panel:operator_merge",
                kwargs ={"entry_pk":_existing_entry0 .pk },
                )
                )





        fecha_str =POST .get ("fecha","").strip ()
        work_date =None 
        if fecha_str :
            for fmt in ("%d/%m/%Y","%Y-%m-%d"):
                try :
                    from datetime import datetime 
                    work_date =datetime .strptime (fecha_str ,fmt ).date ()
                    break 
                except ValueError :
                    continue 










        entry_lines_data =_parse_entry_lines_from_post (POST ,company )
        spare_parts_data =_parse_spare_parts_from_post (
        POST ,company ,entry_lines_data =entry_lines_data 
        )

































        integrity_errors =[]


        if not work_date :
            integrity_errors .append (
            "La fecha del parte es obligatoria y debe tener formato DD/MM/AAAA."
            )


        if not entry_lines_data :
            integrity_errors .append (
            "El parte debe contener al menos un bloque de trabajo."
            )

        for ld in entry_lines_data :
            blk =f"Bloque {ld['line_number']}"
            if not ld ["machine_raw"]:
                integrity_errors .append (
                f"{blk}: el código de máquina es obligatorio."
                )
            elif ld ["machine_asset"]is None :
                integrity_errors .append (
                f"{blk}: el código '{ld['machine_raw']}' no se ha podido "
                f"identificar en el catálogo de flota. "
                f"Corrígelo antes de guardar."
                )
            if not ld ["hc"]:
                integrity_errors .append (
                f"{blk}: la hora de inicio (H.C.) es obligatoria."
                )
            if not ld ["hf"]:
                integrity_errors .append (
                f"{blk}: la hora de fin (H.F.) es obligatoria."
                )
            if ld ["hc"]and ld ["hf"]and ld ["delta_hours"]is not None :
                if ld ["delta_hours"]<=0 :
                    integrity_errors .append (
                    f"{blk}: la H.F. debe ser posterior a la H.C. "
                    f"(Δ horas calculado: {ld['delta_hours']})."
                    )
            if not ld ["fault_description"]:
                integrity_errors .append (
                f"{blk}: la descripción de la avería es obligatoria."
                )
            if not ld ["repair_notes"]:
                integrity_errors .append (
                f"{blk}: la descripción de la reparación realizada es obligatoria."
                )







        for ld in entry_lines_data :
            if ld ["machine_asset"]is not None :
                asset =ld ["machine_asset"]
                blk =f"Bloque {ld['line_number']}"
                if asset .has_odometer :
                    reading =ld .get ("odometer_reading")
                    if reading is None :
                        integrity_errors .append (
                        f"{blk}: lectura de km (odómetro) obligatoria para {asset.code}."
                        )
                    elif reading ==0 and not asset .first_repair :
                        integrity_errors .append (
                        f"{blk}: la lectura de km no puede ser cero para {asset.code} "
                        f"(ya tiene partes anteriores registrados)."
                        )
                if asset .has_engine_hours :
                    reading =ld .get ("engine_hours_reading")
                    if reading is None :
                        integrity_errors .append (
                        f"{blk}: lectura de horómetro motor obligatoria para {asset.code}."
                        )
                    elif reading ==0 and not asset .first_repair :
                        integrity_errors .append (
                        f"{blk}: la lectura de horómetro motor no puede ser cero "
                        f"para {asset.code} (ya tiene partes anteriores registrados)."
                        )
                if asset .has_crane_hours :
                    reading =ld .get ("crane_hours_reading")
                    if reading is None :
                        integrity_errors .append (
                        f"{blk}: lectura de horómetro grúa obligatoria para {asset.code}."
                        )
                    elif reading ==0 and not asset .first_repair :
                        integrity_errors .append (
                        f"{blk}: la lectura de horómetro grúa no puede ser cero "
                        f"para {asset.code} (ya tiene partes anteriores registrados)."
                        )


        for spd in spare_parts_data :
            rep =f"Repuesto {spd['line_number']}"
            if not spd ["material"]:
                integrity_errors .append (
                f"{rep}: la descripción del material es obligatoria."
                )
            if spd ["quantity"]is None or spd ["quantity"]<=0 :
                integrity_errors .append (
                f"{rep}: las unidades deben ser un número positivo."
                )

        if integrity_errors :




            entradas_enriched_post =[
            {
            "idx":ld ["line_number"],
            "machine_raw":ld ["machine_raw"],
            "machine_asset":ld ["machine_asset"],
            "fault_description":ld ["fault_description"],
            "repair_notes":ld ["repair_notes"],
            "hc":ld ["hc"].strftime ("%H:%M")if ld ["hc"]else "",
            "hf":ld ["hf"].strftime ("%H:%M")if ld ["hf"]else "",
            "or_val":ld ["or_val"],
            "flags":ld ["flags"],
            }
            for ld in entry_lines_data 
            ]
            spare_enriched_post =[
            {
            "ridx":spd ["line_number"],
            "referencia":spd ["referencia"],
            "vehiculo_raw":spd ["vehiculo_raw"],
            "vehicle_asset":spd ["vehicle_asset"],
            "material":spd ["material"],
            "unidades":str (spd ["quantity"])if spd ["quantity"]is not None else "",
            "origen":spd ["source"],
            "proveedor":spd ["supplier"],
            "flags":spd ["flags"],
            }
            for spd in spare_parts_data 
            ]
            context =self ._get_context_base (request )
            context .update ({
            "error":" | ".join (integrity_errors ),
            "fecha":fecha_str ,
            "uncertain_date":False ,
            "confidence":POST .get ("confidence",""),
            "entradas_enriched":entradas_enriched_post ,
            "repuestos_enriched":spare_enriched_post ,
            "num_entradas":len (entry_lines_data ),
            "num_repuestos":len (spare_parts_data ),
            })
            return render (request ,self .template_name ,context )







        if not POST .get ("save_confirmed")and _form_action !="save_blocks":
            entradas_enriched_post =[
            {
            "idx":ld ["line_number"],
            "machine_raw":ld ["machine_raw"],
            "machine_asset":ld ["machine_asset"],
            "fault_description":ld ["fault_description"],
            "repair_notes":ld ["repair_notes"],
            "hc":ld ["hc"].strftime ("%H:%M")if ld ["hc"]else "",
            "hf":ld ["hf"].strftime ("%H:%M")if ld ["hf"]else "",
            "or_val":ld ["or_val"],
            "flags":ld ["flags"],
            }
            for ld in entry_lines_data 
            ]
            spare_enriched_post =[
            {
            "ridx":spd ["line_number"],
            "referencia":spd ["referencia"],
            "vehiculo_raw":spd ["vehiculo_raw"],
            "vehicle_asset":spd ["vehicle_asset"],
            "material":spd ["material"],
            "unidades":str (spd ["quantity"])if spd ["quantity"]is not None else "",
            "origen":spd ["source"],
            "proveedor":spd ["supplier"],
            "flags":spd ["flags"],
            }
            for spd in spare_parts_data 
            ]
            context =self ._get_context_base (request )
            context .update ({
            "error":None ,
            "fecha":fecha_str ,
            "uncertain_date":False ,
            "confidence":POST .get ("confidence",""),
            "entradas_enriched":entradas_enriched_post ,
            "repuestos_enriched":spare_enriched_post ,
            "num_entradas":len (entry_lines_data ),
            "num_repuestos":len (spare_parts_data ),
            })
            return render (request ,self .template_name ,context )





        from work_order_processor .validators import (
        run_intra_part_validation ,
        parse_blocks_from_post ,
        validate_inter_overlap ,
        TimeBlock ,
        )

        num_entradas_post =int (POST .get ("num_entradas",len (entry_lines_data )))
        _blocks =parse_blocks_from_post (POST ,num_entradas_post ,entry_lines_data =entry_lines_data )
        _intra =run_intra_part_validation (_blocks )

        if not _intra .ok and _form_action !="save_blocks":
            entradas_enriched_post =[
            {
            "idx":ld ["line_number"],
            "machine_raw":ld ["machine_raw"],
            "machine_asset":ld ["machine_asset"],
            "fault_description":ld ["fault_description"],
            "repair_notes":ld ["repair_notes"],
            "hc":ld ["hc"].strftime ("%H:%M")if ld ["hc"]else "",
            "hf":ld ["hf"].strftime ("%H:%M")if ld ["hf"]else "",
            "or_val":ld ["or_val"],
            "flags":ld ["flags"],
            }
            for ld in entry_lines_data 
            ]
            spare_enriched_post =[
            {
            "ridx":spd ["line_number"],
            "referencia":spd ["referencia"],
            "vehiculo_raw":spd ["vehiculo_raw"],
            "vehicle_asset":spd ["vehicle_asset"],
            "material":spd ["material"],
            "unidades":str (spd ["quantity"])if spd ["quantity"]is not None else "",
            "origen":spd ["source"],
            "proveedor":spd ["supplier"],
            "flags":spd ["flags"],
            }
            for spd in spare_parts_data 
            ]
            context =self ._get_context_base (request )
            context .update ({
            "error":" | ".join (e .message for e in _intra .errors ),
            "fecha":fecha_str ,
            "uncertain_date":False ,
            "confidence":POST .get ("confidence",""),
            "entradas_enriched":entradas_enriched_post ,
            "repuestos_enriched":spare_enriched_post ,
            "num_entradas":len (entry_lines_data ),
            "num_repuestos":len (spare_parts_data ),
            })
            return render (request ,self .template_name ,context )




        try :
            with transaction .atomic ():


                worker_name =(
                cu .user .get_full_name ()or cu .user .username 
                ).upper ()










                date_tag =(
                work_date .strftime ("%d-%m-%Y")if work_date else "SIN-FECHA"
                )
                synthetic_name =f"{worker_name}_{date_tag}.pdf"

                work_order =WorkOrder (
                company =company ,
                uploaded_by =cu ,
                source =WorkOrder .Source .DIGITAL ,
                status =WorkOrder .Status .DONE ,
                total_pages =1 ,
                processed_pages =1 ,
                reviewed =False ,
                )
                work_order .source_pdf .name =synthetic_name 
                work_order .save ()













                from work_order_processor .services import _coerce_confidence as _cc 
                _session_extraction =request .session .get (
                "operator_upload_extraction",{}
                )
                _gemini_confidence =_cc (
                _session_extraction .get ("extraction_confidence")
                )
                _gemini_uncertain_date =bool (
                _session_extraction .get ("uncertain_date",False )
                )
                entry =WorkOrderEntry .objects .create (
                work_order =work_order ,
                page_number =1 ,
                worker_name =worker_name ,
                work_date =work_date ,
                uncertain_date =_gemini_uncertain_date ,
                extraction_confidence =_gemini_confidence ,
                raw_gemini_response =None ,
                )


                created_lines ={}
                created_line_pks =[]

                for ld in entry_lines_data :
                    line =WorkOrderEntryLine .objects .create (
                    entry =entry ,
                    line_number =ld ["line_number"],
                    machine_asset =ld ["machine_asset"],
                    machine_raw =ld ["machine_raw"],
                    machine_norm =ld ["machine_norm"],
                    fault_description =ld ["fault_description"],
                    repair_notes =ld ["repair_notes"],
                    hc =ld ["hc"],
                    hf =ld ["hf"],
                    or_val =ld ["or_val"],
                    delta_hours =ld ["delta_hours"],
                    flags =ld ["flags"],
                    odometer_reading =ld .get ("odometer_reading"),
                    engine_hours_reading =ld .get ("engine_hours_reading"),
                    crane_hours_reading =ld .get ("crane_hours_reading"),
                    )
                    created_lines [ld ["line_number"]]=line 
                    created_line_pks .append (line .pk )



                for spd in spare_parts_data :




                    target_line =next (iter (created_lines .values ()),None )
                    if target_line is None :
                        continue 

                    SparePartLine .objects .create (
                    entry_line =target_line ,
                    line_number =spd ["line_number"],
                    reference =spd ["referencia"],
                    vehicle =spd ["vehicle_asset"],
                    material =spd ["material"],
                    quantity =spd ["quantity"],
                    source =spd ["source"],
                    supplier =spd ["supplier"],
                    flags =spd ["flags"],
                    )





            if any (spd .get ("cg_incident")for spd in spare_parts_data ):
                WorkOrder .objects .filter (pk =work_order .pk ).update (has_cg_incident =True )
                logger .warning (
                "# [Confirm] WorkOrder #%d marcado con has_cg_incident=True: "
                "al menos un repuesto tiene un CdG no resuelto en catálogo.",
                work_order .pk ,
                )

            logger .info (
            "# [Confirm] WorkOrder #%d creado correctamente. "
            "Entradas: %d | Repuestos: %d.",
            work_order .pk ,
            len (entry_lines_data ),
            len (spare_parts_data ),
            )





            import json as _json_mod 
            _zero_raw =POST .get ("zero_meters_confirmed","").strip ()
            if _zero_raw :
                try :
                    _zero_data =_json_mod .loads (_zero_raw )
                    for _bIdx_str ,_meter_list in _zero_data .items ():
                        try :
                            _bIdx =int (_bIdx_str )
                        except (ValueError ,TypeError ):
                            continue 
                        _line =created_lines .get (_bIdx )
                        if _line is None :
                            continue 
                        _asset =_line .machine_asset 
                        _line_fields =[]
                        _asset_fields =[]
                        for _m in _meter_list :
                            _name =_m .get ("name","")
                            if "odometer"in _name :
                                _line .odometer_reading =None 
                                _line_fields .append ("odometer_reading")
                                if _asset and _asset .has_odometer :
                                    _asset .has_odometer =False 
                                    _asset_fields .append ("has_odometer")
                            elif "engine_hours"in _name :
                                _line .engine_hours_reading =None 
                                _line_fields .append ("engine_hours_reading")
                                if _asset and _asset .has_engine_hours :
                                    _asset .has_engine_hours =False 
                                    _asset_fields .append ("has_engine_hours")
                            elif "crane_hours"in _name :
                                _line .crane_hours_reading =None 
                                _line_fields .append ("crane_hours_reading")
                                if _asset and _asset .has_crane_hours :
                                    _asset .has_crane_hours =False 
                                    _asset_fields .append ("has_crane_hours")
                        if _line_fields :
                            _line .save (update_fields =_line_fields )
                        if _asset and _asset_fields :
                            _asset .save (update_fields =list (set (_asset_fields )))
                            logger .info (
                            "# [Confirm] MachineAsset %s: flags desactivados: %s.",
                            _asset .code ,_asset_fields ,
                            )
                except (_json_mod .JSONDecodeError ,Exception )as _ze :
                    logger .warning (
                    "# [Confirm] Error procesando zero_meters_confirmed: %s",_ze 
                    )



            for ld in entry_lines_data :
                _asset =ld .get ("machine_asset")
                if _asset and _asset .first_repair :
                    _asset .first_repair =False 
                    _asset .save (update_fields =["first_repair"])
                    logger .info (
                    "# [Confirm] MachineAsset %s: first_repair=False.",
                    _asset .code ,
                    )

        except Exception as exc :
            logger .error (
            "# [Confirm] Error en persistencia atómica: %s",exc ,exc_info =True 
            )
            context =self ._get_context_base (request )
            context ["error"]=(
            f"Error al guardar el parte: {exc}. "
            "Por favor, inténtalo de nuevo o contacta con el administrador."
            )
            return render (request ,self .template_name ,context )










        from work_order_processor .models import WorkdayGap as _WDG_CO 
        for _co_ld in entry_lines_data :
            if not _co_ld .get ("is_personal"):
                continue 
            _co_abs_cat =_co_ld .get ("absence_category")
            _co_hc =_co_ld .get ("hc")
            _co_hf =_co_ld .get ("hf")
            if _co_hc is None or _co_hf is None :
                continue 
            _co_dur_min =max (
            0 ,
            (_co_hf .hour *60 +_co_hf .minute )
            -(_co_hc .hour *60 +_co_hc .minute ),
            )
            _WDG_CO .objects .create (
            work_order =work_order ,
            gap_type =_WDG_CO .GapType .GAP ,
            gap_start =_co_hc ,
            gap_end =_co_hf ,
            duration_minutes =_co_dur_min ,
            absence_category =_co_abs_cat ,
            note =_co_ld .get ("repair_notes",""),
            resolved =True ,
            )
            logger .info (
            "# [FormView/close_order] WorkdayGap sintético creado. "
            "work_order_pk=%r gap_start=%r gap_end=%r absence_cat=%r",
            work_order .pk ,_co_hc ,_co_hf ,
            _co_abs_cat .label if _co_abs_cat else None ,
            )










        for _lpk in created_line_pks :
            _line_obj =WorkOrderEntryLine .objects .filter (pk =_lpk ).first ()
            if _line_obj is None :
                continue 
            _cached =find_cached_classification (
            fault_description =_line_obj .fault_description ,
            repair_notes =_line_obj .repair_notes ,
            company =company ,
            )
            if _cached :
                WorkOrderEntryLine .objects .filter (pk =_lpk ).update (
                fault_category =_cached [0 ],
                fault_subcategory =_cached [1 ],
                )
                logger .info (
                "# [Confirm] Clasificación copiada desde caché para "
                "WorkOrderEntryLine pk=%d: category=%s subcategory=%s.",
                _lpk ,_cached [0 ],_cached [1 ],
                )
            else :
                classify_fault_line .apply_async (
                args =[_lpk ],
                queue ="work_orders",
                )
                logger .info (
                "# [Confirm] classify_fault_line encolada para "
                "WorkOrderEntryLine pk=%d.",
                _lpk ,
                )




        try :
            generate_work_order_excel (work_order .pk )
            logger .info (
            "# [Confirm] Excel generado correctamente para WorkOrder #%d.",
            work_order .pk ,
            )
        except Exception as exc :
            logger .warning (
            "# [Confirm] Excel no generado para WorkOrder #%d: %s.",
            work_order .pk ,exc ,
            )

















        if work_date is not None and _form_action !="save_blocks":
            from decimal import Decimal as _Dec_C2 
            from ivr_config .models import WorkerAbsence as _WA_C2 
            _total_hours_c2 =sum (
            (ld ["delta_hours"]for ld in _parsed_lines if ld .get ("delta_hours")is not None ),
            _Dec_C2 ("0"),
            )
            _has_absence_c2 =_WA_C2 .objects .filter (
            company_user =cu ,
            start_date__lte =work_date ,
            end_date__gte =work_date ,
            ).exists ()
            if _total_hours_c2 <_Dec_C2 ("8")and not _has_absence_c2 :
                _missing_c2 =_Dec_C2 ("8")-_total_hours_c2 
                context =self ._get_context_base (request )
                extraction =request .session .get ("operator_upload_extraction",{})
                context .update ({
                "error":(
                f"La jornada del parte suma {_total_hours_c2} h, "
                f"pero se requieren al menos 8 h. "
                f"Faltan {_missing_c2} h para completar la jornada. "
                f"Añade los bloques de trabajo que faltan o registra "
                f"una ausencia justificada para esta fecha."
                ),
                "extraction":extraction ,
                "fecha":POST .get ("fecha",""),
                "uncertain_date":False ,
                "confidence":"",
                "entradas_enriched":[],
                "repuestos_enriched":[],
                "num_entradas":0 ,
                "num_repuestos":0 ,
                "min_date":_get_min_allowed_date (cu ).isoformat ()if _get_min_allowed_date (cu )else "",
                })
                return render (request ,self .template_name ,context )















        if work_date is not None :
            from ivr_config .models import WorkdaySchedule as _WDS_C2 
            from django .urls import reverse as _rev_g4c2 
            _schedule_g4c2 =(
            cu .workday_schedule 
            if cu .workday_schedule_id 
            else (




            next (
            (
            _sec .workday_schedule 
            for _sec in (
            _contact_g4c2 .sections 
            .filter (is_active =True ,workday_schedule__isnull =False )
            .select_related ("workday_schedule")
            .order_by ("name")
            )
            ),
            None ,
            )
            if (_contact_g4c2 :=(
            Contact .objects .filter (company_user =cu )
            .prefetch_related ("sections__workday_schedule")
            .first ()
            ))is not None 
            else None 
            )or _WDS_C2 .objects .filter (
            company =company ,is_default =True 
            ).first ()
            )
            _gaps_g4c2 =_detect_workday_gaps (
            entry_lines_data ,_schedule_g4c2 ,work_date 
            )
            if _gaps_g4c2 :




                from django .db import transaction as _tx_g4c2 
                _worker_name_g4 =(
                cu .user .get_full_name ()or cu .user .username 
                ).upper ()
                _date_tag_g4 =work_date .strftime ("%d-%m-%Y")
                _synth_g4 =f"{_worker_name_g4}_{_date_tag_g4}_DRAFT.pdf"
                with _tx_g4c2 .atomic ():
                    _wo_draft =WorkOrder (
                    company =company ,
                    uploaded_by =cu ,
                    source =WorkOrder .Source .DIGITAL ,
                    status =WorkOrder .Status .PENDING_GAPS ,
                    total_pages =1 ,
                    processed_pages =1 ,
                    reviewed =False ,
                    )
                    _wo_draft .source_pdf .name =_synth_g4 
                    _wo_draft .save ()
                    _entry_draft =WorkOrderEntry .objects .create (
                    work_order =_wo_draft ,
                    page_number =1 ,
                    worker_name =_worker_name_g4 ,
                    work_date =work_date ,
                    uncertain_date =False ,
                    extraction_confidence =WorkOrderEntry .Confidence .HIGH ,
                    raw_gemini_response =None ,
                    )
                    _line_num_g4 =1 
                    for _ld in entry_lines_data :
                        _ln =WorkOrderEntryLine .objects .create (
                        entry =_entry_draft ,
                        line_number =_line_num_g4 ,
                        machine_asset =_ld .get ("machine_asset"),
                        machine_raw =_ld .get ("machine_raw",""),
                        machine_norm ="",
                        fault_description =_ld .get ("fault_description",""),
                        repair_notes =_ld .get ("repair_notes",""),
                        hc =_ld .get ("hc"),
                        hf =_ld .get ("hf"),
                        or_val =_ld .get ("or_val",""),
                        delta_hours =_ld .get ("delta_hours"),
                        flags =[],
                        odometer_reading =_ld .get ("odometer_reading"),
                        engine_hours_reading =_ld .get ("engine_hours_reading"),
                        crane_hours_reading =_ld .get ("crane_hours_reading"),
                        )
                        _line_num_g4 +=1 
                    from work_order_processor .models import WorkdayGap as _WDG_C2 
                    for _gap in _gaps_g4c2 :
                        _WDG_C2 .objects .create (
                        work_order =_wo_draft ,
                        gap_type =_gap ["gap_type"],
                        gap_start =_gap ["gap_start"],
                        gap_end =_gap ["gap_end"],
                        duration_minutes =_gap ["duration_minutes"],
                        )
                request .session ["pending_gaps_wo_pk"]=_wo_draft .pk 
                request .session .modified =True 
                logger .info (
                "# [ConfirmView/Gate4] PENDING_GAPS borrador pk=%d creado. "
                "%d gap(s) detectado(s). Redirigiendo a resolución.",
                _wo_draft .pk ,len (_gaps_g4c2 ),
                )
                return redirect (
                _rev_g4c2 (
                "panel:operator_gap_resolution",
                kwargs ={"wo_draft_pk":_wo_draft .pk },
                )
                )


        request .session .pop ("operator_upload_extraction",None )
        request .session .modified =True 





        _inter =validate_inter_overlap (
        company_user =cu ,
        work_date =work_date ,
        blocks =_blocks ,
        exclude_work_order_pk =work_order .pk ,
        )

        if _inter .has_overlap :


            WorkOrder .objects .filter (
            pk__in =[work_order .pk ]+_inter .conflicting_ids 
            ).update (has_overlap_incident =True )
            logger .warning (
            "# [Confirm] Solapamiento inter-parte detectado. "
            "WorkOrder #%d solapa con: %s.",
            work_order .pk ,
            _inter .conflicting_ids ,
            )
            django_messages .warning (
            request ,
            f"Parte #{work_order.pk} guardado con incidencia de solapamiento."
            )
            context =self ._get_context_base (request )
            context .update ({
            "overlap_incidents":True ,
            "new_work_order_pk":work_order .pk ,
            "conflicting_parts":[
            {"pk":pk ,"fecha":fecha }
            for pk ,fecha in zip (
            _inter .conflicting_ids ,
            _inter .conflicting_dates ,
            )
            ],
            "part_saved":True ,
            })
            return render (request ,self .template_name ,context )

        django_messages .success (
        request ,
        f"Parte de trabajo registrado correctamente (#{work_order.pk}). "
        f"El informe Excel está disponible en tu historial."
        )




        from django .urls import reverse as _reverse 
        _cu =request .user .company_user 
        if _cu .role in (CompanyUser .ROLE_ADMIN ,CompanyUser .ROLE_SUPERVISOR ):
            return redirect (_reverse ("panel:work_order_admin_history"))
        return redirect (_reverse ("panel:operator_history"))


class WorkOrderEntryFormView (WorkshopRequiredMixin ,View ):
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

    template_name ="panel/operator/form_entry.html"

    def _get_company_user (self ,request ):
        """
        Returns the CompanyUser for the authenticated request user.
        ---
        Devuelve el CompanyUser del usuario autenticado en la solicitud.
        """
        return request .user .company_user 

    def _get_context_base (self ,request ):
        """
        Returns the base template context with company and navigation data.
        Provides the list of active MachineAsset records for autocomplete and
        the list of open repair orders (BreakdownTicket with is_repair_order=True
        and status != RESOLVED) available to the authenticated operator.
        Repair orders without assigned_to are available to all operators.
        Repair orders assigned to this operator are included with priority.
        ---
        Devuelve el contexto base con empresa y datos de navegación.
        Proporciona la lista de MachineAsset activos para autocompletado y
        la lista de órdenes de reparación abiertas (BreakdownTicket con
        is_repair_order=True y status != RESOLVED) disponibles para el operario.
        Las OTs sin assigned_to están disponibles para cualquier operario.
        Las OTs asignadas a este operario se incluyen con prioridad.
        """
        from fleet .models import MachineAsset 
        from chat .models import BreakdownTicket 
        from django .db .models import Q as _Q 
        cu =self ._get_company_user (request )
        company =cu .company 
        assets =list (
        MachineAsset .objects .filter (company =company ,is_active =True )
        .order_by ("code")
        .values ("code","brand_model")
        )


        repair_orders =list (
        BreakdownTicket .objects 
        .filter (
        room__company =company ,
        is_repair_order =True ,
        )
        .exclude (status =BreakdownTicket .STATUS_RESOLVED )
        .filter (
        _Q (assigned_to__isnull =True )|_Q (assigned_to =cu )
        )
        .select_related ("machine","section")
        .order_by ("-urgency","created_at")
        )
        return {
        "company":company ,
        "company_user":cu ,
        "active_nav":"operator_dashboard",
        "assets":assets ,
        "repair_orders":repair_orders ,
        }

    def get (self ,request ,*args ,**kwargs ):
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
        from work_order_processor .models import WorkOrder as _WO_E ,SparePartLine as _SPL_E 
        cu =self ._get_company_user (request )
        company =cu .company 
        min_date =_get_min_allowed_date (cu )
        wo_pk =kwargs .get ("wo_pk")

        if wo_pk is not None :


            try :
                wo_edit =_WO_E .objects .get (
                pk =wo_pk ,
                company =company ,
                uploaded_by =cu ,
                reviewed =False ,
                source__in =[
                _WO_E .Source .DIGITAL ,
                _WO_E .Source .GENERATED ,
                ],
                )
            except _WO_E .DoesNotExist :
                django_messages .error (
                request ,
                "El parte no existe, ya ha sido revisado o no te pertenece.",
                )
                return redirect ("/panel/operator/history/")



            entries =list (wo_edit .entries .prefetch_related ("lines").all ())
            first_entry =entries [0 ]if entries else None 
            fecha_str =(
            first_entry .work_date .strftime ("%Y-%m-%d")
            if first_entry and first_entry .work_date else ""
            )
            entradas_enriched =[]
            repuestos_enriched =[]
            ridx =1 
            for entry in entries :
                for line in entry .lines .order_by ("line_number"):
                    entradas_enriched .append ({
                    "idx":len (entradas_enriched )+1 ,
                    "machine_raw":line .machine_raw or "",
                    "machine_asset":line .machine_asset ,
                    "fault_description":line .fault_description or "",
                    "repair_notes":line .repair_notes or "",
                    "hc":line .hc .strftime ("%H:%M")if line .hc else "",
                    "hf":line .hf .strftime ("%H:%M")if line .hf else "",
                    "or_val":line .or_val or "",
                    "flags":line .flags or [],
                    "odometer_reading":float (line .odometer_reading )if line .odometer_reading is not None else "",
                    "engine_hours_reading":float (line .engine_hours_reading )if line .engine_hours_reading is not None else "",
                    "crane_hours_reading":float (line .crane_hours_reading )if line .crane_hours_reading is not None else "",
                    })
                    for spare in _SPL_E .objects .filter (entry_line =line ).order_by ("line_number"):
                        repuestos_enriched .append ({
                        "ridx":ridx ,
                        "referencia":spare .reference or "",
                        "vehiculo_raw":"",
                        "vehicle_asset":spare .vehicle ,
                        "material":spare .material or "",
                        "unidades":str (spare .quantity )if spare .quantity is not None else "",
                        "origen":spare .source or "WAREHOUSE",
                        "proveedor":spare .supplier or "",
                        "unit_price":str (spare .unit_price )if spare .unit_price is not None else "",
                        "flags":spare .flags or [],
                        })
                        ridx +=1 



            _schedule_edit =_resolve_operator_schedule (cu ,company )
            _lunch_start_edit =""
            _lunch_end_edit =""
            _first_hc_edit =""
            _show_lunch_edit =False 
            _end_time_morning_edit =""
            _end_time_afternoon_edit =""
            if _schedule_edit and not _schedule_edit .is_intensive :
                _show_lunch_edit =True 
                if _schedule_edit .end_time_morning :
                    _lunch_start_edit =_schedule_edit .end_time_morning .strftime ("%H:%M")
                    _end_time_morning_edit =_lunch_start_edit 
                if _schedule_edit .start_time_afternoon :
                    _lunch_end_edit =_schedule_edit .start_time_afternoon .strftime ("%H:%M")
            if _schedule_edit and _schedule_edit .end_time_afternoon :
                _end_time_afternoon_edit =_schedule_edit .end_time_afternoon .strftime ("%H:%M")
            elif _schedule_edit and _schedule_edit .is_intensive and _schedule_edit .end_time_morning :
                _end_time_afternoon_edit =_schedule_edit .end_time_morning .strftime ("%H:%M")
            if _schedule_edit and _schedule_edit .start_time_morning :
                _first_hc_edit =_schedule_edit .start_time_morning .strftime ("%H:%M")


            _first_hf_edit =_end_time_morning_edit if _end_time_morning_edit else _end_time_afternoon_edit 

            context =self ._get_context_base (request )
            context .update ({
            "edit_mode":True ,
            "edit_wo_pk":wo_pk ,
            "num_entradas":len (entradas_enriched )or 1 ,
            "num_repuestos":len (repuestos_enriched ),
            "fecha":fecha_str ,
            "entradas_enriched":entradas_enriched ,
            "repuestos_enriched":repuestos_enriched ,
            "min_date":min_date .isoformat ()if min_date else "",
            "lunch_break_start":_lunch_start_edit ,
            "lunch_break_end":_lunch_end_edit ,
            "first_block_hc":_first_hc_edit ,
            "first_block_hf":_first_hf_edit ,
            "show_lunch_break":_show_lunch_edit ,
            "end_time_morning":_end_time_morning_edit ,
            "end_time_afternoon":_end_time_afternoon_edit ,
            })
            return render (request ,self .template_name ,context )



        from datetime import date as _date_ip 
        from work_order_processor .models import WorkOrder as _WO_IP ,SparePartLine as _SPL_IP 
        _today_ip =_date_ip .today ()
        _in_progress_wo =_WO_IP .objects .filter (
        company =company ,
        uploaded_by =cu ,
        source =_WO_IP .Source .DIGITAL ,
        status =_WO_IP .Status .IN_PROGRESS ,
        ).order_by ("-upload_date").first ()

        if _in_progress_wo is not None :


            _ip_entries =list (_in_progress_wo .entries .prefetch_related ("lines").all ())
            _ip_first_entry =_ip_entries [0 ]if _ip_entries else None 
            _ip_fecha_str =(
            _ip_first_entry .work_date .strftime ("%Y-%m-%d")
            if _ip_first_entry and _ip_first_entry .work_date else ""
            )
            _ip_entradas =[]
            _ip_repuestos =[]
            _ip_ridx =1 
            for _ip_entry in _ip_entries :
                for _ip_line in _ip_entry .lines .order_by ("line_number"):
                    _ip_entradas .append ({
                    "idx":len (_ip_entradas )+1 ,
                    "machine_raw":_ip_line .machine_raw or "",
                    "machine_asset":_ip_line .machine_asset ,
                    "fault_description":_ip_line .fault_description or "",
                    "repair_notes":_ip_line .repair_notes or "",
                    "hc":_ip_line .hc .strftime ("%H:%M")if _ip_line .hc else "",
                    "hf":_ip_line .hf .strftime ("%H:%M")if _ip_line .hf else "",
                    "or_val":_ip_line .or_val or "",
                    "flags":_ip_line .flags or [],
                    "odometer_reading":float (_ip_line .odometer_reading )if _ip_line .odometer_reading is not None else "",
                    "engine_hours_reading":float (_ip_line .engine_hours_reading )if _ip_line .engine_hours_reading is not None else "",
                    "crane_hours_reading":float (_ip_line .crane_hours_reading )if _ip_line .crane_hours_reading is not None else "",
                    })
                    for _ip_spare in _SPL_IP .objects .filter (entry_line =_ip_line ).order_by ("line_number"):
                        _ip_repuestos .append ({
                        "ridx":_ip_ridx ,
                        "referencia":_ip_spare .reference or "",
                        "vehiculo_raw":"",
                        "vehicle_asset":_ip_spare .vehicle ,
                        "material":_ip_spare .material or "",
                        "unidades":str (_ip_spare .quantity )if _ip_spare .quantity is not None else "",
                        "origen":_ip_spare .source or "WAREHOUSE",
                        "proveedor":_ip_spare .supplier or "",
                        "unit_price":str (_ip_spare .unit_price )if _ip_spare .unit_price is not None else "",
                        "flags":_ip_spare .flags or [],
                        })
                        _ip_ridx +=1 


            _schedule_ip =_resolve_operator_schedule (cu ,company )
            _ip_lunch_start =""
            _ip_lunch_end =""
            _ip_first_hc =""
            _ip_show_lunch =False 
            _ip_end_time_morning =""
            _ip_end_time_afternoon =""
            if _schedule_ip and not _schedule_ip .is_intensive :
                _ip_show_lunch =True 
                if _schedule_ip .end_time_morning :
                    _ip_lunch_start =_schedule_ip .end_time_morning .strftime ("%H:%M")
                    _ip_end_time_morning =_ip_lunch_start 
                if _schedule_ip .start_time_afternoon :
                    _ip_lunch_end =_schedule_ip .start_time_afternoon .strftime ("%H:%M")
            if _schedule_ip and _schedule_ip .end_time_afternoon :
                _ip_end_time_afternoon =_schedule_ip .end_time_afternoon .strftime ("%H:%M")
            elif _schedule_ip and _schedule_ip .is_intensive and _schedule_ip .end_time_morning :
                _ip_end_time_afternoon =_schedule_ip .end_time_morning .strftime ("%H:%M")
            if _schedule_ip and _schedule_ip .start_time_morning :
                _ip_first_hc =_schedule_ip .start_time_morning .strftime ("%H:%M")
            _ip_first_hf =_ip_end_time_morning if _ip_end_time_morning else _ip_end_time_afternoon 
            _ip_no_lunch =_ip_first_entry .no_lunch_break if _ip_first_entry else False 
            logger .info (
            "# [I2-DIAG-GET] _ip_first_entry=%r lb_start_bd=%r lb_end_bd=%r "
            "no_lunch_bd=%r _ip_lunch_start=%r _ip_lunch_end=%r",
            _ip_first_entry ,
            _ip_first_entry .lunch_break_start if _ip_first_entry else None ,
            _ip_first_entry .lunch_break_end if _ip_first_entry else None ,
            _ip_first_entry .no_lunch_break if _ip_first_entry else None ,
            _ip_lunch_start ,_ip_lunch_end ,
            )
            context =self ._get_context_base (request )
            from ivr_config .models import AbsenceCategory as _AbsCat 
            from fleet .models import MachineAsset as _MA 
            from work_order_processor .management .commands .seed_personal_asset import PERSONAL_ASSET_CODE 
            _absence_cats =list (
            _AbsCat .objects .filter (company =company ,is_active =True )
            .order_by ("order","label")
            .values ("id","label","requires_note")
            )
            context .update ({
            "in_progress_mode":True ,
            "in_progress_wo_pk":_in_progress_wo .pk ,
            "num_entradas":len (_ip_entradas ),
            "num_repuestos":len (_ip_repuestos ),
            "fecha":_ip_fecha_str ,
            "entradas_enriched":_ip_entradas ,
            "repuestos_enriched":_ip_repuestos ,
            "min_date":min_date .isoformat ()if min_date else "",
            "lunch_break_start":_ip_first_entry .lunch_break_start .strftime ("%H:%M")if _ip_first_entry and _ip_first_entry .lunch_break_start else "",
            "lunch_break_end":_ip_first_entry .lunch_break_end .strftime ("%H:%M")if _ip_first_entry and _ip_first_entry .lunch_break_end else "",
            "first_block_hc":_ip_first_hc ,
            "first_block_hf":_ip_first_hf ,
            "no_lunch_break":_ip_no_lunch ,
            "show_lunch_break":_ip_show_lunch ,
            "end_time_morning":_ip_end_time_morning ,
            "end_time_afternoon":_ip_end_time_afternoon ,
            "absence_categories":_json_fix .dumps (_absence_cats ),
            "personal_asset_code":PERSONAL_ASSET_CODE ,
            })
            return render (request ,self .template_name ,context )








        _schedule_create =_resolve_operator_schedule (cu ,company )
        _lunch_start =""
        _lunch_end =""
        _first_hc =""
        _end_time_morning_create =""
        _end_time_afternoon_create =""
        if _schedule_create is not None :
            if not _schedule_create .is_intensive :


                if _schedule_create .end_time_morning :
                    _lunch_start =_schedule_create .end_time_morning .strftime ("%H:%M")
                if _schedule_create .start_time_afternoon :
                    _lunch_end =_schedule_create .start_time_afternoon .strftime ("%H:%M")


            if _schedule_create .start_time_morning :
                _first_hc =_schedule_create .start_time_morning .strftime ("%H:%M")
            if not _schedule_create .is_intensive and _schedule_create .end_time_morning :
                _end_time_morning_create =_schedule_create .end_time_morning .strftime ("%H:%M")
            if _schedule_create .end_time_afternoon :
                _end_time_afternoon_create =_schedule_create .end_time_afternoon .strftime ("%H:%M")
            elif _schedule_create .is_intensive and _schedule_create .end_time_morning :
                _end_time_afternoon_create =_schedule_create .end_time_morning .strftime ("%H:%M")

        import json as _json_fix 
        from ivr_config .models import AbsenceCategory as _AbsCat 
        from work_order_processor .management .commands .seed_personal_asset import PERSONAL_ASSET_CODE 
        _absence_cats =list (
        _AbsCat .objects .filter (company =company ,is_active =True )
        .order_by ("order","label")
        .values ("id","label","requires_note")
        )
        context =self ._get_context_base (request )
        context .update ({
        "num_entradas":1 ,
        "num_repuestos":0 ,
        "fecha":"",
        "min_date":min_date .isoformat ()if min_date else "",
        "lunch_break_start":_lunch_start ,
        "lunch_break_end":_lunch_end ,
        "first_block_hc":_first_hc ,
        "first_block_hf":_end_time_morning_create if _end_time_morning_create else _end_time_afternoon_create ,
        "no_lunch_break":False ,
        "show_lunch_break":bool (_lunch_start ),
        "end_time_morning":_end_time_morning_create ,
        "end_time_afternoon":_end_time_afternoon_create ,
        "absence_categories":_json_fix .dumps (_absence_cats ),
        "personal_asset_code":PERSONAL_ASSET_CODE ,
        "is_intensive_override":getattr (cu ,"is_intensive_override",False ),
        })
        return render (request ,self .template_name ,context )

    def post (self ,request ,*args ,**kwargs ):
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
        from datetime import datetime ,time as dt_time 
        from decimal import Decimal ,InvalidOperation 
        from django .db import transaction 
        from fleet .models import MachineAsset 
        from work_order_processor .models import (
        WorkOrder ,WorkOrderEntry ,WorkOrderEntryLine ,SparePartLine ,
        )
        from work_order_processor .services import (
        generate_work_order_excel ,
        _normalise_machine_code ,
        _compute_delta_hours ,
        )

        cu =self ._get_company_user (request )
        company =cu .company 
        POST =request .POST 





        from datetime import time as _dt_time_lb 
        def _parse_time_field (raw ):
            """
            Parses a HH:MM string into a datetime.time or None.
            ---
            Parsea una cadena HH:MM a datetime.time o None.
            """
            if not raw :
                return None 
            try :
                parts =raw .strip ().split (":")
                return _dt_time_lb (int (parts [0 ]),int (parts [1 ]))
            except (ValueError ,IndexError ):
                return None 

        _lb_start_raw =POST .get ("lunch_break_start","").strip ()
        _lb_end_raw =POST .get ("lunch_break_end","").strip ()
        _lb_start =_parse_time_field (_lb_start_raw )
        _lb_end =_parse_time_field (_lb_end_raw )


        _no_lunch_break =POST .get ("no_lunch_break","")=="1"


        _form_action =POST .get ("form_action","close_order").strip ()


        _post_schedule =_resolve_operator_schedule (cu ,company )
        _post_lb_start =""
        _post_lb_end =""
        _post_show_lunch =False 
        if _post_schedule and not _post_schedule .is_intensive :
            _post_show_lunch =True 
            if _post_schedule .end_time_morning :
                _post_lb_start =_post_schedule .end_time_morning .strftime ("%H:%M")
            if _post_schedule .start_time_afternoon :
                _post_lb_end =_post_schedule .start_time_afternoon .strftime ("%H:%M")
        logger .info (
        "# [I2-DIAG] lunch_break_start_raw=%r lb_start=%r "
        "lunch_break_end_raw=%r lb_end=%r no_lunch_break=%r form_action=%r",
        _lb_start_raw ,_lb_start ,_lb_end_raw ,_lb_end ,
        _no_lunch_break ,POST .get ("form_action",""),
        )




        fecha_str =POST .get ("fecha","").strip ()
        work_date =None 
        if fecha_str :
            for fmt in ("%d/%m/%Y","%Y-%m-%d"):
                try :
                    work_date =datetime .strptime (fecha_str ,fmt ).date ()
                    break 
                except ValueError :
                    continue 







        logger .info (
        "# [I2-DIAG-WORKDATE] work_date=%r form_action=%r",
        work_date ,_form_action ,
        )
        if work_date is not None :
            _min_date =_get_min_allowed_date (cu )
            logger .info (
            "# [I2-DIAG-MINDATE] work_date=%r _min_date=%r form_action=%r",
            work_date ,_min_date ,_form_action ,
            )
            if _min_date is not None and work_date <_min_date :
                from datetime import timedelta as _td_fd 
                _last_rev =_min_date -_td_fd (days =1 )
                context =self ._get_context_base (request )
                context .update ({
                "error":(
                f"No puedes introducir un parte con fecha "
                f"{work_date.strftime('%d/%m/%Y')}. "
                f"El ultimo parte revisado es del "
                f"{_last_rev.strftime('%d/%m/%Y')} y ya ha sido auditado. "
                f"La fecha minima permitida es "
                f"{_min_date.strftime('%d/%m/%Y')}."
                ),
                "fecha":fecha_str ,
                "entradas_enriched":[],
                "repuestos_enriched":[],
                "num_entradas":1 ,
                "num_repuestos":0 ,
                "min_date":_min_date .isoformat (),
                "lunch_break_start":_post_lb_start ,
                "lunch_break_end":_post_lb_end ,
                "show_lunch_break":_post_show_lunch ,
                })
                return render (request ,self .template_name ,context )









        _edit_wo_pk_pre =POST .get ("edit_wo_pk","").strip ()
        if _edit_wo_pk_pre :
            try :
                _wo_orig_pre =WorkOrder .objects .get (
                pk =int (_edit_wo_pk_pre ),
                company =company ,
                uploaded_by =cu ,
                reviewed =False ,
                source__in =[
                WorkOrder .Source .DIGITAL ,
                WorkOrder .Source .GENERATED ,
                ],
                )
                _wo_orig_pre .delete ()
            except (WorkOrder .DoesNotExist ,ValueError ):


                pass 















        if work_date is not None :
            from django .urls import reverse as _rev0 
            from work_order_processor .models import WorkOrder as _WO0 ,WorkOrderEntry as _WOE0 
            _existing_entry0 =_WOE0 .objects .filter (
            work_order__company =company ,
            work_order__uploaded_by =cu ,
            work_order__source__in =[
            _WO0 .Source .DIGITAL ,
            _WO0 .Source .GENERATED ,
            ],
            work_order__reviewed =False ,
            work_date =work_date ,
            ).select_related ("work_order").first ()

            if _existing_entry0 is not None :









                _is_own_in_progress =(
                _existing_entry0 .work_order .status ==_WO0 .Status .IN_PROGRESS 
                and _existing_entry0 .work_order .uploaded_by_id ==cu .pk 
                )
                if not _is_own_in_progress :
                    logger .info (
                    "# [I2-DIAG-GATE0] duplicado detectado. form_action=%r "
                    "existing_entry0_pk=%r is_own_in_progress=%r",
                    _form_action ,_existing_entry0 .pk ,_is_own_in_progress ,
                    )


                    _gate0_lines =_parse_entry_lines_from_post (POST ,company )
                    _gate0_spare =_parse_spare_parts_from_post (
                    POST ,company ,entry_lines_data =_gate0_lines 
                    )
                    request .session ["pending_merge_lines"]=_serialize_pending_lines (
                    _gate0_lines ,_gate0_spare ,work_date 
                    )
                    return redirect (
                    _rev0 (
                    "panel:operator_merge",
                    kwargs ={"entry_pk":_existing_entry0 .pk },
                    )
                    )











        entry_lines_data =_parse_entry_lines_from_post (POST ,company )
        spare_parts_data =_parse_spare_parts_from_post (
        POST ,company ,entry_lines_data =entry_lines_data 
        )





        integrity_errors =[]

        if not work_date :
            integrity_errors .append (
            "La fecha del parte es obligatoria y debe tener formato DD/MM/AAAA."
            )

        if not entry_lines_data :
            integrity_errors .append ("El parte debe contener al menos un bloque de trabajo.")

        for ld in entry_lines_data :
            blk =f"Bloque {ld['line_number']}"
            if not ld ["machine_raw"]:
                integrity_errors .append (f"{blk}: el codigo de maquina es obligatorio.")
            elif ld ["machine_asset"]is None :
                integrity_errors .append (
                f"{blk}: el codigo '{ld['machine_raw']}' no se ha podido "
                f"identificar en el catalogo de flota. Corrigelo antes de guardar."
                )
            if not ld ["hc"]:
                integrity_errors .append (f"{blk}: la hora de inicio (H.C.) es obligatoria.")
            if not ld ["hf"]:
                integrity_errors .append (f"{blk}: la hora de fin (H.F.) es obligatoria.")
            if ld ["hc"]and ld ["hf"]and ld ["delta_hours"]is not None :
                if ld ["delta_hours"]<=0 :
                    integrity_errors .append (
                    f"{blk}: la H.F. debe ser posterior a la H.C. "
                    f"(Delta horas calculado: {ld['delta_hours']})."
                    )
            if not ld ["fault_description"]:
                integrity_errors .append (
                f"{blk}: la descripcion de la averia es obligatoria."
                )
            if not ld ["repair_notes"]:
                integrity_errors .append (
                f"{blk}: la descripcion de la reparacion realizada es obligatoria."
                )







        for ld in entry_lines_data :
            if ld ["machine_asset"]is not None :
                asset =ld ["machine_asset"]
                blk =f"Bloque {ld['line_number']}"
                if asset .has_odometer :
                    reading =ld .get ("odometer_reading")
                    if reading is None :
                        integrity_errors .append (
                        f"{blk}: lectura de km (odometro) obligatoria para {asset.code}."
                        )
                    elif reading ==0 and not asset .first_repair :
                        integrity_errors .append (
                        f"{blk}: la lectura de km no puede ser cero para {asset.code} "
                        f"(ya tiene partes anteriores registrados)."
                        )
                if asset .has_engine_hours :
                    reading =ld .get ("engine_hours_reading")
                    if reading is None :
                        integrity_errors .append (
                        f"{blk}: lectura de horometro motor obligatoria para {asset.code}."
                        )
                    elif reading ==0 and not asset .first_repair :
                        integrity_errors .append (
                        f"{blk}: la lectura de horometro motor no puede ser cero "
                        f"para {asset.code} (ya tiene partes anteriores registrados)."
                        )
                if asset .has_crane_hours :
                    reading =ld .get ("crane_hours_reading")
                    if reading is None :
                        integrity_errors .append (
                        f"{blk}: lectura de horometro grua obligatoria para {asset.code}."
                        )
                    elif reading ==0 and not asset .first_repair :
                        integrity_errors .append (
                        f"{blk}: la lectura de horometro grua no puede ser cero "
                        f"para {asset.code} (ya tiene partes anteriores registrados)."
                        )

        for spd in spare_parts_data :
            rep =f"Repuesto {spd['line_number']}"
            if not spd ["material"]:
                integrity_errors .append (f"{rep}: la descripcion del material es obligatoria.")
            if spd ["quantity"]is None or spd ["quantity"]<=0 :
                integrity_errors .append (f"{rep}: las unidades deben ser un numero positivo.")

        if integrity_errors :
            logger .info (
            "# [I2-DIAG-INTEGRITY] form_action=%r errors=%r",
            _form_action if "_form_action"in dir ()else POST .get ("form_action",""),
            integrity_errors ,
            )
            entradas_post =[
            {
            "idx":ld ["line_number"],
            "machine_raw":ld ["machine_raw"],
            "machine_asset":ld ["machine_asset"],
            "fault_description":ld ["fault_description"],
            "repair_notes":ld ["repair_notes"],
            "hc":ld ["hc"].strftime ("%H:%M")if ld ["hc"]else "",
            "hf":ld ["hf"].strftime ("%H:%M")if ld ["hf"]else "",
            "or_val":ld ["or_val"],
            "flags":[],
            }
            for ld in entry_lines_data 
            ]
            repuestos_post =[
            {
            "ridx":spd ["line_number"],
            "referencia":spd ["referencia"],
            "vehiculo_raw":spd ["vehiculo_raw"],
            "vehicle_asset":spd ["vehicle_asset"],
            "material":spd ["material"],
            "unidades":str (spd ["quantity"])if spd ["quantity"]is not None else "",
            "origen":spd ["source"],
            "proveedor":spd ["supplier"],
            "flags":[],
            }
            for spd in spare_parts_data 
            ]
            context =self ._get_context_base (request )
            context .update ({
            "error":" | ".join (integrity_errors ),
            "fecha":fecha_str ,
            "entradas_enriched":entradas_post ,
            "repuestos_enriched":repuestos_post ,
            "num_entradas":len (entry_lines_data ),
            "num_repuestos":len (spare_parts_data ),
            "lunch_break_start":_post_lb_start ,
            "lunch_break_end":_post_lb_end ,
            "show_lunch_break":_post_show_lunch ,
            })
            return render (request ,self .template_name ,context )





        if not POST .get ("save_confirmed"):
            entradas_post =[
            {
            "idx":ld ["line_number"],
            "machine_raw":ld ["machine_raw"],
            "machine_asset":ld ["machine_asset"],
            "fault_description":ld ["fault_description"],
            "repair_notes":ld ["repair_notes"],
            "hc":ld ["hc"].strftime ("%H:%M")if ld ["hc"]else "",
            "hf":ld ["hf"].strftime ("%H:%M")if ld ["hf"]else "",
            "or_val":ld ["or_val"],
            "flags":[],
            }
            for ld in entry_lines_data 
            ]
            repuestos_post =[
            {
            "ridx":spd ["line_number"],
            "referencia":spd ["referencia"],
            "vehiculo_raw":spd ["vehiculo_raw"],
            "vehicle_asset":spd ["vehicle_asset"],
            "material":spd ["material"],
            "unidades":str (spd ["quantity"])if spd ["quantity"]is not None else "",
            "origen":spd ["source"],
            "proveedor":spd ["supplier"],
            "flags":[],
            }
            for spd in spare_parts_data 
            ]
            context =self ._get_context_base (request )
            context .update ({
            "error":None ,
            "fecha":fecha_str ,
            "entradas_enriched":entradas_post ,
            "repuestos_enriched":repuestos_post ,
            "num_entradas":len (entry_lines_data ),
            "num_repuestos":len (spare_parts_data ),
            "lunch_break_start":_post_lb_start ,
            "lunch_break_end":_post_lb_end ,
            "show_lunch_break":_post_show_lunch ,
            })
            return render (request ,self .template_name ,context )





        from work_order_processor .validators import (
        run_intra_part_validation ,
        parse_blocks_from_post ,
        validate_inter_overlap ,
        TimeBlock ,
        )

        num_entradas_post =int (POST .get ("num_entradas",len (entry_lines_data )))
        _blocks =parse_blocks_from_post (POST ,num_entradas_post ,entry_lines_data =entry_lines_data )
        _intra =run_intra_part_validation (_blocks )

        if not _intra .ok :


            _error_msgs =[e .message for e in _intra .errors ]
            if _intra .warnings :
                _error_msgs +=[f"[AVISO] {w.message}"for w in _intra .warnings ]
            entradas_post =[
            {
            "idx":ld ["line_number"],
            "machine_raw":ld ["machine_raw"],
            "machine_asset":ld ["machine_asset"],
            "fault_description":ld ["fault_description"],
            "repair_notes":ld ["repair_notes"],
            "hc":ld ["hc"].strftime ("%H:%M")if ld ["hc"]else "",
            "hf":ld ["hf"].strftime ("%H:%M")if ld ["hf"]else "",
            "or_val":ld ["or_val"],
            "flags":[],
            }
            for ld in entry_lines_data 
            ]
            repuestos_post =[
            {
            "ridx":spd ["line_number"],
            "referencia":spd ["referencia"],
            "vehiculo_raw":spd ["vehiculo_raw"],
            "vehicle_asset":spd ["vehicle_asset"],
            "material":spd ["material"],
            "unidades":str (spd ["quantity"])if spd ["quantity"]is not None else "",
            "origen":spd ["source"],
            "proveedor":spd ["supplier"],
            "flags":[],
            }
            for spd in spare_parts_data 
            ]
            context =self ._get_context_base (request )
            context .update ({
            "error":" | ".join (_error_msgs ),
            "fecha":fecha_str ,
            "entradas_enriched":entradas_post ,
            "repuestos_enriched":repuestos_post ,
            "num_entradas":len (entry_lines_data ),
            "num_repuestos":len (spare_parts_data ),
            "lunch_break_start":_post_lb_start ,
            "lunch_break_end":_post_lb_end ,
            "show_lunch_break":_post_show_lunch ,
            })
            return render (request ,self .template_name ,context )



        _meter_warnings =[w .message for w in _intra .warnings ]













        if work_date is not None :
            from decimal import Decimal as _Dec_C 
            from ivr_config .models import WorkerAbsence as _WA_C 
            _total_hours_c =sum (
            (ld ["delta_hours"]for ld in entry_lines_data if ld ["delta_hours"]is not None ),
            _Dec_C ("0"),
            )
            _has_absence_c =_WA_C .objects .filter (
            company_user =cu ,
            start_date__lte =work_date ,
            end_date__gte =work_date ,
            ).exists ()
            if _total_hours_c <_Dec_C ("8")and not _has_absence_c :
                _missing_c =_Dec_C ("8")-_total_hours_c 
                entradas_post_c =[
                {
                "idx":ld ["line_number"],
                "machine_raw":ld ["machine_raw"],
                "machine_asset":ld ["machine_asset"],
                "fault_description":ld ["fault_description"],
                "repair_notes":ld ["repair_notes"],
                "hc":ld ["hc"].strftime ("%H:%M")if ld ["hc"]else "",
                "hf":ld ["hf"].strftime ("%H:%M")if ld ["hf"]else "",
                "or_val":ld ["or_val"],
                "flags":[],
                }
                for ld in entry_lines_data 
                ]
                repuestos_post_c =[
                {
                "ridx":spd ["line_number"],
                "referencia":spd ["referencia"],
                "vehiculo_raw":spd ["vehiculo_raw"],
                "vehicle_asset":spd ["vehicle_asset"],
                "material":spd ["material"],
                "unidades":str (spd ["quantity"])if spd ["quantity"]is not None else "",
                "origen":spd ["source"],
                "proveedor":spd ["supplier"],
                "flags":[],
                }
                for spd in spare_parts_data 
                ]
                context =self ._get_context_base (request )
                context .update ({
                "error":(
                f"La jornada del parte suma {_total_hours_c} h, "
                f"pero se requieren al menos 8 h. "
                f"Faltan {_missing_c} h para completar la jornada. "
                f"Añade los bloques de trabajo que faltan o registra "
                f"una ausencia justificada para esta fecha."
                ),
                "fecha":fecha_str ,
                "entradas_enriched":entradas_post_c ,
                "repuestos_enriched":repuestos_post_c ,
                "num_entradas":len (entry_lines_data ),
                "num_repuestos":len (spare_parts_data ),
                "min_date":_get_min_allowed_date (cu ).isoformat ()if _get_min_allowed_date (cu )else "",
                })
                return render (request ,self .template_name ,context )










        if work_date is not None and _form_action !="save_blocks":
            from ivr_config .models import WorkdaySchedule as _WDS_FA 
            from django .urls import reverse as _rev_g4fa 
            _schedule_g4fa =(
            cu .workday_schedule 
            if cu .workday_schedule_id 
            else (




            next (
            (
            _sec .workday_schedule 
            for _sec in (
            _contact_g4fa .sections 
            .filter (is_active =True ,workday_schedule__isnull =False )
            .select_related ("workday_schedule")
            .order_by ("name")
            )
            ),
            None ,
            )
            if (_contact_g4fa :=(
            Contact .objects .filter (company_user =cu )
            .prefetch_related ("sections__workday_schedule")
            .first ()
            ))is not None 
            else None 
            )or _WDS_FA .objects .filter (
            company =company ,is_default =True 
            ).first ()
            )




            _gaps_g4fa =[]if _no_lunch_break else _detect_workday_gaps (
            entry_lines_data ,_schedule_g4fa ,work_date 
            )
            if _gaps_g4fa :
                from django .db import transaction as _tx_g4fa 
                _worker_name_g4fa =(
                cu .user .get_full_name ()or cu .user .username 
                ).upper ()
                _date_tag_g4fa =work_date .strftime ("%d-%m-%Y")
                _synth_g4fa =f"{_worker_name_g4fa}_{_date_tag_g4fa}_DRAFT.pdf"
                with _tx_g4fa .atomic ():
                    _wo_draft_fa =WorkOrder (
                    company =company ,
                    uploaded_by =cu ,
                    source =WorkOrder .Source .DIGITAL ,
                    status =WorkOrder .Status .PENDING_GAPS ,
                    total_pages =1 ,
                    processed_pages =1 ,
                    reviewed =False ,
                    )
                    _wo_draft_fa .source_pdf .name =_synth_g4fa 
                    _wo_draft_fa .save ()
                    _entry_draft_fa =WorkOrderEntry .objects .create (
                    work_order =_wo_draft_fa ,
                    page_number =1 ,
                    worker_name =_worker_name_g4fa ,
                    work_date =work_date ,
                    uncertain_date =False ,
                    extraction_confidence =WorkOrderEntry .Confidence .HIGH ,
                    raw_gemini_response =None ,
                    )
                    _line_num_g4fa =1 
                    for _ld in entry_lines_data :
                        WorkOrderEntryLine .objects .create (
                        entry =_entry_draft_fa ,
                        line_number =_line_num_g4fa ,
                        machine_asset =_ld .get ("machine_asset"),
                        machine_raw =_ld .get ("machine_raw",""),
                        machine_norm ="",
                        fault_description =_ld .get ("fault_description",""),
                        repair_notes =_ld .get ("repair_notes",""),
                        hc =_ld .get ("hc"),
                        hf =_ld .get ("hf"),
                        or_val =_ld .get ("or_val",""),
                        delta_hours =_ld .get ("delta_hours"),
                        flags =[],
                        odometer_reading =_ld .get ("odometer_reading"),
                        engine_hours_reading =_ld .get ("engine_hours_reading"),
                        crane_hours_reading =_ld .get ("crane_hours_reading"),
                        )
                        _line_num_g4fa +=1 
                    from work_order_processor .models import WorkdayGap as _WDG_FA 
                    for _gap in _gaps_g4fa :
                        _WDG_FA .objects .create (
                        work_order =_wo_draft_fa ,
                        gap_type =_gap ["gap_type"],
                        gap_start =_gap ["gap_start"],
                        gap_end =_gap ["gap_end"],
                        duration_minutes =_gap ["duration_minutes"],
                        )
                request .session ["pending_gaps_wo_pk"]=_wo_draft_fa .pk 
                request .session .modified =True 
                logger .info (
                "# [FormView/Gate4] PENDING_GAPS borrador pk=%d creado. "
                "%d gap(s) detectado(s). Redirigiendo a resolución.",
                _wo_draft_fa .pk ,len (_gaps_g4fa ),
                )
                return redirect (
                _rev_g4fa (
                "panel:operator_gap_resolution",
                kwargs ={"wo_draft_pk":_wo_draft_fa .pk },
                )
                )


















        if _form_action =="save_blocks":
            logger .info (
            "# [I2-DIAG-PRE] entrando en save_blocks. work_date=%r "
            "num_entry_lines=%r _lb_start=%r _lb_end=%r",
            work_date ,len (entry_lines_data )if entry_lines_data else -1 ,
            _lb_start ,_lb_end ,
            )
            from django .db import transaction as _tx_ip 
            from work_order_processor .models import (
            WorkOrder as _WO_IP2 ,
            WorkOrderEntry as _WOE_IP2 ,
            WorkOrderEntryLine as _WOEL_IP2 ,
            SparePartLine as _SPL_IP2 ,
            )
            _ip_wo_pk_post =POST .get ("in_progress_wo_pk","").strip ()
            try :
                with _tx_ip .atomic ():
                    _worker_name_ip =(
                    cu .user .get_full_name ()or cu .user .username 
                    ).upper ()
                    _date_tag_ip =(
                    work_date .strftime ("%d-%m-%Y")if work_date else "SIN-FECHA"
                    )
                    _synth_ip =f"{_worker_name_ip}_{_date_tag_ip}.pdf"



                    if _ip_wo_pk_post :
                        try :
                            _ip_wo =_WO_IP2 .objects .get (
                            pk =int (_ip_wo_pk_post ),
                            company =company ,
                            uploaded_by =cu ,
                            status =_WO_IP2 .Status .IN_PROGRESS ,
                            )
                        except (_WO_IP2 .DoesNotExist ,ValueError ):
                            _ip_wo =None 
                    else :
                        _ip_wo =_WO_IP2 .objects .filter (
                        company =company ,
                        uploaded_by =cu ,
                        status =_WO_IP2 .Status .IN_PROGRESS ,
                        ).first ()

                    if _ip_wo is None :


                        _ip_wo =_WO_IP2 (
                        company =company ,
                        uploaded_by =cu ,
                        source =_WO_IP2 .Source .DIGITAL ,
                        status =_WO_IP2 .Status .IN_PROGRESS ,
                        total_pages =1 ,
                        processed_pages =1 ,
                        reviewed =False ,
                        )
                        _ip_wo .source_pdf .name =_synth_ip 
                        _ip_wo .save ()
                        _ip_entry =_WOE_IP2 .objects .create (
                        work_order =_ip_wo ,
                        page_number =1 ,
                        worker_name =_worker_name_ip ,
                        work_date =work_date ,
                        uncertain_date =False ,
                        extraction_confidence =_WOE_IP2 .Confidence .HIGH ,
                        raw_gemini_response =None ,
                        lunch_break_start =None if _no_lunch_break else _lb_start ,
                        lunch_break_end =None if _no_lunch_break else _lb_end ,
                        no_lunch_break =_no_lunch_break ,
                        )
                    else :




                        _ip_entry =_ip_wo .entries .first ()
                        if _ip_entry is None :
                            _ip_entry =_WOE_IP2 .objects .create (
                            work_order =_ip_wo ,
                            page_number =1 ,
                            worker_name =_worker_name_ip ,
                            work_date =work_date ,
                            uncertain_date =False ,
                            extraction_confidence =_WOE_IP2 .Confidence .HIGH ,
                            raw_gemini_response =None ,
                            lunch_break_start =None if _no_lunch_break else _lb_start ,
                            lunch_break_end =None if _no_lunch_break else _lb_end ,
                            no_lunch_break =_no_lunch_break ,
                            )
                        else :


                            _ip_entry .lunch_break_start =None if _no_lunch_break else _lb_start 
                            _ip_entry .lunch_break_end =None if _no_lunch_break else _lb_end 
                            _ip_entry .no_lunch_break =_no_lunch_break 
                            _ip_entry .save (update_fields =[
                            "lunch_break_start","lunch_break_end","no_lunch_break"
                            ])


                        _ip_entry .lines .all ().delete ()






























                    from decimal import Decimal as _Dec_ip 
                    from work_order_processor .services import _compute_delta_hours as _cdh_ip 


                    _ip_eff_lb_start =_lb_start 
                    _ip_eff_lb_end =_lb_end 
                    if not _no_lunch_break and (
                    _ip_eff_lb_start is None or _ip_eff_lb_end is None 
                    ):


                        if _post_schedule and not _post_schedule .is_intensive :
                            if _ip_eff_lb_start is None :
                                _ip_eff_lb_start =_post_schedule .end_time_morning 
                            if _ip_eff_lb_end is None :
                                _ip_eff_lb_end =_post_schedule .start_time_afternoon 
                    def _ip_to_min (t ):
                        """
                        Converts a time object to total minutes from midnight.
                        Returns 0 when t is None.
                        ---
                        Convierte un objeto time a minutos totales desde medianoche.
                        Devuelve 0 cuando t es None.
                        """
                        return t .hour *60 +t .minute if t is not None else 0 
                    def _ip_calc_overlap (hc_t ,hf_t ,lb_s ,lb_e ,no_lb ):
                        """
                        Computes the lunch overlap in minutes between a work block
                        [hc_t, hf_t] and the lunch window [lb_s, lb_e].
                        Returns 0 if no_lb is True or any value is None.
                        ---
                        Calcula el solapamiento de la pausa de comida en minutos entre
                        un bloque de trabajo [hc_t, hf_t] y la ventana [lb_s, lb_e].
                        Devuelve 0 si no_lb es True o algún valor es None.
                        """
                        if no_lb or hc_t is None or hf_t is None or lb_s is None or lb_e is None :
                            return 0 
                        return max (
                        0 ,
                        min (_ip_to_min (hf_t ),_ip_to_min (lb_e ))
                        -max (_ip_to_min (hc_t ),_ip_to_min (lb_s )),
                        )











                    _ip_pause_changed =(
                    _ip_entry .no_lunch_break !=_no_lunch_break 
                    or _ip_entry .lunch_break_start !=(
                    None if _no_lunch_break else _ip_eff_lb_start 
                    )
                    or _ip_entry .lunch_break_end !=(
                    None if _no_lunch_break else _ip_eff_lb_end 
                    )
                    )
                    if _ip_pause_changed :
                        logger .info (
                        "# [FormView/save_blocks] Pausa de comida modificada. "
                        "Recalculando líneas existentes. "
                        "entry_pk=%r old_lb_start=%r old_lb_end=%r old_no_lb=%r "
                        "new_lb_start=%r new_lb_end=%r new_no_lb=%r",
                        _ip_entry .pk ,
                        _ip_entry .lunch_break_start ,_ip_entry .lunch_break_end ,
                        _ip_entry .no_lunch_break ,
                        _ip_eff_lb_start ,_ip_eff_lb_end ,_no_lunch_break ,
                        )
                        for _ip_existing_line in _ip_entry .lines .all ():
                            _ip_ex_hc =_ip_existing_line .hc 
                            _ip_ex_hf =_ip_existing_line .hf 
                            if _ip_ex_hc is None or _ip_ex_hf is None :


                                continue 


                            _ip_gross =_cdh_ip (_ip_ex_hc ,_ip_ex_hf ,deduct_lunch =False )
                            if _ip_gross is None :
                                continue 


                            _ip_ex_overlap =_ip_calc_overlap (
                            _ip_ex_hc ,_ip_ex_hf ,
                            _ip_eff_lb_start ,_ip_eff_lb_end ,
                            _no_lunch_break ,
                            )
                            if _ip_ex_overlap >0 :
                                _ip_new_delta =_Dec_ip (str (_ip_gross ))-_Dec_ip (_ip_ex_overlap )/_Dec_ip ("60")
                                _ip_new_delta =max (_Dec_ip ("0"),_ip_new_delta )
                            else :
                                _ip_new_delta =_Dec_ip (str (_ip_gross ))
                            _ip_existing_line .delta_hours =_ip_new_delta 
                            _ip_existing_line .save (update_fields =["delta_hours"])
                            logger .info (
                            "# [FormView/save_blocks] Línea pk=%r recalculada. "
                            "hc=%r hf=%r gross=%r overlap_min=%r new_delta=%r",
                            _ip_existing_line .pk ,
                            _ip_ex_hc ,_ip_ex_hf ,_ip_gross ,
                            _ip_ex_overlap ,_ip_new_delta ,
                            )


                    _ip_created_lines ={}
                    for _ip_ld in entry_lines_data :
                        _ip_line_num =_ip_ld ["line_number"]
                        _ip_hc =_ip_ld .get ("hc")
                        _ip_hf =_ip_ld .get ("hf")
                        _ip_overlap_min =_ip_calc_overlap (
                        _ip_hc ,_ip_hf ,
                        _ip_eff_lb_start ,_ip_eff_lb_end ,
                        _no_lunch_break ,
                        )
                        _ip_delta_raw =_ip_ld ["delta_hours"]
                        if _ip_delta_raw is not None and _ip_overlap_min >0 :
                            _ip_delta_net =_Dec_ip (str (_ip_delta_raw ))-_Dec_ip (_ip_overlap_min )/_Dec_ip ("60")
                            _ip_delta_net =max (_Dec_ip ("0"),_ip_delta_net )
                        else :
                            _ip_delta_net =_ip_delta_raw 
                        _ip_line_obj =_WOEL_IP2 .objects .create (
                        entry =_ip_entry ,
                        line_number =_ip_line_num ,
                        machine_asset =_ip_ld .get ("machine_asset"),
                        machine_raw =_ip_ld .get ("machine_raw",""),
                        machine_norm =_ip_ld .get ("machine_norm",""),
                        fault_description =_ip_ld .get ("fault_description",""),
                        repair_notes =_ip_ld .get ("repair_notes",""),
                        hc =_ip_ld .get ("hc"),
                        hf =_ip_ld .get ("hf"),
                        or_val =_ip_ld .get ("or_val",""),
                        delta_hours =_ip_delta_net ,
                        flags =[],
                        odometer_reading =_ip_ld .get ("odometer_reading"),
                        engine_hours_reading =_ip_ld .get ("engine_hours_reading"),
                        crane_hours_reading =_ip_ld .get ("crane_hours_reading"),
                        )
                        _ip_created_lines [_ip_line_num ]=_ip_line_obj 



                    for _ip_spd in spare_parts_data :
                        _ip_target =next (iter (_ip_created_lines .values ()),None )
                        if _ip_target is None :
                            continue 
                        _SPL_IP2 .objects .create (
                        entry_line =_ip_target ,
                        line_number =_ip_spd ["line_number"],
                        reference =_ip_spd ["referencia"],
                        vehicle =_ip_spd ["vehicle_asset"],
                        material =_ip_spd ["material"],
                        quantity =_ip_spd ["quantity"],
                        source =_ip_spd ["source"],
                        supplier =_ip_spd ["supplier"],
                        flags =_ip_spd ["flags"],
                        )















                    from work_order_processor .models import WorkdayGap as _WDG_IP 
                    _WDG_IP .objects .filter (
                    work_order =_ip_wo ,
                    resolved =True ,
                    ).filter (
                    gap_type =_WDG_IP .GapType .GAP ,
                    ).delete ()
                    for _ip_ld_p in entry_lines_data :
                        if not _ip_ld_p .get ("is_personal"):
                            continue 
                        _ip_abs_cat =_ip_ld_p .get ("absence_category")
                        _ip_p_hc =_ip_ld_p .get ("hc")
                        _ip_p_hf =_ip_ld_p .get ("hf")
                        if _ip_p_hc is None or _ip_p_hf is None :
                            continue 
                        _ip_dur_min =max (
                        0 ,
                        (_ip_p_hf .hour *60 +_ip_p_hf .minute )
                        -(_ip_p_hc .hour *60 +_ip_p_hc .minute ),
                        )
                        _WDG_IP .objects .create (
                        work_order =_ip_wo ,
                        gap_type =_WDG_IP .GapType .GAP ,
                        gap_start =_ip_p_hc ,
                        gap_end =_ip_p_hf ,
                        duration_minutes =_ip_dur_min ,
                        absence_category =_ip_abs_cat ,
                        note =_ip_ld_p .get ("repair_notes",""),
                        resolved =True ,
                        )
                        logger .info (
                        "# [FormView/save_blocks] WorkdayGap sintético creado. "
                        "entry_pk=%r gap_start=%r gap_end=%r absence_cat=%r",
                        _ip_entry .pk ,_ip_p_hc ,_ip_p_hf ,
                        _ip_abs_cat .label if _ip_abs_cat else None ,
                        )

                logger .info (
                "# [FormView/save_blocks] WorkOrder IN_PROGRESS #%d actualizado. "
                "Bloques guardados: %d. entry_pk=%r lb_start=%r lb_end=%r no_lunch=%r",
                _ip_wo .pk ,len (entry_lines_data ),
                _ip_entry .pk ,
                _ip_entry .lunch_break_start ,
                _ip_entry .lunch_break_end ,
                _ip_entry .no_lunch_break ,
                )
            except Exception as _exc_ip :
                logger .error (
                "# [FormView/save_blocks] Error en persistencia: %s",
                _exc_ip ,exc_info =True ,
                )
                context =self ._get_context_base (request )
                context ["error"]=(
                f"Error al guardar los bloques: {_exc_ip}. "
                "Por favor, inténtalo de nuevo."
                )
                return render (request ,self .template_name ,context )

            django_messages .success (
            request ,
            f"{len(entry_lines_data)} bloque(s) guardado(s). "
            "Puedes añadir más bloques o cerrar el parte cuando termines."
            )
            return redirect ("/panel/operator/form/")










        _ip_wo_pk_close =POST .get ("in_progress_wo_pk","").strip ()
        if not _ip_wo_pk_close :
            from work_order_processor .models import WorkOrder as _WO_CL 
            _ip_wo_close =_WO_CL .objects .filter (
            company =company ,
            uploaded_by =cu ,
            status =_WO_CL .Status .IN_PROGRESS ,
            ).first ()
            if _ip_wo_close :
                _ip_wo_pk_close =str (_ip_wo_close .pk )





        edit_wo_pk =POST .get ("edit_wo_pk","").strip ()or _ip_wo_pk_close 
        if edit_wo_pk :
            try :
                _wo_orig =WorkOrder .objects .get (
                pk =int (edit_wo_pk ),
                company =company ,
                uploaded_by =cu ,
                reviewed =False ,
                source__in =[
                WorkOrder .Source .DIGITAL ,
                WorkOrder .Source .GENERATED ,
                ],
                )
                _wo_orig .delete ()
            except (WorkOrder .DoesNotExist ,ValueError ):


                pass 

        try :
            with transaction .atomic ():
                worker_name =(
                cu .user .get_full_name ()or cu .user .username 
                ).upper ()

                work_order =WorkOrder (
                company =company ,
                uploaded_by =cu ,
                source =WorkOrder .Source .DIGITAL ,
                status =WorkOrder .Status .DONE ,
                total_pages =1 ,
                processed_pages =1 ,
                reviewed =False ,
                )









                date_tag =(
                work_date .strftime ("%d-%m-%Y")if work_date else "SIN-FECHA"
                )
                synthetic_name =f"{worker_name}_{date_tag}.pdf"

                work_order .source_pdf .name =synthetic_name 
                work_order .save ()

                entry =WorkOrderEntry .objects .create (
                work_order =work_order ,
                page_number =1 ,
                worker_name =worker_name ,
                work_date =work_date ,
                uncertain_date =False ,
                extraction_confidence =WorkOrderEntry .Confidence .HIGH ,
                raw_gemini_response =None ,
                lunch_break_start =None if _no_lunch_break else _lb_start ,
                lunch_break_end =None if _no_lunch_break else _lb_end ,
                no_lunch_break =_no_lunch_break ,
                )

                created_lines ={}
                created_line_pks =[]
















                from decimal import Decimal as _Dec_lb 


                _co_eff_lb_start =_lb_start 
                _co_eff_lb_end =_lb_end 
                if not _no_lunch_break and (
                _co_eff_lb_start is None or _co_eff_lb_end is None 
                ):


                    if _post_schedule and not _post_schedule .is_intensive :
                        if _co_eff_lb_start is None :
                            _co_eff_lb_start =_post_schedule .end_time_morning 
                        if _co_eff_lb_end is None :
                            _co_eff_lb_end =_post_schedule .start_time_afternoon 
                def _co_to_min (t ):
                    """
                    Converts a time object to total minutes from midnight.
                    Returns 0 when t is None.
                    ---
                    Convierte un objeto time a minutos totales desde medianoche.
                    Devuelve 0 cuando t es None.
                    """
                    return t .hour *60 +t .minute if t is not None else 0 
                def _co_calc_overlap (hc_t ,hf_t ,lb_s ,lb_e ,no_lb ):
                    """
                    Computes the lunch overlap in minutes between a work block
                    [hc_t, hf_t] and the lunch window [lb_s, lb_e].
                    Returns 0 if no_lb is True or any value is None.
                    ---
                    Calcula el solapamiento de la pausa de comida en minutos entre
                    un bloque de trabajo [hc_t, hf_t] y la ventana [lb_s, lb_e].
                    Devuelve 0 si no_lb es True o algún valor es None.
                    """
                    if no_lb or hc_t is None or hf_t is None or lb_s is None or lb_e is None :
                        return 0 
                    return max (
                    0 ,
                    min (_co_to_min (hf_t ),_co_to_min (lb_e ))
                    -max (_co_to_min (hc_t ),_co_to_min (lb_s )),
                    )
                for ld in entry_lines_data :
                    _line_num =ld ["line_number"]
                    _co_hc =ld .get ("hc")
                    _co_hf =ld .get ("hf")
                    _overlap_min =_co_calc_overlap (
                    _co_hc ,_co_hf ,
                    _co_eff_lb_start ,_co_eff_lb_end ,
                    _no_lunch_break ,
                    )
                    _delta_raw =ld ["delta_hours"]
                    if _delta_raw is not None and _overlap_min >0 :
                        _delta_net =_Dec_lb (str (_delta_raw ))-_Dec_lb (_overlap_min )/_Dec_lb ("60")
                        _delta_net =max (_Dec_lb ("0"),_delta_net )
                    else :
                        _delta_net =_delta_raw 

                    line =WorkOrderEntryLine .objects .create (
                    entry =entry ,
                    line_number =ld ["line_number"],
                    machine_asset =ld ["machine_asset"],
                    machine_raw =ld ["machine_raw"],
                    machine_norm =ld ["machine_norm"],
                    fault_description =ld ["fault_description"],
                    repair_notes =ld ["repair_notes"],
                    hc =ld ["hc"],
                    hf =ld ["hf"],
                    or_val =ld ["or_val"],
                    delta_hours =_delta_net ,
                    flags =ld ["flags"],
                    odometer_reading =ld .get ("odometer_reading"),
                    engine_hours_reading =ld .get ("engine_hours_reading"),
                    crane_hours_reading =ld .get ("crane_hours_reading"),
                    )
                    created_lines [ld ["line_number"]]=line 
                    created_line_pks .append (line .pk )

                for spd in spare_parts_data :




                    target_line =next (iter (created_lines .values ()),None )
                    if target_line is None :
                        continue 
                    SparePartLine .objects .create (
                    entry_line =target_line ,
                    line_number =spd ["line_number"],
                    reference =spd ["referencia"],
                    vehicle =spd ["vehicle_asset"],
                    material =spd ["material"],
                    quantity =spd ["quantity"],
                    source =spd ["source"],
                    supplier =spd ["supplier"],
                    flags =spd ["flags"],
                    )





            if any (spd .get ("cg_incident")for spd in spare_parts_data ):
                WorkOrder .objects .filter (pk =work_order .pk ).update (has_cg_incident =True )
                logger .warning (
                "# [FormView] WorkOrder #%d marcado con has_cg_incident=True: "
                "al menos un repuesto tiene un CdG no resuelto en catálogo.",
                work_order .pk ,
                )

            logger .info (
            "# [FormView] WorkOrder #%d creado correctamente (Via A). "
            "Bloques: %d | Repuestos: %d.",
            work_order .pk ,
            len (entry_lines_data ),
            len (spare_parts_data ),
            )





            import json as _json_mod 
            _zero_raw =POST .get ("zero_meters_confirmed","").strip ()
            if _zero_raw :
                try :
                    _zero_data =_json_mod .loads (_zero_raw )
                    for _bIdx_str ,_meter_list in _zero_data .items ():
                        try :
                            _bIdx =int (_bIdx_str )
                        except (ValueError ,TypeError ):
                            continue 
                        _line =created_lines .get (_bIdx )
                        if _line is None :
                            continue 
                        _asset =_line .machine_asset 
                        _line_fields =[]
                        _asset_fields =[]
                        for _m in _meter_list :
                            _name =_m .get ("name","")
                            if "odometer"in _name :
                                _line .odometer_reading =None 
                                _line_fields .append ("odometer_reading")
                                if _asset and _asset .has_odometer :
                                    _asset .has_odometer =False 
                                    _asset_fields .append ("has_odometer")
                            elif "engine_hours"in _name :
                                _line .engine_hours_reading =None 
                                _line_fields .append ("engine_hours_reading")
                                if _asset and _asset .has_engine_hours :
                                    _asset .has_engine_hours =False 
                                    _asset_fields .append ("has_engine_hours")
                            elif "crane_hours"in _name :
                                _line .crane_hours_reading =None 
                                _line_fields .append ("crane_hours_reading")
                                if _asset and _asset .has_crane_hours :
                                    _asset .has_crane_hours =False 
                                    _asset_fields .append ("has_crane_hours")
                        if _line_fields :
                            _line .save (update_fields =_line_fields )
                        if _asset and _asset_fields :
                            _asset .save (update_fields =list (set (_asset_fields )))
                            logger .info (
                            "# [FormView] MachineAsset %s: flags desactivados: %s.",
                            _asset .code ,_asset_fields ,
                            )
                except (_json_mod .JSONDecodeError ,Exception )as _ze :
                    logger .warning (
                    "# [FormView] Error procesando zero_meters_confirmed: %s",_ze 
                    )



            for ld in entry_lines_data :
                _asset =ld .get ("machine_asset")
                if _asset and _asset .first_repair :
                    _asset .first_repair =False 
                    _asset .save (update_fields =["first_repair"])
                    logger .info (
                    "# [FormView] MachineAsset %s: first_repair=False.",
                    _asset .code ,
                    )

        except Exception as exc :
            logger .error (
            "# [FormView] Error en persistencia atomica: %s",exc ,exc_info =True 
            )
            context =self ._get_context_base (request )
            context ["error"]=(
            f"Error al guardar el parte: {exc}. "
            "Por favor, intentalo de nuevo o contacta con el administrador."
            )
            return render (request ,self .template_name ,context )










        for _lpk in created_line_pks :
            _line_obj =WorkOrderEntryLine .objects .filter (pk =_lpk ).first ()
            if _line_obj is None :
                continue 
            _cached =find_cached_classification (
            fault_description =_line_obj .fault_description ,
            repair_notes =_line_obj .repair_notes ,
            company =company ,
            )
            if _cached :
                WorkOrderEntryLine .objects .filter (pk =_lpk ).update (
                fault_category =_cached [0 ],
                fault_subcategory =_cached [1 ],
                )
                logger .info (
                "# [FormView] Clasificación copiada desde caché para "
                "WorkOrderEntryLine pk=%d: category=%s subcategory=%s.",
                _lpk ,_cached [0 ],_cached [1 ],
                )
            else :
                classify_fault_line .apply_async (
                args =[_lpk ],
                queue ="work_orders",
                )
                logger .info (
                "# [FormView] classify_fault_line encolada para "
                "WorkOrderEntryLine pk=%d.",
                _lpk ,
                )




        try :
            generate_work_order_excel (work_order .pk )
            logger .info (
            "# [FormView] Excel generado correctamente para WorkOrder #%d.",
            work_order .pk ,
            )
        except Exception as exc :
            logger .warning (
            "# [FormView] Excel no generado para WorkOrder #%d: %s.",
            work_order .pk ,exc ,
            )





        _inter =validate_inter_overlap (
        company_user =cu ,
        work_date =work_date ,
        blocks =_blocks ,
        exclude_work_order_pk =work_order .pk ,
        )

        if _inter .has_overlap :


            WorkOrder .objects .filter (
            pk__in =[work_order .pk ]+_inter .conflicting_ids 
            ).update (has_overlap_incident =True )
            logger .warning (
            "# [FormView] Solapamiento inter-parte detectado. "
            "WorkOrder #%d solapa con: %s.",
            work_order .pk ,
            _inter .conflicting_ids ,
            )
            django_messages .warning (
            request ,
            f"Parte #{work_order.pk} guardado con incidencia de solapamiento."
            )
            context =self ._get_context_base (request )
            context .update ({
            "overlap_incidents":True ,
            "new_work_order_pk":work_order .pk ,
            "conflicting_parts":[
            {"pk":pk ,"fecha":fecha }
            for pk ,fecha in zip (
            _inter .conflicting_ids ,
            _inter .conflicting_dates ,
            )
            ],
            "part_saved":True ,
            })
            return render (request ,self .template_name ,context )

        if _meter_warnings :
            django_messages .warning (
            request ,
            "Parte guardado con avisos de contadores: "+" | ".join (_meter_warnings ),
            )

        django_messages .success (
        request ,
        f"Parte de trabajo registrado correctamente (#{work_order.pk}). "
        f"El informe Excel está disponible en la lista de partes."
        )






        from django .urls import reverse as _reverse_co 
        if cu .role =="WORKSHOP":
            return redirect (_reverse_co ("panel:operator_history"))
        return redirect (_reverse_co ("panel:digital_work_order_list"))


class WorkOrderEntryHistoryView (WorkshopRequiredMixin ,View ):
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

    template_name ="panel/operator/history.html"

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

    def _count_working_days (self ,start_date ,end_date ):
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
        count =0 
        current =start_date 
        while current <=end_date :
            if current .weekday ()<5 :
                count +=1 
            current +=timedelta (days =1 )
        return count 

    def _enrich_work_orders_for_period (self ,qs ):
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
        result =[]
        total_hours =Decimal ("0")
        for wo in qs :
            entries_list =list (wo .entries .all ())
            first_entry =entries_list [0 ]if entries_list else None 
            work_date =first_entry .work_date if first_entry else None 
            num_bloques =sum (entry .lines .count ()for entry in entries_list )
            horas_totales =sum (
            (line .delta_hours 
            for entry in entries_list 
            for line in entry .lines .all ()
            if line .delta_hours is not None ),
            Decimal ("0"),
            )
            total_hours +=horas_totales 
            result .append ({
            "pk":wo .pk ,
            "fecha":work_date ,
            "num_bloques":num_bloques ,
            "horas_totales":horas_totales ,
            "reviewed":wo .reviewed ,
            "has_overlap_incident":wo .has_overlap_incident ,
            "source":wo .source ,
            })
        return result ,total_hours 

    def get (self ,request ,*args ,**kwargs ):
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
        from django .urls import reverse 
        from ivr_config .models import WorkerAbsence ,WorkPeriod 

        cu =request .user .company_user 
        company =cu .company 
        role =cu .role 
        today =dt_date .today ()



        if role in (CompanyUser .ROLE_ADMIN ,CompanyUser .ROLE_SUPERVISOR ):
            return redirect (reverse ("panel:work_order_admin_history"))

        active_tab =request .GET .get ("tab","current_period")






        sort_col =request .GET .get ("sort","fecha")
        sort_dir =request .GET .get ("dir","asc")
        if sort_col not in ("fecha","num_bloques","horas_totales","reviewed"):
            sort_col ="fecha"
        if sort_dir not in ("asc","desc"):
            sort_dir ="asc"








        def _base_qs ():
            return (
            WorkOrder .objects 
            .filter (
            company =company ,
            uploaded_by =cu ,
            source__in =[
            WorkOrder .Source .DIGITAL ,
            WorkOrder .Source .GENERATED ,
            ],
            )
            .prefetch_related (
            Prefetch (
            "entries",
            queryset =WorkOrderEntry .objects .prefetch_related ("lines"),
            )
            )
            .order_by ("entries__work_date")
            )




        active_period =(
        WorkPeriod .objects 
        .filter (
        company_user =cu ,
        )
        .filter (
        Q (end_date__isnull =True )|Q (end_date__gte =today )
        )
        .order_by ("-start_date")
        .first ()
        )

        current_period_list =[]
        current_period_hours =Decimal ("0")

        if active_period :


            period_qs =_base_qs ().filter (
            entries__work_date__gte =active_period .start_date ,
            )
            if active_period .end_date :
                period_qs =period_qs .filter (
                entries__work_date__lte =active_period .end_date ,
                )
            period_qs =period_qs .distinct ()
        else :




            period_qs =_base_qs ().distinct ()

        current_period_list ,current_period_hours =(
        self ._enrich_work_orders_for_period (period_qs )
        )



        def _sort_key_history (item ):
            """
            Returns the sort key for a current_period_list dict entry.
            None values sort last in both directions.
            ---
            Devuelve la clave de ordenación para un dict de current_period_list.
            Los valores None se ordenan al final en ambas direcciones.
            """
            val =item .get (sort_col )
            if val is None :


                return (1 ,None )
            return (0 ,val )

        current_period_list =sorted (
        current_period_list ,
        key =_sort_key_history ,
        reverse =(sort_dir =="desc"),
        )




        closed_periods =(
        WorkPeriod .objects 
        .filter (company_user =cu ,end_date__isnull =False ,end_date__lt =today )
        .order_by ("-start_date")
        )

        period_groups =[]
        for period in closed_periods :
            pqs =_base_qs ().filter (
            entries__work_date__gte =period .start_date ,
            entries__work_date__lte =period .end_date ,
            ).distinct ()
            wo_list ,period_hours =self ._enrich_work_orders_for_period (pqs )
            period_label =(
            period .label 
            or f"{period.start_date:%d/%m/%Y} – {period.end_date:%d/%m/%Y}"
            )
            period_groups .append ({
            "label":period_label ,
            "total_hours":period_hours ,
            "work_orders":wo_list ,
            })








        overtime_hours =Decimal ("0")
        working_days_count =0 

        if active_period :
            period_start_for_calc =active_period .start_date 
            period_end_for_calc =(
            active_period .end_date 
            if active_period .end_date and active_period .end_date <today 
            else today 
            )
        else :







            from work_order_processor .models import WorkOrderEntry as _WOE_OT 
            earliest =(
            _WOE_OT .objects 
            .filter (work_order__company =cu .company ,work_order__uploaded_by =cu )
            .order_by ("work_date")
            .values_list ("work_date",flat =True )
            .first ()
            )
            if earliest is None :


                working_days_count =0 
                overtime_hours =Decimal ("0")


                context ={
                "company":company ,
                "company_user":cu ,
                "own_presence":self ._get_own_presence (cu ),
                "active_nav":"operator_history",
                "active_tab":active_tab ,

                "sort_col":sort_col ,
                "sort_dir":sort_dir ,
                "active_period":active_period ,
                "current_period_list":current_period_list ,
                "current_period_hours":current_period_hours ,
                "period_groups":period_groups ,
                "working_days_count":0 ,
                "overtime_hours":Decimal ("0"),
                "overtime_worked_hours":Decimal ("0"),
                "absences":WorkerAbsence .objects .filter (company_user =cu ).order_by ("-start_date"),
                }
                return render (request ,self .template_name ,context )
            period_start_for_calc =earliest 
            period_end_for_calc =today 

        working_days_count =self ._count_working_days (
        period_start_for_calc ,period_end_for_calc 
        )
        expected_hours =Decimal (working_days_count )*Decimal ("8")
        overtime_hours =current_period_hours -expected_hours 




        absences =(
        WorkerAbsence .objects 
        .filter (company_user =cu )
        .order_by ("-start_date")
        )

        context ={
        "company":company ,
        "company_user":cu ,
        "own_presence":self ._get_own_presence (cu ),
        "active_nav":"operator_history",
        "active_tab":active_tab ,

        "sort_col":sort_col ,
        "sort_dir":sort_dir ,

        "active_period":active_period ,
        "current_period_list":current_period_list ,
        "current_period_hours":current_period_hours ,

        "period_groups":period_groups ,




        "working_days_count":working_days_count ,
        "overtime_hours":overtime_hours ,
        "overtime_worked_hours":current_period_hours ,

        "absences":absences ,
        }
        return render (request ,self .template_name ,context )


def _serialize_pending_lines (parsed_lines ,parsed_repuestos ,parsed_date ):
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
    serialized =[]
    for ld in parsed_lines :
        hc_val =ld ["hc"].strftime ("%H:%M")if ld ["hc"]else None 
        hf_val =ld ["hf"].strftime ("%H:%M")if ld ["hf"]else None 



        line_repuestos =[]
        for spd in parsed_repuestos :
            unit_price_val =str (spd ["unit_price"])if spd .get ("unit_price")is not None else None 
            line_repuestos .append ({
            "material":spd ["material"],
            "reference":spd ["referencia"],
            "quantity":str (spd ["quantity"])if spd ["quantity"]is not None else None ,
            "source":spd ["source"],
            "supplier":spd ["supplier"],
            "unit_price":unit_price_val ,
            })

        serialized .append ({
        "machine_raw":ld ["machine_raw"],
        "machine_asset_pk":ld ["machine_asset"].pk if ld ["machine_asset"]else None ,
        "fault_description":ld ["fault_description"],
        "repair_notes":ld ["repair_notes"],
        "hc":hc_val ,
        "hf":hf_val ,
        "delta_hours":str (ld ["delta_hours"])if ld ["delta_hours"]is not None else None ,
        "odometer_reading":str (ld ["odometer_reading"])if ld .get ("odometer_reading")is not None else None ,
        "engine_hours_reading":str (ld ["engine_hours_reading"])if ld .get ("engine_hours_reading")is not None else None ,
        "crane_hours_reading":str (ld ["crane_hours_reading"])if ld .get ("crane_hours_reading")is not None else None ,
        "repuestos":line_repuestos ,
        })

    return {
    "lines":serialized ,
    "work_date":parsed_date .isoformat ()if parsed_date else None ,
    }


def _get_min_allowed_date (cu ):









    from datetime import timedelta 
    from work_order_processor .models import WorkOrderEntry 
    last_reviewed =(
    WorkOrderEntry .objects 
    .filter (
    work_order__company =cu .company ,
    work_order__uploaded_by =cu ,
    work_order__reviewed =True ,
    )
    .order_by ("-work_date")
    .values_list ("work_date",flat =True )
    .first ()
    )
    if last_reviewed is None :
        return None 
    return last_reviewed +timedelta (days =1 )


def _detect_workday_gaps (entry_lines ,schedule ,work_date ):
    """
    Detects workday gaps and deviations in a set of parsed entry lines
    against a WorkdaySchedule reference timetable.

    Supports both intensive (single morning tract) and split-shift schedules
    (morning + afternoon tracts). The midday window in split-shift mode is
    classified as LUNCH_BREAK — not a blocking GAP — to allow the operator
    to justify it with a simplified lunch confirmation dialog.

    Checks performed (all require schedule to be non-None):
      LATE_START   — first block starts after start_time_morning + tolerance.
      EARLY_END    — last block ends before effective end_time - tolerance.
                     Intensive: end_time_morning. Split: end_time_afternoon.
      LUNCH_BREAK  — split-shift only: midday window between end_time_morning
                     and start_time_afternoon not covered by work blocks.
      GAP          — uncovered interval >= tolerance_minutes between consecutive
                     blocks, excluding the lunch window in split-shift mode.

    Lines with null hc or hf are silently ignored in all checks.

    Parameters:
        entry_lines (list[dict]) — parsed line dicts with keys 'hc' and 'hf'
                                   (time objects or HH:MM strings).
        schedule    (WorkdaySchedule | None) — reference timetable. If None,
                                   the function returns an empty list
                                   (Gate 4 disabled).
        work_date   (date)        — date of the work order (reserved for
                                   future use, e.g. holiday calendars).

    Returns:
        list[dict] — one dict per detected gap/deviation, each with keys:
            gap_type         (str)  — "GAP" | "LATE_START" | "EARLY_END"
                                      | "LUNCH_BREAK"
            gap_start        (time) — start of the uncovered interval.
            gap_end          (time) — end of the uncovered interval.
            duration_minutes (int)  — duration in minutes.

    ---

    Detecta lagunas y desviaciones de jornada en un conjunto de líneas de
    entrada parseadas contra un horario de referencia WorkdaySchedule.

    Soporta jornada intensiva (solo tramo de mañana) y turno partido
    (tramo de mañana + tarde). La ventana de mediodía en turno partido se
    clasifica como LUNCH_BREAK — no como GAP bloqueante — para permitir al
    operario justificarla con un diálogo simplificado de confirmación de comida.

    Comprobaciones realizadas (todas requieren schedule no nulo):
      LATE_START   — el primer bloque comienza después de start_time_morning
                     + tolerancia.
      EARLY_END    — el último bloque termina antes de la hora de salida
                     efectiva - tolerancia. Intensiva: end_time_morning.
                     Partida: end_time_afternoon.
      LUNCH_BREAK  — solo turno partido: ventana de mediodía entre
                     end_time_morning y start_time_afternoon no cubierta
                     por bloques de trabajo.
      GAP          — intervalo sin cubrir >= tolerance_minutes entre bloques
                     consecutivos, excluyendo la ventana de comida en turno
                     partido.

    Las líneas con hc o hf nulos se ignoran silenciosamente en todas las
    comprobaciones.

    Parámetros:
        entry_lines (list[dict]) — dicts de líneas parseadas con claves 'hc' y
                                   'hf' (objetos time o cadenas HH:MM).
        schedule    (WorkdaySchedule | None) — horario de referencia. Si es
                                   None, la función devuelve lista vacía
                                   (Gate 4 desactivado).
        work_date   (date)        — fecha del parte (reservado para uso futuro,
                                   p. ej. calendarios de festivos).

    Retorna:
        list[dict] — un dict por laguna/desviación detectada, con claves:
            gap_type         (str)  — "GAP" | "LATE_START" | "EARLY_END"
                                      | "LUNCH_BREAK"
            gap_start        (time) — inicio del intervalo sin cubrir.
            gap_end          (time) — fin del intervalo sin cubrir.
            duration_minutes (int)  — duración en minutos.
    """
    from datetime import datetime as _dt_gaps ,time as _time_gaps 



    if schedule is None :
        return []

    def _to_t (val ):
        """
        Coerces a time object or HH:MM string to a time instance.
        Returns None on failure.
        ---
        Convierte un objeto time o cadena HH:MM a una instancia time.
        Devuelve None en caso de fallo.
        """
        if val is None :
            return None 
        if hasattr (val ,"hour"):
            return val 
        try :
            return _dt_gaps .strptime (str (val ).strip (),"%H:%M").time ()
        except ValueError :
            return None 

    def _mins (t ):
        """
        Converts a time object to total minutes since midnight.
        ---
        Convierte un objeto time a minutos totales desde medianoche.
        """
        return t .hour *60 +t .minute 












    start_morning =getattr (schedule ,"start_time_morning",None )or getattr (schedule ,"start_time",None )
    end_morning =getattr (schedule ,"end_time_morning",None )or getattr (schedule ,"end_time",None )
    is_intensive =getattr (schedule ,"is_intensive",True )
    start_afternoon =None if is_intensive else getattr (schedule ,"start_time_afternoon",None )
    end_afternoon =None if is_intensive else getattr (schedule ,"end_time_afternoon",None )

    if start_morning is None or end_morning is None :


        return []



    effective_end =end_afternoon if (not is_intensive and end_afternoon )else end_morning 





    valid_blocks =[]
    for ld in entry_lines :
        hc =_to_t (ld .get ("hc"))
        hf =_to_t (ld .get ("hf"))
        if hc is not None and hf is not None :
            valid_blocks .append ((hc ,hf ))

    if not valid_blocks :
        return []

    valid_blocks .sort (key =lambda b :_mins (b [0 ]))

    gaps =[]
    tol =schedule .tolerance_minutes 





    first_hc =valid_blocks [0 ][0 ]
    if _mins (first_hc )>_mins (start_morning )+tol :
        gaps .append ({
        "gap_type":"LATE_START",
        "gap_start":start_morning ,
        "gap_end":first_hc ,
        "duration_minutes":_mins (first_hc )-_mins (start_morning ),
        })





    last_hf =valid_blocks [-1 ][1 ]
    if _mins (last_hf )<_mins (effective_end )-tol :
        gaps .append ({
        "gap_type":"EARLY_END",
        "gap_start":last_hf ,
        "gap_end":effective_end ,
        "duration_minutes":_mins (effective_end )-_mins (last_hf ),
        })












    if not is_intensive and start_afternoon and end_morning :
        lunch_start_m =_mins (end_morning )
        lunch_end_m =_mins (start_afternoon )


        lunch_covered =any (
        _mins (hf )>=lunch_start_m and _mins (hc )<=lunch_end_m 
        for hc ,hf in valid_blocks 
        )
        if not lunch_covered :
            gaps .append ({
            "gap_type":"LUNCH_BREAK",
            "gap_start":end_morning ,
            "gap_end":start_afternoon ,
            "duration_minutes":lunch_end_m -lunch_start_m ,
            })







    for i in range (len (valid_blocks )-1 ):
        hf_curr =valid_blocks [i ][1 ]
        hc_next =valid_blocks [i +1 ][0 ]
        gap_mins =_mins (hc_next )-_mins (hf_curr )

        if gap_mins <tol :
            continue 





        if not is_intensive and start_afternoon and end_morning :
            lunch_start_m =_mins (end_morning )
            lunch_end_m =_mins (start_afternoon )
            gap_start_m =_mins (hf_curr )
            gap_end_m =_mins (hc_next )
            if gap_start_m >=lunch_start_m and gap_end_m <=lunch_end_m :
                continue 

        gaps .append ({
        "gap_type":"GAP",
        "gap_start":hf_curr ,
        "gap_end":hc_next ,
        "duration_minutes":gap_mins ,
        })

    return gaps 


def _detect_overlaps (existing_lines ,new_lines ):
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

    def _t (val ):
        """
        Parses HH:MM string to time, returns None on failure.
        ---
        Parsea cadena HH:MM a time, devuelve None en fallo.
        """
        if val is None :
            return None 
        try :
            return _dt_ov .strptime (str (val ).strip (),"%H:%M").time ()
        except ValueError :
            return None 

    conflicts =[]
    for idx_e ,existing_line in enumerate (existing_lines ,start =1 ):
        hc_e =existing_line .hc 
        hf_e =existing_line .hf 
        if hc_e is None or hf_e is None :
            continue 
        for idx_n ,new_line in enumerate (new_lines ,start =1 ):
            hc_n =_t (new_line .get ("hc"))
            hf_n =_t (new_line .get ("hf"))
            if hc_n is None or hf_n is None :
                continue 


            if hc_e <hf_n and hc_n <hf_e :
                conflicts .append ((
                idx_e ,
                idx_n ,
                hc_e .strftime ("%H:%M"),
                hf_e .strftime ("%H:%M"),
                hc_n .strftime ("%H:%M"),
                hf_n .strftime ("%H:%M"),
                ))
    return conflicts 


class WorkOrderEntryMergeView (WorkshopRequiredMixin ,View ):
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

    template_name ="panel/operator/merge_entry.html"





    def _get_pending (self ,request ):
        """
        Returns the pending_merge_lines dict from the session, or None.
        ---
        Devuelve el dict pending_merge_lines de la sesion, o None.
        """
        return request .session .get ("pending_merge_lines")

    def _clear_pending (self ,request ):
        """
        Removes pending_merge_lines from the session.
        ---
        Elimina pending_merge_lines de la sesion.
        """
        request .session .pop ("pending_merge_lines",None )
        request .session .modified =True 

    def _resolve_entry (self ,entry_pk ,company ,cu ):
        """
        Retrieves the WorkOrderEntry by pk, scoped to operator company
        and user. Returns None if not found or inaccessible.
        ---
        Recupera el WorkOrderEntry por pk, acotado a empresa y usuario
        del operario. Devuelve None si no existe o no es accesible.
        """
        try :
            return WorkOrderEntry .objects .select_related ("work_order").get (
            pk =entry_pk ,
            work_order__company =company ,
            work_order__uploaded_by =cu ,
            work_order__source__in =[
            WorkOrder .Source .DIGITAL ,
            WorkOrder .Source .GENERATED ,
            ],
            work_order__reviewed =False ,
            )
        except WorkOrderEntry .DoesNotExist :
            return None 

    def _parse_time_str (self ,val ):
        """
        Parses HH:MM string to datetime.time, returns None on failure.
        ---
        Parsea cadena HH:MM a datetime.time, devuelve None en fallo.
        """
        from datetime import time as _time 
        if not val :
            return None 
        try :
            parts =str (val ).strip ().split (":")
            return _time (int (parts [0 ]),int (parts [1 ]))
        except (ValueError ,IndexError ):
            return None 

    def _to_decimal (self ,val ):
        """
        Converts str/int/float to Decimal, returns None on failure.
        ---
        Convierte str/int/float a Decimal, devuelve None en fallo.
        """
        from decimal import Decimal ,InvalidOperation 
        if val is None :
            return None 
        try :
            return Decimal (str (val ))
        except InvalidOperation :
            return None 

    def _parse_edited_hc_hf (self ,POST ,prefix ,count ):
        """
        Parses operator-edited hc/hf from POST for a set of lines
        identified by prefix and count (1-based).
        Returns a list of dicts: [{hc: HH:MM|None, hf: HH:MM|None}].
        ---
        Parsea hc/hf editados del POST para un conjunto de lineas
        identificadas por prefix y count (base 1).
        """
        result =[]
        for i in range (1 ,count +1 ):
            hc_raw =POST .get (f"{prefix}{i}_hc","").strip ()or None 
            hf_raw =POST .get (f"{prefix}{i}_hf","").strip ()or None 
            result .append ({"hc":hc_raw ,"hf":hf_raw })
        return result 

    def _build_context (self ,company ,cu ,existing_entry ,existing_lines ,
    new_lines ,work_date_iso ,conflicts ,merge_error =None ):
        """
        Builds the template context dict for the merge view.
        ---
        Construye el dict de contexto del template para la vista de merge.
        """
        return {
        "company":company ,
        "company_user":cu ,
        "active_nav":"operator_dashboard",
        "existing_entry":existing_entry ,
        "existing_lines":existing_lines ,
        "new_lines":new_lines ,
        "work_date":work_date_iso ,
        "conflicts":conflicts ,
        "has_conflicts":bool (conflicts ),
        "merge_error":merge_error ,
        }

    def _create_lines_from_session (self ,new_lines ,edited_new ,
    target_entry ,start_line_number ,company ):
        """
        Creates WorkOrderEntryLine and SparePartLine records from the
        session pending data inside an already-open atomic block.
        edited_new may provide operator-corrected hc/hf values.
        ---
        Crea WorkOrderEntryLine y SparePartLine desde los datos pendientes
        de la sesion dentro de un bloque atomico ya abierto.
        edited_new puede aportar hc/hf corregidos por el operario.
        """
        from fleet .models import MachineAsset 
        from work_order_processor .models import SparePartLine 
        from work_order_processor .services import (
        _normalise_machine_code ,
        _compute_delta_hours ,
        )

        for idx ,line_data in enumerate (new_lines ):
            edits =edited_new [idx ]if idx <len (edited_new )else {}
            hc_str =edits .get ("hc")or line_data .get ("hc")
            hf_str =edits .get ("hf")or line_data .get ("hf")
            hc_val =self ._parse_time_str (hc_str )
            hf_val =self ._parse_time_str (hf_str )
            delta =_compute_delta_hours (hc_val ,hf_val ,deduct_lunch =False )



            asset =None 
            _asset_pk =line_data .get ("machine_asset_pk")
            if _asset_pk is not None :
                try :
                    asset =MachineAsset .objects .get (
                    pk =_asset_pk ,company =company 
                    )
                except MachineAsset .DoesNotExist :
                    pass 

            machine_raw =line_data .get ("machine_raw","")
            machine_norm =_normalise_machine_code (machine_raw )

            new_line =WorkOrderEntryLine .objects .create (
            entry =target_entry ,
            line_number =start_line_number +idx ,
            machine_asset =asset ,
            machine_raw =machine_raw ,
            machine_norm =machine_norm or "",
            fault_description =line_data .get ("fault_description",""),
            repair_notes =line_data .get ("repair_notes",""),
            hc =hc_val ,
            hf =hf_val ,
            or_val ="",
            delta_hours =delta ,
            flags =[],
            odometer_reading =self ._to_decimal (line_data .get ("odometer_reading")),
            engine_hours_reading =self ._to_decimal (line_data .get ("engine_hours_reading")),
            crane_hours_reading =self ._to_decimal (line_data .get ("crane_hours_reading")),
            )



            for rep_idx ,rep in enumerate (line_data .get ("repuestos",[]),start =1 ):
                SparePartLine .objects .create (
                entry_line =new_line ,
                line_number =rep_idx ,
                reference =rep .get ("reference",""),
                vehicle =None ,
                material =rep .get ("material",""),
                quantity =self ._to_decimal (rep .get ("quantity")),
                source =rep .get ("source","WAREHOUSE"),
                supplier =rep .get ("supplier",""),
                flags =[],
                )





    def get (self ,request ,entry_pk ,*args ,**kwargs ):
        """
        Renders the merge resolution page. Detects initial overlaps.
        Redirects to operator history with an error if session data is
        missing or the entry is inaccessible.
        ---
        Renderiza la pagina de resolucion de merge. Detecta solapamientos
        iniciales. Redirige al historial si faltan datos o el entry no
        es accesible.
        """
        from django .urls import reverse 

        cu =request .user .company_user 
        company =cu .company 

        pending =self ._get_pending (request )
        if not pending :
            django_messages .error (
            request ,
            "No hay datos de parte pendiente en sesion. "
            "El formulario ha expirado o fue enviado ya.",
            )
            return redirect (reverse ("panel:operator_history"))

        existing_entry =self ._resolve_entry (entry_pk ,company ,cu )
        if existing_entry is None :
            self ._clear_pending (request )
            django_messages .error (
            request ,
            "El parte existente no se ha encontrado o no es accesible.",
            )
            return redirect (reverse ("panel:operator_history"))

        existing_lines =list (existing_entry .lines .order_by ("line_number"))
        new_lines =pending .get ("lines",[])
        work_date_iso =pending .get ("work_date")

        conflicts =_detect_overlaps (existing_lines ,new_lines )

        context =self ._build_context (
        company ,cu ,existing_entry ,existing_lines ,
        new_lines ,work_date_iso ,conflicts ,
        )
        return render (request ,self .template_name ,context )

    def post (self ,request ,entry_pk ,*args ,**kwargs ):
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
        from django .db import transaction 
        from django .urls import reverse 
        from work_order_processor .services import generate_work_order_excel 

        cu =request .user .company_user 
        company =cu .company 

        pending =self ._get_pending (request )
        if not pending :
            django_messages .error (
            request ,
            "No hay datos de parte pendiente en sesion. "
            "El formulario ha expirado o fue enviado ya.",
            )
            return redirect (reverse ("panel:operator_history"))

        existing_entry =self ._resolve_entry (entry_pk ,company ,cu )
        if existing_entry is None :
            self ._clear_pending (request )
            django_messages .error (
            request ,
            "El parte existente no se ha encontrado o no es accesible.",
            )
            return redirect (reverse ("panel:operator_history"))

        merge_action =request .POST .get ("merge_action","").strip ()
        existing_lines =list (existing_entry .lines .order_by ("line_number"))
        new_lines =pending .get ("lines",[])
        work_date_iso =pending .get ("work_date")




        if merge_action =="discard_new":
            self ._clear_pending (request )
            django_messages .success (
            request ,
            "Parte nuevo descartado. Se conserva el parte existente.",
            )
            return redirect (reverse ("panel:operator_history"))















        if merge_action in ("discard_existing","merge"):
            _work_date_g4mv =None 
            if work_date_iso :
                try :
                    _work_date_g4mv =_dtp .strptime (work_date_iso ,"%Y-%m-%d").date ()
                except ValueError :
                    pass 

            if _work_date_g4mv is not None :
                from ivr_config .models import WorkdaySchedule as _WDS_MV 
                from django .urls import reverse as _rev_g4mv 
                _schedule_g4mv =(
                cu .workday_schedule 
                if cu .workday_schedule_id 
                else (




                next (
                (
                _sec .workday_schedule 
                for _sec in (
                _contact_g4mv .sections 
                .filter (is_active =True ,workday_schedule__isnull =False )
                .select_related ("workday_schedule")
                .order_by ("name")
                )
                ),
                None ,
                )
                if (_contact_g4mv :=(
                Contact .objects .filter (company_user =cu )
                .prefetch_related ("sections__workday_schedule")
                .first ()
                ))is not None 
                else None 
                )or _WDS_MV .objects .filter (
                company =company ,is_default =True 
                ).first ()
                )
                _gaps_g4mv =_detect_workday_gaps (
                new_lines ,_schedule_g4mv ,_work_date_g4mv 
                )
                if _gaps_g4mv :
                    from django .db import transaction as _tx_g4mv 
                    _worker_name_g4mv =(
                    cu .user .get_full_name ()or cu .user .username 
                    ).upper ()
                    _date_tag_g4mv =_work_date_g4mv .strftime ("%d-%m-%Y")
                    _synth_g4mv =(
                    f"{_worker_name_g4mv}_{_date_tag_g4mv}_MERGE_DRAFT.pdf"
                    )
                    with _tx_g4mv .atomic ():
                        _wo_draft_mv =WorkOrder (
                        company =company ,
                        uploaded_by =cu ,
                        source =WorkOrder .Source .DIGITAL ,
                        status =WorkOrder .Status .PENDING_GAPS ,
                        total_pages =1 ,
                        processed_pages =1 ,
                        reviewed =False ,
                        )
                        _wo_draft_mv .source_pdf .name =_synth_g4mv 
                        _wo_draft_mv .save ()
                        _entry_draft_mv =WorkOrderEntry .objects .create (
                        work_order =_wo_draft_mv ,
                        page_number =1 ,
                        worker_name =_worker_name_g4mv ,
                        work_date =_work_date_g4mv ,
                        uncertain_date =False ,
                        extraction_confidence =WorkOrderEntry .Confidence .HIGH ,
                        raw_gemini_response =None ,
                        )
                        _line_num_g4mv =1 
                        for _nd in new_lines :
                            _ma_pk =_nd .get ("machine_asset_pk")
                            _ma_mv =None 
                            if _ma_pk :
                                try :
                                    from fleet .models import MachineAsset as _MA_MV 
                                    _ma_mv =_MA_MV .objects .filter (
                                    pk =_ma_pk ,company =company 
                                    ).first ()
                                except Exception :
                                    pass 
                            from datetime import datetime as _dtm_mv 
                            def _tp (v ):
                                if not v :
                                    return None 
                                try :
                                    return _dtm_mv .strptime (str (v ).strip (),"%H:%M").time ()
                                except ValueError :
                                    return None 
                            from decimal import Decimal as _Dec_mv 
                            WorkOrderEntryLine .objects .create (
                            entry =_entry_draft_mv ,
                            line_number =_line_num_g4mv ,
                            machine_asset =_ma_mv ,
                            machine_raw =_nd .get ("machine_raw",""),
                            machine_norm ="",
                            fault_description =_nd .get ("fault_description",""),
                            repair_notes =_nd .get ("repair_notes",""),
                            hc =_tp (_nd .get ("hc")),
                            hf =_tp (_nd .get ("hf")),
                            or_val ="",
                            delta_hours =(
                            _Dec_mv (_nd ["delta_hours"])
                            if _nd .get ("delta_hours")else None 
                            ),
                            flags =[],
                            odometer_reading =(
                            _Dec_mv (_nd ["odometer_reading"])
                            if _nd .get ("odometer_reading")else None 
                            ),
                            engine_hours_reading =(
                            _Dec_mv (_nd ["engine_hours_reading"])
                            if _nd .get ("engine_hours_reading")else None 
                            ),
                            crane_hours_reading =(
                            _Dec_mv (_nd ["crane_hours_reading"])
                            if _nd .get ("crane_hours_reading")else None 
                            ),
                            )
                            _line_num_g4mv +=1 
                        from work_order_processor .models import WorkdayGap as _WDG_MV 
                        for _gap in _gaps_g4mv :
                            _WDG_MV .objects .create (
                            work_order =_wo_draft_mv ,
                            gap_type =_gap ["gap_type"],
                            gap_start =_gap ["gap_start"],
                            gap_end =_gap ["gap_end"],
                            duration_minutes =_gap ["duration_minutes"],
                            )
                    request .session ["pending_gaps_wo_pk"]=_wo_draft_mv .pk 
                    request .session .modified =True 
                    logger .info (
                    "# [MergeView/Gate4] PENDING_GAPS borrador pk=%d creado. "
                    "%d gap(s) detectado(s). Redirigiendo a resolución.",
                    _wo_draft_mv .pk ,len (_gaps_g4mv ),
                    )
                    return redirect (
                    _rev_g4mv (
                    "panel:operator_gap_resolution",
                    kwargs ={"wo_draft_pk":_wo_draft_mv .pk },
                    )
                    )




        if merge_action =="discard_existing":
            work_date =None 
            if work_date_iso :
                try :
                    work_date =_dtp .strptime (work_date_iso ,"%Y-%m-%d").date ()
                except ValueError :
                    pass 

            try :
                with transaction .atomic ():


                    existing_entry .work_order .delete ()

                    worker_name =(
                    cu .user .get_full_name ()or cu .user .username 
                    ).upper ()
                    date_tag =(
                    work_date .strftime ("%d-%m-%Y")if work_date else "SIN-FECHA"
                    )
                    synthetic_name =f"{worker_name}_{date_tag}.pdf"

                    new_wo =WorkOrder (
                    company =company ,
                    uploaded_by =cu ,
                    source =WorkOrder .Source .DIGITAL ,
                    status =WorkOrder .Status .DONE ,
                    total_pages =1 ,
                    processed_pages =1 ,
                    reviewed =False ,
                    )
                    new_wo .source_pdf .name =synthetic_name 
                    new_wo .save ()

                    new_entry =WorkOrderEntry .objects .create (
                    work_order =new_wo ,
                    page_number =1 ,
                    worker_name =worker_name ,
                    work_date =work_date ,
                    uncertain_date =False ,
                    extraction_confidence =WorkOrderEntry .Confidence .HIGH ,
                    raw_gemini_response =None ,
                    )



                    self ._create_lines_from_session (
                    new_lines ,[],new_entry ,1 ,company 
                    )

            except Exception as exc :
                logger .error (
                "# [MergeView] Error en discard_existing: %s",exc ,exc_info =True 
                )
                django_messages .error (
                request ,
                f"Error al procesar el merge: {exc}. Intentalo de nuevo.",
                )
                return redirect (reverse ("panel:operator_history"))

            self ._clear_pending (request )





            for _line in new_entry .lines .all ():
                _cached =find_cached_classification (
                fault_description =_line .fault_description ,
                repair_notes =_line .repair_notes ,
                company =company ,
                )
                if _cached :
                    WorkOrderEntryLine .objects .filter (pk =_line .pk ).update (
                    fault_category =_cached [0 ],
                    fault_subcategory =_cached [1 ],
                    )
                    logger .info (
                    "# [MergeView/discard_existing] Clasificación copiada "
                    "desde caché para WorkOrderEntryLine pk=%d: "
                    "category=%s subcategory=%s.",
                    _line .pk ,_cached [0 ],_cached [1 ],
                    )
                else :
                    classify_fault_line .apply_async (
                    args =[_line .pk ],
                    queue ="work_orders",
                    )
                    logger .info (
                    "# [MergeView/discard_existing] classify_fault_line "
                    "encolada para WorkOrderEntryLine pk=%d.",
                    _line .pk ,
                    )

            try :
                generate_work_order_excel (new_wo .pk )
            except Exception as exc :
                logger .warning (
                "# [MergeView] Excel no generado para WorkOrder #%d: %s",
                new_wo .pk ,exc ,
                )
            django_messages .success (
            request ,
            "Parte existente sustituido correctamente. "
            "El nuevo parte ha sido registrado.",
            )
            return redirect (reverse ("panel:operator_history"))




        if merge_action =="merge":
            edited_existing =self ._parse_edited_hc_hf (
            request .POST ,"existing_line_",len (existing_lines )
            )
            edited_new =self ._parse_edited_hc_hf (
            request .POST ,"new_line_",len (new_lines )
            )



            class _LineCopy :
                pass 

            existing_copies =[]
            for line ,edits in zip (existing_lines ,edited_existing ):
                copy =_LineCopy ()
                copy .hc =self ._parse_time_str (edits ["hc"])if edits ["hc"]else line .hc 
                copy .hf =self ._parse_time_str (edits ["hf"])if edits ["hf"]else line .hf 
                existing_copies .append (copy )

            new_copies =[]
            for nd ,edits in zip (new_lines ,edited_new ):
                new_copies .append ({
                "hc":edits ["hc"]if edits ["hc"]else nd .get ("hc"),
                "hf":edits ["hf"]if edits ["hf"]else nd .get ("hf"),
                })

            conflicts =_detect_overlaps (existing_copies ,new_copies )

            if conflicts :
                context =self ._build_context (
                company ,cu ,existing_entry ,existing_lines ,
                new_lines ,work_date_iso ,conflicts ,
                merge_error =(
                "No es posible fusionar: existen solapamientos horarios. "
                "Edita los horarios para resolver los conflictos."
                ),
                )
                return render (request ,self .template_name ,context )



            try :
                with transaction .atomic ():
                    start_number =existing_entry .lines .count ()+1 
                    self ._create_lines_from_session (
                    new_lines ,edited_new ,existing_entry ,start_number ,company 
                    )
            except Exception as exc :
                logger .error (
                "# [MergeView] Error en merge: %s",exc ,exc_info =True 
                )
                django_messages .error (
                request ,
                f"Error al fusionar el parte: {exc}. Intentalo de nuevo.",
                )
                return redirect (reverse ("panel:operator_history"))

            self ._clear_pending (request )







            _total_lines =existing_entry .lines .count ()
            _new_start_nr =_total_lines -len (new_lines )+1 
            for _line in existing_entry .lines .filter (line_number__gte =_new_start_nr ):
                _cached =find_cached_classification (
                fault_description =_line .fault_description ,
                repair_notes =_line .repair_notes ,
                company =company ,
                )
                if _cached :
                    WorkOrderEntryLine .objects .filter (pk =_line .pk ).update (
                    fault_category =_cached [0 ],
                    fault_subcategory =_cached [1 ],
                    )
                    logger .info (
                    "# [MergeView/merge] Clasificación copiada desde caché "
                    "para WorkOrderEntryLine pk=%d: "
                    "category=%s subcategory=%s.",
                    _line .pk ,_cached [0 ],_cached [1 ],
                    )
                else :
                    classify_fault_line .apply_async (
                    args =[_line .pk ],
                    queue ="work_orders",
                    )
                    logger .info (
                    "# [MergeView/merge] classify_fault_line encolada "
                    "para WorkOrderEntryLine pk=%d.",
                    _line .pk ,
                    )

            try :
                generate_work_order_excel (existing_entry .work_order .pk )
            except Exception as exc :
                logger .warning (
                "# [MergeView] Excel no regenerado para WorkOrder #%d: %s",
                existing_entry .work_order .pk ,exc ,
                )
            django_messages .success (
            request ,
            f"Parte fusionado correctamente. Tareas anadidas al parte del "
            f"{work_date_iso or 'fecha desconocida'}.",
            )
            return redirect (reverse ("panel:operator_history"))



        django_messages .warning (
        request ,
        "Accion de merge no reconocida. No se ha realizado ningun cambio.",
        )
        return redirect (reverse ("panel:operator_history"))


class WorkdayGapResolutionView (WorkshopRequiredMixin ,View ):
    """
    Allows a WORKSHOP operator to justify each workday gap detected by Gate 4
    before the draft work order is promoted from PENDING_GAPS to DONE.

    GET  /panel/operator/gaps/<int:wo_draft_pk>/
         Retrieves the pending WorkdayGap records for the draft WorkOrder and
         renders the resolution form. Each unresolved gap is presented with an
         AbsenceCategory selector and an optional note field.
         Redirects to operator_history if the draft is not found or does not
         belong to the authenticated operator.

    POST /panel/operator/gaps/<int:wo_draft_pk>/
         Validates that every gap has an AbsenceCategory assigned, and that a
         note is provided when AbsenceCategory.requires_note=True.
         On success:
           - Persists AbsenceCategory + note on each WorkdayGap.
           - Marks all gaps as resolved=True.
           - Promotes the WorkOrder from PENDING_GAPS to DONE.
           - Clears the pending_gaps_wo_pk session key.
           - Enqueues classify_fault_line for each entry line.
           - Generates the Excel report synchronously.
           - Redirects to operator_history with a success message.
         The "Volver y editar" action (POST field back_to_form=1) discards
         the draft WorkOrder and redirects to operator_dashboard so the
         operator can resubmit with corrected times.

    ---

    Permite a un operario WORKSHOP justificar cada laguna de jornada detectada
    por Gate 4 antes de que el borrador de parte sea promovido de PENDING_GAPS
    a DONE.

    GET  /panel/operator/gaps/<int:wo_draft_pk>/
         Recupera los registros WorkdayGap pendientes del WorkOrder borrador y
         renderiza el formulario de resolución. Cada gap no resuelto se presenta
         con un selector de AbsenceCategory y un campo de nota opcional.
         Redirige a operator_history si el borrador no se encuentra o no
         pertenece al operario autenticado.

    POST /panel/operator/gaps/<int:wo_draft_pk>/
         Valida que cada gap tenga una AbsenceCategory asignada, y que se
         proporcione nota cuando AbsenceCategory.requires_note=True.
         En caso de éxito:
           - Persiste AbsenceCategory + nota en cada WorkdayGap.
           - Marca todos los gaps como resolved=True.
           - Promueve el WorkOrder de PENDING_GAPS a DONE.
           - Limpia la clave de sesión pending_gaps_wo_pk.
           - Encola classify_fault_line para cada línea del entry.
           - Genera el informe Excel de forma síncrona.
           - Redirige a operator_history con mensaje de éxito.
         La acción "Volver y editar" (campo POST back_to_form=1) descarta el
         borrador WorkOrder y redirige a operator_dashboard para que el operario
         pueda reenviar con horas corregidas.
    """

    template_name ="panel/operator/gap_resolution.html"

    def _get_draft (self ,wo_draft_pk ,company ,cu ):
        """
        Resolves the PENDING_GAPS WorkOrder draft by pk, scoped to the
        authenticated operator and company. Returns None if not found.
        ---
        Resuelve el borrador WorkOrder PENDING_GAPS por pk, acotado al operario
        autenticado y la empresa. Devuelve None si no se encuentra.
        """
        return WorkOrder .objects .filter (
        pk =wo_draft_pk ,
        company =company ,
        uploaded_by =cu ,
        status =WorkOrder .Status .PENDING_GAPS ,
        source__in =[WorkOrder .Source .DIGITAL ,WorkOrder .Source .GENERATED ],
        ).first ()

    def get (self ,request ,wo_draft_pk ,*args ,**kwargs ):
        """
        Renders the gap resolution form for the given PENDING_GAPS draft.
        ---
        Renderiza el formulario de resolución de gaps para el borrador dado.
        """
        from django .urls import reverse 
        from ivr_config .models import AbsenceCategory 
        from work_order_processor .models import WorkdayGap 

        cu =request .user .company_user 
        company =cu .company 

        draft =self ._get_draft (wo_draft_pk ,company ,cu )
        if draft is None :
            django_messages .error (
            request ,
            "El parte borrador no se ha encontrado o ya fue procesado.",
            )
            return redirect (reverse ("panel:operator_history"))

        gaps =WorkdayGap .objects .filter (
        work_order =draft ,resolved =False 
        ).order_by ("gap_start")

        absence_categories =AbsenceCategory .objects .filter (
        company =company ,is_active =True 
        ).order_by ("order","label")

















        first_entry =draft .entries .first ()
        raw_lines =(
        list (first_entry .lines .order_by ("hc"))
        if first_entry else []
        )



        gaps_list =list (gaps )
        gap_by_start ={g .gap_start :g for g in gaps_list }













        for line in raw_lines :
            matched =gap_by_start .get (line .hf )









            line .next_gap =(
            matched 
            if matched and matched .gap_type =="GAP"
            else None 
            )








        late_start_gap =next (
        (g for g in gaps_list if g .gap_type =="LATE_START"),None 
        )
        early_end_gap =next (
        (g for g in gaps_list if g .gap_type =="EARLY_END"),None 
        )

        context ={
        "company":company ,
        "company_user":cu ,
        "active_nav":"operator_dashboard",
        "draft":draft ,
        "gaps":gaps_list ,
        "absence_categories":absence_categories ,
        "work_date":first_entry .work_date if first_entry else None ,
        "entry_lines":raw_lines ,
        "late_start_gap":late_start_gap ,
        "early_end_gap":early_end_gap ,
        }
        return render (request ,self .template_name ,context )

    def post (self ,request ,wo_draft_pk ,*args ,**kwargs ):
        """
        Processes the gap resolution form. On "Volver y editar" discards
        the draft. Otherwise validates and persists all gap justifications,
        promotes the WorkOrder to DONE and enqueues post-processing tasks.
        ---
        Procesa el formulario de resolución de gaps. Con "Volver y editar"
        descarta el borrador. Si no, valida y persiste todas las justificaciones,
        promueve el WorkOrder a DONE y encola las tareas de post-procesamiento.
        """
        from django .urls import reverse 
        from django .db import transaction 
        from ivr_config .models import AbsenceCategory 
        from work_order_processor .models import WorkdayGap 
        from work_order_processor .services import (
        generate_work_order_excel ,
        find_cached_classification ,
        )

        cu =request .user .company_user 
        company =cu .company 

        draft =self ._get_draft (wo_draft_pk ,company ,cu )
        if draft is None :
            django_messages .error (
            request ,
            "El parte borrador no se ha encontrado o ya fue procesado.",
            )
            return redirect (reverse ("panel:operator_history"))















        if request .POST .get ("back_to_form"):
            from django .urls import reverse as _rev_btf 
            from work_order_processor .models import WorkOrder as _WO_BTF 




            _WO_BTF .objects .filter (pk =draft .pk ).update (
            status =_WO_BTF .Status .DONE ,
            )
            request .session .pop ("pending_gaps_wo_pk",None )
            request .session .modified =True 
            django_messages .info (
            request ,
            "Puedes corregir las horas del parte y enviarlo de nuevo.",
            )
            return redirect (
            _rev_btf ("panel:operator_form_edit",kwargs ={"wo_pk":draft .pk })
            )














        gaps =list (
        WorkdayGap .objects .filter (
        work_order =draft ,resolved =False 
        ).order_by ("gap_start")
        )

        validation_errors =[]
        resolutions =[]

        for gap in gaps :
            label_gap =f"Laguna {gap.gap_start:%H:%M}–{gap.gap_end:%H:%M}"

            if gap .gap_type ==WorkdayGap .GapType .LUNCH_BREAK :




                lunch_had_raw =request .POST .get (f"gap_{gap.pk}_lunch_had","").strip ()
                note_val =request .POST .get (f"gap_{gap.pk}_note","").strip ()
                lunch_time_raw =request .POST .get (f"gap_{gap.pk}_lunch_time","").strip ()

                if lunch_had_raw not in ("yes","no"):
                    validation_errors .append (
                    f"{label_gap}: debes indicar si has parado a comer."
                    )
                    continue 

                lunch_had =lunch_had_raw =="yes"

                if not lunch_had and not note_val :
                    validation_errors .append (
                    f"{label_gap}: si no has parado a comer, debes indicar el motivo."
                    )
                    continue 



                lunch_time =None 
                if lunch_had and lunch_time_raw :
                    from datetime import datetime as _dt_lt 
                    try :
                        lunch_time =_dt_lt .strptime (lunch_time_raw ,"%H:%M").time ()
                    except ValueError :
                        lunch_time =None 

                resolutions .append ((gap ,{
                "type":"lunch",
                "lunch_had":lunch_had ,
                "lunch_time":lunch_time ,
                "note":note_val ,
                }))

            else :




                field_cat =f"gap_{gap.pk}_category"
                field_note =f"gap_{gap.pk}_note"

                cat_pk_raw =request .POST .get (field_cat ,"").strip ()
                note_val =request .POST .get (field_note ,"").strip ()

                if not cat_pk_raw :
                    validation_errors .append (
                    f"{label_gap}: debes seleccionar un motivo de ausencia."
                    )
                    continue 

                try :
                    absence_cat =AbsenceCategory .objects .get (
                    pk =int (cat_pk_raw ),company =company ,is_active =True 
                    )
                except (AbsenceCategory .DoesNotExist ,ValueError ,TypeError ):
                    validation_errors .append (
                    f"{label_gap}: la categoría seleccionada no es válida."
                    )
                    continue 

                if absence_cat .requires_note and not note_val :
                    validation_errors .append (
                    f"{label_gap}: la categoría '{absence_cat.label}' "
                    f"requiere una nota explicativa."
                    )
                    continue 

                resolutions .append ((gap ,{
                "type":"standard",
                "absence_cat":absence_cat ,
                "note":note_val ,
                }))

        if validation_errors :


            from ivr_config .models import AbsenceCategory as _AC 
            absence_categories =_AC .objects .filter (
            company =company ,is_active =True 
            ).order_by ("order","label")
            first_entry =draft .entries .first ()
            context ={
            "company":company ,
            "company_user":cu ,
            "active_nav":"operator_dashboard",
            "draft":draft ,
            "gaps":gaps ,
            "absence_categories":absence_categories ,
            "work_date":first_entry .work_date if first_entry else None ,
            "entry_lines":list (first_entry .lines .order_by ("hc"))if first_entry else [],
            "errors":validation_errors ,
            }
            return render (request ,self .template_name ,context )



















        from work_order_processor .management .commands .seed_personal_asset import (
        PERSONAL_ASSET_CODE as _PERSONAL_CODE_GR ,
        )
        from fleet .models import MachineAsset as _MA_GR 
        from work_order_processor .services import _compute_delta_hours as _cdh_gr 
        try :
            _personal_asset_gr =_MA_GR .objects .get (
            code__iexact =_PERSONAL_CODE_GR ,company =company 
            )
        except _MA_GR .DoesNotExist :
            _personal_asset_gr =None 
            logger .warning (
            "# [GapResolutionView] Activo PERSONAL no encontrado para empresa pk=%r. "
            "Las líneas PERSONAL no se crearán.",
            company .pk ,
            )
        try :
            with transaction .atomic ():
                first_entry_gr =draft .entries .first ()


                _next_line_num =1 
                if first_entry_gr :
                    existing_max =(
                    first_entry_gr .lines 
                    .order_by ("-line_number")
                    .values_list ("line_number",flat =True )
                    .first ()
                    )
                    _next_line_num =(existing_max or 0 )+1 
                for gap ,res in resolutions :
                    if res ["type"]=="lunch":
                        gap .lunch_had =res ["lunch_had"]
                        gap .lunch_time =res ["lunch_time"]
                        gap .note =res ["note"]
                        gap .resolved =True 
                        gap .save (update_fields =["lunch_had","lunch_time","note","resolved"])
                    else :
                        gap .absence_category =res ["absence_cat"]
                        gap .note =res ["note"]
                        gap .resolved =True 
                        gap .save (update_fields =["absence_category","note","resolved"])









                        if first_entry_gr is not None and _personal_asset_gr is not None :
                            _gr_delta =_cdh_gr (
                            gap .gap_start ,gap .gap_end ,deduct_lunch =False 
                            )
                            WorkOrderEntryLine .objects .create (
                            entry =first_entry_gr ,
                            line_number =_next_line_num ,
                            machine_asset =_personal_asset_gr ,
                            machine_raw =_personal_asset_gr .code ,
                            machine_norm =_personal_asset_gr .code ,
                            fault_description =res ["absence_cat"].label ,
                            repair_notes =res ["note"],
                            hc =gap .gap_start ,
                            hf =gap .gap_end ,
                            or_val ="",
                            delta_hours =_gr_delta ,
                            flags =[],
                            )
                            logger .info (
                            "# [GapResolutionView] WorkOrderEntryLine PERSONAL creado. "
                            "entry_pk=%r line_number=%r hc=%r hf=%r absence_cat=%r",
                            first_entry_gr .pk ,_next_line_num ,
                            gap .gap_start ,gap .gap_end ,
                            res ["absence_cat"].label ,
                            )
                            _next_line_num +=1 

                draft .status =WorkOrder .Status .DONE 
                draft .save (update_fields =["status"])

        except Exception as exc :
            logger .error (
            "# [GapResolutionView] Error al persistir resoluciones: %s",
            exc ,exc_info =True ,
            )
            django_messages .error (
            request ,
            f"Error al guardar la justificación: {exc}. "
            "Por favor, inténtalo de nuevo.",
            )
            return redirect (
            reverse (
            "panel:operator_gap_resolution",
            kwargs ={"wo_draft_pk":wo_draft_pk },
            )
            )



        request .session .pop ("pending_gaps_wo_pk",None )
        request .session .modified =True 





        first_entry =draft .entries .first ()
        if first_entry :
            for _line in first_entry .lines .all ():
                _cached =find_cached_classification (
                fault_description =_line .fault_description ,
                repair_notes =_line .repair_notes ,
                company =company ,
                )
                if _cached :
                    WorkOrderEntryLine .objects .filter (pk =_line .pk ).update (
                    fault_category =_cached [0 ],
                    fault_subcategory =_cached [1 ],
                    )
                    logger .info (
                    "# [GapResolutionView] Clasificación copiada desde caché "
                    "para WorkOrderEntryLine pk=%d: category=%s subcategory=%s.",
                    _line .pk ,_cached [0 ],_cached [1 ],
                    )
                else :
                    classify_fault_line .apply_async (
                    args =[_line .pk ],
                    queue ="work_orders",
                    )
                    logger .info (
                    "# [GapResolutionView] classify_fault_line encolada "
                    "para WorkOrderEntryLine pk=%d.",
                    _line .pk ,
                    )

        try :
            generate_work_order_excel (draft .pk )
            logger .info (
            "# [GapResolutionView] Excel generado para WorkOrder #%d.",
            draft .pk ,
            )
        except Exception as exc :
            logger .warning (
            "# [GapResolutionView] Excel no generado para WorkOrder #%d: %s.",
            draft .pk ,exc ,
            )

        django_messages .success (
        request ,
        f"Parte #{draft.pk} registrado correctamente. "
        f"Todas las lagunas de jornada han sido justificadas.",
        )
        return redirect (reverse ("panel:operator_history"))


class WorkshopAssetDetailView (WorkshopRequiredMixin ,View ):
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

    def get (self ,request ,*args ,**kwargs ):
        """
        Returns meter-reading flags and reference values for the requested asset.
        Scoped to the authenticated user's company. Returns HTTP 400 on missing
        code and HTTP 404 if the asset does not exist for the company.
        ---
        Devuelve los flags de contadores y valores de referencia del activo
        solicitado. Acotado a la empresa del usuario autenticado. Devuelve
        HTTP 400 si falta el código y HTTP 404 si el activo no existe.
        """
        from django .http import JsonResponse 
        from fleet .models import MachineAsset 

        code =request .GET .get ("code","").strip ()
        if not code :
            return JsonResponse (
            {"error":"Parámetro 'code' obligatorio."},
            status =400 ,
            )

        company =request .user .company_user .company 

        try :
            asset =MachineAsset .objects .get (
            code__iexact =code ,
            company =company ,
            )
        except MachineAsset .DoesNotExist :
            return JsonResponse (
            {"error":f"Activo '{code}' no encontrado en catálogo."},
            status =404 ,
            )

        return JsonResponse ({
        "has_odometer":asset .has_odometer ,
        "has_engine_hours":asset .has_engine_hours ,
        "has_crane_hours":asset .has_crane_hours ,
        "first_repair":asset .first_repair ,
        "mileage":float (asset .mileage )if asset .mileage is not None else None ,
        "hours":float (asset .hours )if asset .hours is not None else None ,
        })


class WorkOrderDescriptionAutocompleteView (WorkshopRequiredMixin ,View ):
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



    _ALLOWED_FIELDS ={"fault_description","repair_notes"}


    _MIN_QUERY_LEN =2 


    _MAX_RESULTS =8 

    def get (self ,request ,*args ,**kwargs ):
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
        from django .http import JsonResponse 
        from work_order_processor .models import WorkOrderEntryLine 

        field =request .GET .get ("field","").strip ()
        q =request .GET .get ("q","").strip ()



        if field not in self ._ALLOWED_FIELDS :
            return JsonResponse ({"results":[]})



        if len (q )<self ._MIN_QUERY_LEN :
            return JsonResponse ({"results":[]})

        company_user =request .user .company_user 
        company =company_user .company 



        lookup ={field +"__icontains":q }

        qs =(
        WorkOrderEntryLine .objects 
        .filter (entry__work_order__company =company ,**lookup )
        .exclude (**{field :""})
        .values_list (field ,flat =True )
        .distinct ()
        .order_by (field )
        [:self ._MAX_RESULTS ]
        )

        return JsonResponse ({"results":list (qs )})


class WorkshopIntensiveToggleView (WorkshopRequiredMixin ,View ):
    """
    JSON endpoint that toggles or explicitly sets the is_intensive_override
    flag on the authenticated CompanyUser. Called from the operator work-order
    entry form when the operator activates or deactivates the intensive-shift
    checkbox. Returns the updated schedule data so the frontend can reload
    EB_CONFIG without a full page refresh.

    POST /panel/operator/intensive-toggle/
        Body (form-encoded or JSON): value=1|0
          1 — activate intensive shift.
          0 — deactivate intensive shift.
        Returns JSON:
          {
            "is_intensive": bool,
            "lunch_break_start": "HH:MM" | "",
            "lunch_break_end":   "HH:MM" | "",
            "end_time_morning":  "HH:MM" | "",
            "end_time_afternoon":"HH:MM" | "",
            "first_hc":          "HH:MM" | ""
          }
    ---
    Endpoint JSON que activa o desactiva el flag is_intensive_override del
    CompanyUser autenticado. Llamado desde el formulario de parte del operario
    cuando activa o desactiva el checkbox de jornada intensiva. Devuelve los
    datos del horario actualizado para que el frontend recargue EB_CONFIG sin
    recargar la pagina completa.

    POST /panel/operator/intensive-toggle/
        Cuerpo (form-encoded o JSON): value=1|0
          1 — activar jornada intensiva.
          0 — desactivar jornada intensiva.
        Devuelve JSON con los campos de horario actualizados.
    """

    def post (self ,request ,*args ,**kwargs ):
        """
        Persists the intensive-shift override and returns updated schedule
        fields as JSON for immediate EB_CONFIG reload on the client.
        ---
        Persiste el override de jornada intensiva y devuelve los campos de
        horario actualizados como JSON para recargar EB_CONFIG en el cliente.
        """
        import json as _json
        from django .http import JsonResponse 

        try :
            cu =request .user .company_user 
            company =cu .company 
        except AttributeError :
            return JsonResponse ({"error":"Sin perfil de empresa."},status =403 )

        # -- Parse value from JSON body or form-encoded body. --
        # -- Parsear value desde cuerpo JSON o form-encoded. --
        raw_value =None 
        if request .content_type and "application/json" in request .content_type :
            try :
                payload =_json .loads (request .body )
                raw_value =payload .get ("value")
            except (ValueError ,KeyError ):
                pass 
        if raw_value is None :
            raw_value =request .POST .get ("value","0")

        activate =str (raw_value ).strip ()in ("1","true","True")

        # -- Persist the flag. --
        # -- Persistir el flag. --
        cu .is_intensive_override =activate 
        cu .save (update_fields =["is_intensive_override"])

        # -- Resolve updated schedule and build response payload. --
        # -- Resolver horario actualizado y construir payload de respuesta. --
        schedule =_resolve_operator_schedule (cu ,company )

        def _fmt (t ):
            """
            Formats a time field as HH:MM string, or returns empty string.
            ---
            Formatea un campo de hora como cadena HH:MM, o devuelve cadena vacia.
            """
            return t .strftime ("%H:%M") if t else ""

        lunch_break_start =""
        lunch_break_end =""
        end_time_morning =""
        end_time_afternoon =""
        first_hc =""

        if schedule is not None :
            first_hc =_fmt (schedule .start_time_morning )
            if not schedule .is_intensive :
                lunch_break_start =_fmt (schedule .end_time_morning )
                lunch_break_end =_fmt (schedule .start_time_afternoon )
                end_time_morning =_fmt (schedule .end_time_morning )
            if schedule .end_time_afternoon :
                end_time_afternoon =_fmt (schedule .end_time_afternoon )
            elif schedule .is_intensive and schedule .end_time_morning :
                end_time_afternoon =_fmt (schedule .end_time_morning )

        # -- Build schedule context for the HTMX partial. --
        # -- Construir contexto de horario para el partial HTMX. --
        from django .shortcuts import render as _render
        from ivr_config .models import AbsenceCategory as _AbsCat

        _absence_cats = list (
            _AbsCat .objects
            .filter (company =company ,is_active =True )
            .order_by ('label')
            .values ('id','label','requires_note')
        )

        _first_hc = first_hc
        _first_hf = (
            end_time_afternoon
            if end_time_afternoon
            else end_time_morning
        )

        _ctx = {
            'is_intensive_override': activate ,
            'show_lunch_break': bool (lunch_break_start ),
            'lunch_break_start': lunch_break_start ,
            'lunch_break_end': lunch_break_end ,
            'end_time_morning': end_time_morning ,
            'end_time_afternoon': end_time_afternoon ,
            'first_block_hc': _first_hc ,
            'first_block_hf': _first_hf ,
            'absence_categories': _absence_cats ,
        }
        return _render (
            request ,
            'panel/operator/_schedule_fields_fragment.html',
            _ctx ,
        )

