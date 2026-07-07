

# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_operator.py
from django.contrib import messages as django_messages
from django.views.generic import TemplateView, View
from django.shortcuts import get_object_or_404, redirect, render
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
            # Build a compound OR filter so the operator can search by
            # asset code, brand/model or plate. A fourth branch extracts
            # only the digit characters from the query and searches them
            # as a substring inside the plate field — this allows finding
            # "AB1234C" by typing "1234", regardless of the letter layout
            # of the plate format (LNNNNLL, NNNNLLL, LLLNNNN, etc.).
            #
            # Construye un filtro OR compuesto para que el operario pueda
            # buscar por código, marca/modelo o matrícula. Una cuarta rama
            # extrae únicamente los dígitos del query y los busca como
            # subcadena dentro del campo plate — permite encontrar "AB1234C"
            # escribiendo "1234", independientemente del formato de la
            # matrícula (LNNNNLL, NNNNLLL, LLLNNNN, etc.).
            _q_digits = "".join(ch for ch in q if ch.isdigit())
            _plate_filter = django_models.Q(plate__icontains=q)
            if len(_q_digits) >= 4:
                # Only activate digit-substring plate search when the query
                # contains at least 4 consecutive digit characters. Shorter
                # digit sequences (e.g. 'G12') produce too many false positives
                # because they match any plate containing those digits.
                # Solo activar la búsqueda por subcadena de dígitos en
                # matrícula cuando el query contiene al menos 4 dígitos.
                # Secuencias más cortas (ej: 'G12') generan demasiados falsos
                # positivos al coincidir con cualquier matrícula que las contenga.
                _plate_filter = (
                    django_models.Q(plate__icontains=q)
                    | django_models.Q(plate__icontains=_q_digits)
                )
            qs = qs.filter(
                django_models.Q(code__icontains=q)
                | django_models.Q(brand_model__icontains=q)
                | _plate_filter
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
    from work_order_processor .management .commands .seed_empresa_assets import (
    EMPRESA_ASSETS as _EMPRESA_ASSETS ,
    )
    _EMPRESA_CODES = {
        a ["code"].upper () for a in _EMPRESA_ASSETS
    }

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

        # Pass 3 — label was submitted (e.g. "B43 — PALFINGER PK 72002"):
        # extract the code before " — " and retry passes 1 and 2.
        # Pasada 3 — se envió el label completo: extraer el código antes de " — "
        # y reintentar las pasadas 1 y 2.
        if machine_asset is None and machine_raw :
            import re as _re
            _label_match = _re.match(r"^([^—–\-]+?)\s*[—–]\s+", machine_raw)
            if _label_match :
                _code_from_label = _label_match .group (1).strip ()
                _norm_from_label = _normalise_machine_code (_code_from_label )
                machine_asset = MachineAsset .objects .filter (
                    code__iexact =_code_from_label ,company =company ,
                ).first ()
                if machine_asset is None :
                    machine_asset = MachineAsset .objects .filter (
                        code__iexact =_norm_from_label ,company =company ,
                    ).first ()

        # Pass 4 — match by brand_model (exact or contains).
        # Pasada 4 — coincidencia por brand_model (exacta o contenida).
        if machine_asset is None and machine_raw :
            machine_asset = MachineAsset .objects .filter (
                brand_model__iexact =machine_raw ,company =company ,is_active =True ,
            ).first ()
            if machine_asset is None :
                machine_asset = MachineAsset .objects .filter (
                    brand_model__icontains =machine_raw ,company =company ,is_active =True ,
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

        # is_on_site — checkbox submitted as "1" when checked.
        # is_on_site — checkbox enviado como "1" cuando está marcado.
        _is_on_site = POST.get(f"{pfx}is_on_site", "") == "1"

        # breakdown ticket resolution -- H10 Paso 4-bis (revisado S007),
        # sustituye el desplegable manual ticket_pk de H17.
        # Resolución de ticket de avería -- H10 Paso 4-bis (revisado
        # S007), sustituye el desplegable manual ticket_pk de H17.
        _ticket_action = POST.get(f"{pfx}ticket_action", "").strip()
        _ticket_reopen_raw = POST.get(f"{pfx}ticket_reopen", "").strip()
        _ticket_reopen = (
            _ticket_reopen_raw == "1" if _ticket_reopen_raw in ("0", "1")
            else None
        )
        _ticket_chosen_raw = POST.get(f"{pfx}ticket_chosen_pk", "").strip()
        _ticket_create_new = (_ticket_chosen_raw == "new")
        _ticket_chosen_pk = (
            int(_ticket_chosen_raw)
            if _ticket_chosen_raw.isdigit()
            else None
        )
        _ticket_closed = POST.get(f"{pfx}ticket_closed", "") == "1"

        # EMPRESA_* block — detect and resolve subtype label.
        # Bloque EMPRESA_* — detectar y resolver el label del subtipo.
        _is_empresa_block = (
            machine_asset is not None
            and machine_asset.code.upper() in _EMPRESA_CODES
        )
        if _is_empresa_block:
            _empresa_subtype = POST.get(
                f"{pfx}empresa_subtype", ""
            ).strip()
            if _empresa_subtype:
                # Override fault_description with subtype + asset label.
                # Sobreescribir fault_description con subtipo + label activo.
                desc_averia = _empresa_subtype

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
        "is_on_site":_is_on_site ,
        "is_empresa":_is_empresa_block ,
        "ticket_action":_ticket_action ,
        "ticket_reopen":_ticket_reopen ,
        "ticket_create_new":_ticket_create_new ,
        "ticket_chosen_pk":_ticket_chosen_pk ,
        "ticket_closed":_ticket_closed ,
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

            # Gate 0a — reject future dates.
            # Gate 0a — rechazar fechas futuras.
            from datetime import date as _date_today_c 
            if _gate0_work_date >_date_today_c .today ():
                context =self ._get_context_base (request )
                context .update ({
                "error":(
                f"No puedes introducir un parte con fecha futura "
                f"({_gate0_work_date.strftime('%d/%m/%Y')}). "
                f"La fecha del parte no puede ser posterior a hoy."
                ),
                "fecha":_gate0_fecha_str ,
                "uncertain_date":False ,
                "confidence":"",
                "entradas_enriched":[],
                "repuestos_enriched":[],
                "num_entradas":0 ,
                "num_repuestos":0 ,
                "min_date":_get_min_allowed_date (cu ).isoformat ()if _get_min_allowed_date (cu )else "",
                })
                return render (request ,self .template_name ,context )

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
                # Duplicate date — error returned in the same form.
                # Fecha duplicada — error devuelto en el mismo formulario.
                _extraction_cm = request .session .get (
                    "operator_upload_extraction", {}
                )
                context = self ._get_context_base (request )
                context .update ({
                    "error": (
                        "Ya existe un parte para la fecha "
                        f"{_gate0_work_date.strftime('%d/%m/%Y')}. "
                        "Si quieres editarlo, ve al historial y pulsa "
                        "'Editar' en el parte correspondiente."
                    ),
                    "extraction": _extraction_cm ,
                    "fecha": _gate0_fecha_str ,
                    "uncertain_date": False ,
                    "confidence": "",
                    "entradas_enriched": [],
                    "repuestos_enriched": [],
                    "num_entradas": 0 ,
                    "num_repuestos": 0 ,
                    "min_date": (
                        _get_min_allowed_date (cu ).isoformat ()
                        if _get_min_allowed_date (cu ) else ""
                    ),
                })
                return render (request , self .template_name , context )





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
            blk =f"Tarea {ld['line_number']}"
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
            _is_absence_blk =ld .get ("absence_category")is not None 
            if _is_absence_blk :
                # Absence block: fault_description not required (auto-filled
                # with category label). repair_notes optional unless the
                # category requires a note.
                # Bloque de ausencia: descripción de avería no obligatoria
                # (se autorrellena con la etiqueta de la categoría).
                # repair_notes opcional salvo que la categoría requiera nota.
                _abs_cat =ld .get ("absence_category")
                if (getattr (_abs_cat ,"requires_note",False )
                        and not ld ["repair_notes"]):
                    integrity_errors .append (
                    f"{blk}: esta categoría de ausencia requiere que "
                    f"describas brevemente el motivo."
                    )
            else :
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
                blk =f"Tarea {ld['line_number']}"
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
                    is_on_site =ld .get ("is_on_site", False),
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
                f"Añade los bloques que faltan o, si hubo ausencia, "
                f"añade un bloque con código PERSONAL en el campo "
                f"Máquina/Centro de Gasto y selecciona el motivo."
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


def _resolve_editable_work_order(pk, cu, company):
    """
    Resolves the digital WorkOrder targeted by wo_pk/edit_wo_pk for
    WorkOrderEntryFormView's edit mode, with role-aware scope.

    Fix (2026-07-07, bug detectado por Miguel Ángel -- "Editar /
    Revisar" en admin_history.html no entraba en modo edición real):
    la condición original (uploaded_by=cu, reviewed=False) es correcta
    SOLO para el operario editando su propio parte antes de revisión
    -- pero esta misma vista también se usa desde el listado de ADMIN
    (botón "Editar / Revisar" sobre partes de CUALQUIER operario,
    revisados o no). Con la condición original, esa consulta fallaba
    siempre que el ADMIN no fuera quien subió el parte, o que ya
    estuviera revisado -- DoesNotExist, y la vista rebotaba al
    historial sin entrar en modo edición.

    ADMIN: acceso completo dentro de su empresa, cualquier autor,
    revisado o no (coincide con "ADMIN: acceso completo" ya
    documentado en CompanyUser).
    Cualquier otro rol que llegue aquí (WORKSHOP, único otro permitido
    por WorkshopRequiredMixin): solo su propio parte, sin revisar --
    comportamiento sin cambios.

    Raises WorkOrder.DoesNotExist si no hay coincidencia -- el
    llamante decide qué hacer (mensaje + redirect en GET, None en
    POST).

    ---

    Resuelve el WorkOrder digital señalado por wo_pk/edit_wo_pk para
    el modo edición de WorkOrderEntryFormView, con alcance según rol.

    Corrección (2026-07-07, bug detectado por Miguel Ángel -- "Editar
    / Revisar" en admin_history.html no entraba en modo edición real):
    la condición original (uploaded_by=cu, reviewed=False) es correcta
    SOLO para el operario editando su propio parte antes de revisión
    -- pero esta misma vista también se usa desde el listado de ADMIN
    (botón "Editar / Revisar" sobre partes de CUALQUIER operario,
    revisados o no). Con la condición original, esa consulta fallaba
    siempre que el ADMIN no fuera quien subió el parte, o que ya
    estuviera revisado -- DoesNotExist, y la vista rebotaba al
    historial sin entrar en modo edición.

    ADMIN: acceso completo dentro de su empresa, cualquier autor,
    revisado o no (coincide con "ADMIN: acceso completo" ya
    documentado en CompanyUser).
    Cualquier otro rol que llegue aquí (WORKSHOP, único otro permitido
    por WorkshopRequiredMixin): solo su propio parte, sin revisar --
    comportamiento sin cambios.

    Lanza WorkOrder.DoesNotExist si no hay coincidencia -- quien llama
    decide qué hacer (mensaje + redirect en GET, None en POST).
    """
    base_filter = dict(
        pk=pk,
        company=company,
        source__in=[WorkOrder.Source.DIGITAL, WorkOrder.Source.GENERATED],
    )
    if cu.role == CompanyUser.ROLE_ADMIN:
        return WorkOrder.objects.get(**base_filter)
    return WorkOrder.objects.get(
        uploaded_by=cu, reviewed=False, **base_filter,
    )


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
        Provides the list of active MachineAsset records for autocomplete.
        Ticket-per-machine resolution (H10 Paso 4-bis) is no longer
        preloaded here as a static list -- it is resolved on demand per
        block via TaskTicketResolutionView (HTMX), once the mechanic
        picks a machine, replacing the old H17 free-choice dropdown.
        ---
        Devuelve el contexto base con empresa y datos de navegación.
        Proporciona la lista de MachineAsset activos para autocompletado.
        La resolución de ticket por máquina (H10 Paso 4-bis) ya no se
        precarga aquí como lista estática -- se resuelve bajo demanda
        por bloque vía TaskTicketResolutionView (HTMX), en cuanto el
        mecánico elige una máquina, sustituyendo al antiguo desplegable
        de elección libre de H17.
        """
        from fleet .models import MachineAsset 
        cu =self ._get_company_user (request )
        company =cu .company 
        assets =list (
        MachineAsset .objects .filter (company =company ,is_active =True )
        .order_by ("code")
        .values ("code","brand_model")
        )


        import json as _json_ctx
        from ivr_config .models import AbsenceCategory as _AbsCatCtx
        _absence_cats_ctx =list (
            _AbsCatCtx .objects .filter (company =company ,is_active =True )
            .order_by ("order","label")
            .values ("id","label","requires_note")
        )
        return {
        "company":company ,
        "company_user":cu ,
        "active_nav":"operator_dashboard",
        "assets":assets ,
        "absence_categories":_json_ctx .dumps (_absence_cats_ctx ),
        "absence_categories_list":_absence_cats_ctx ,
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
                wo_edit =_resolve_editable_work_order (wo_pk ,cu ,company )
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
            "lunch_break_start":first_entry .lunch_break_start .strftime ("%H:%M")if first_entry and first_entry .lunch_break_start else _lunch_start_edit ,
            "lunch_break_end":first_entry .lunch_break_end .strftime ("%H:%M")if first_entry and first_entry .lunch_break_end else _lunch_end_edit ,
            "first_block_hc":_first_hc_edit ,
            "first_block_hf":_first_hf_edit ,
            "no_lunch_break":first_entry .no_lunch_break if first_entry else False ,
            "show_lunch_break":_show_lunch_edit ,
            "end_time_morning":_end_time_morning_edit ,
            "end_time_afternoon":_end_time_afternoon_edit ,
            "start_time_afternoon":_lunch_end_edit ,
            "is_intensive_override":getattr (cu ,"is_intensive_override",False ),
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
            import json as _json_fix 
            from ivr_config .models import AbsenceCategory as _AbsCat 
            from fleet .models import MachineAsset as _MA 
            from work_order_processor .management .commands .seed_personal_asset import PERSONAL_ASSET_CODE 
            from work_order_processor .management .commands .seed_empresa_assets import (
                EMPRESA_SUBTYPES as _ES_MAP_IP ,
                get_empresa_subtype_group as _get_es_group_ip ,
            )
            _empresa_assets_ip = list (
                _MA .objects .filter (
                    company =company ,
                    code__startswith ="EMPRESA_",
                    is_active =True ,
                ).order_by ("code").values ("code","brand_model")
            )
            _empresa_subtypes_ip = {
                a ["code"]: _ES_MAP_IP [_get_es_group_ip (a ["code"])]
                for a in _empresa_assets_ip
            }
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
            "start_time_afternoon":_ip_lunch_end ,
            "absence_categories":_json_fix .dumps (_absence_cats) ,
            "personal_asset_code":PERSONAL_ASSET_CODE ,
            "is_intensive_override":getattr (cu ,"is_intensive_override",False ),
            "empresa_subtypes":_json_fix .dumps (_empresa_subtypes_ip ),
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
        from work_order_processor .management .commands .seed_empresa_assets import (
            EMPRESA_SUBTYPES as _ES_MAP ,
            get_empresa_subtype_group as _get_es_group ,
        )
        from fleet .models import MachineAsset as _MA_ctx 
        _empresa_assets_ctx = list (
            _MA_ctx .objects .filter (
                company =company ,
                code__startswith ="EMPRESA_",
                is_active =True ,
            ).order_by ("code").values ("code","brand_model")
        )
        _empresa_subtypes_ctx = {
            a ["code"]: _ES_MAP [_get_es_group (a ["code"])]
            for a in _empresa_assets_ctx
        }
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
        "start_time_afternoon":_lunch_end ,
        "absence_categories":_json_fix .dumps (_absence_cats) ,
        "personal_asset_code":PERSONAL_ASSET_CODE ,
        "is_intensive_override":getattr (cu ,"is_intensive_override",False ),
        "empresa_subtypes":_json_fix .dumps (_empresa_subtypes_ctx ),
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
        # Preserve operator-modified lunch times from POST over schedule defaults.
        # On re-render after a validation error, the operator's input must not
        # be overwritten by the schedule's configured window.
        # Preservar los horarios de pausa modificados por el operario desde POST
        # sobre los valores por defecto del schedule.
        # Al re-renderizar tras un error de validacion, el input del operario no
        # debe ser sobreescrito por la ventana configurada en el schedule.
        if _lb_start_raw :
            _post_lb_start =_lb_start_raw 
        if _lb_end_raw :
            _post_lb_end =_lb_end_raw 
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
            # Gate 0a — reject future dates.
            # Gate 0a — rechazar fechas futuras.
            from datetime import date as _date_today_fa 
            if work_date >_date_today_fa .today ():
                _eld_future =_parse_entry_lines_from_post (POST ,company )
                _entradas_future =[
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
                for ld in _eld_future
                ]
                context =self ._get_context_base (request )
                context .update ({
                "error":(
                f"No puedes introducir un parte con fecha futura "
                f"({work_date.strftime('%d/%m/%Y')}). "
                f"La fecha del parte no puede ser posterior a hoy."
                ),
                "fecha":fecha_str ,
                "entradas_enriched":_entradas_future ,
                "repuestos_enriched":[],
                "num_entradas":max (1 ,len (_entradas_future )),
                "num_repuestos":0 ,
                "min_date":_get_min_allowed_date (cu ).isoformat ()if _get_min_allowed_date (cu )else "",
                "lunch_break_start":_post_lb_start ,
                "lunch_break_end":_post_lb_end ,
                "show_lunch_break":_post_show_lunch ,
                })
                return render (request ,self .template_name ,context )

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









        # Non-destructive pre-edit check: verify the work order exists and
        # belongs to the operator. Never delete — data must never be lost.
        # Comprobacion pre-edicion no destructiva: verificar que el parte existe
        # y pertenece al operario. Nunca borrar — la informacion no debe perderse.
        _edit_wo_pk_pre =POST .get ("edit_wo_pk","").strip ()
        if _edit_wo_pk_pre :
            try :
                _wo_orig_pre =_resolve_editable_work_order (
                int (_edit_wo_pk_pre ),cu ,company ,
                )
                # Parte verificado — no se borra. El flujo continua.
                # Work order verified — not deleted. Flow continues.
                logger .info (
                "# [FormView/pre-edit] WorkOrder pk=%d verificado. "
                "No se borra — edicion no destructiva.",
                _wo_orig_pre .pk ,
                )
            except (WorkOrder .DoesNotExist ,ValueError ):
                pass 















        if work_date is not None :
            from work_order_processor .models import WorkOrder as _WO0 ,WorkOrderEntry as _WOE0 
            _excl_pks = set ()
            _edit_wo_pk_ck = POST .get ("edit_wo_pk", "").strip ()
            _ip_wo_pk_ck   = POST .get ("in_progress_wo_pk", "").strip ()
            if _edit_wo_pk_ck :
                try :
                    _excl_pks .add (int (_edit_wo_pk_ck ))
                except ValueError :
                    pass
            if _ip_wo_pk_ck :
                try :
                    _excl_pks .add (int (_ip_wo_pk_ck ))
                except ValueError :
                    pass
            _ip_pks = list (
                _WO0 .objects .filter (
                    company =company ,
                    uploaded_by =cu ,
                    status =_WO0 .Status .IN_PROGRESS ,
                ).values_list ("pk", flat =True )
            )
            _excl_pks .update (_ip_pks )
            _existing_entry0 = _WOE0 .objects .filter (
                work_order__company =company ,
                work_order__uploaded_by =cu ,
                work_order__source__in =[
                    _WO0 .Source .DIGITAL ,
                    _WO0 .Source .GENERATED ,
                ],
                work_order__reviewed =False ,
                work_date =work_date ,
            ).exclude (
                work_order__pk__in =_excl_pks ,
            ).select_related ("work_order").first ()

            if _existing_entry0 is not None :
                # Duplicate date — error returned in the same form.
                # Fecha duplicada — error devuelto en el mismo formulario.
                _is_editing_this = (
                    bool (_edit_wo_pk_ck)
                    and str (_existing_entry0 .work_order .pk) == _edit_wo_pk_ck
                )
                if not _is_editing_this :
                    logger .info (
                    "# [FormView/Gate0] Fecha duplicada. "
                    "form_action=%r existing_entry0_pk=%r",
                    _form_action , _existing_entry0 .pk ,
                    )
                    _entradas_err = [
                    {
                        "idx": ld ["line_number"],
                        "machine_raw": ld ["machine_raw"],
                        "machine_asset": ld ["machine_asset"],
                        "fault_description": ld ["fault_description"],
                        "repair_notes": ld ["repair_notes"],
                        "hc": ld ["hc"].strftime ("%H:%M") if ld ["hc"] else "",
                        "hf": ld ["hf"].strftime ("%H:%M") if ld ["hf"] else "",
                        "or_val": ld ["or_val"],
                        "flags": [],
                    }
                    for ld in _parse_entry_lines_from_post (POST , company )
                    ]
                    context = self ._get_context_base (request )
                    context .update ({
                        "error": (
                            "Ya existe un parte para la fecha "
                            f"{work_date.strftime('%d/%m/%Y')}. "
                            "Si quieres editarlo, ve al historial y pulsa "
                            "'Editar' en el parte correspondiente."
                        ),
                        "fecha": fecha_str ,
                        "entradas_enriched": _entradas_err ,
                        "repuestos_enriched": [],
                        "num_entradas": len (_entradas_err ),
                        "num_repuestos": 0 ,
                        "lunch_break_start": _post_lb_start ,
                        "lunch_break_end": _post_lb_end ,
                        "show_lunch_break": _post_show_lunch ,
                        "min_date": _get_min_allowed_date (cu ).isoformat ()
                        if _get_min_allowed_date (cu ) else "",
                    })
                    return render (request , self .template_name , context )











        entry_lines_data =_parse_entry_lines_from_post (POST ,company )
        spare_parts_data =_parse_spare_parts_from_post (
        POST ,company ,entry_lines_data =entry_lines_data 
        )

        # SAFETY LOG — full part content logged before any DB operation.
        # Allows data recovery from server.log if a bug causes data loss.
        # LOG DE SEGURIDAD — contenido completo del parte antes de cualquier
        # operacion en BD. Permite recuperar datos desde server.log si un
        # bug provoca perdida de informacion.
        _log_edit_pk =POST .get ("edit_wo_pk","").strip ()or POST .get ("in_progress_wo_pk","").strip ()
        logger .info (
        "# [SAFETY-LOG] form_action=%r edit_wo_pk=%r fecha=%r "
        "num_bloques=%d num_repuestos=%d",
        _form_action ,_log_edit_pk ,fecha_str ,
        len (entry_lines_data ),len (spare_parts_data ),
        )
        for _sld in entry_lines_data :
            logger .info (
            "# [SAFETY-LOG] BLOQUE %d | maquina=%r | hc=%r | hf=%r | "
            "delta_h=%r | averia=%r | reparacion=%r | or=%r",
            _sld .get ("line_number"),
            _sld .get ("machine_raw"),
            _sld ["hc"].strftime ("%H:%M")if _sld .get ("hc")else None ,
            _sld ["hf"].strftime ("%H:%M")if _sld .get ("hf")else None ,
            _sld .get ("delta_hours"),
            _sld .get ("fault_description"),
            _sld .get ("repair_notes"),
            _sld .get ("or_val"),
            )
        for _ssp in spare_parts_data :
            logger .info (
            "# [SAFETY-LOG] REPUESTO %d | material=%r | cantidad=%r | "
            "referencia=%r | proveedor=%r | origen=%r",
            _ssp .get ("line_number"),
            _ssp .get ("material"),
            _ssp .get ("quantity"),
            _ssp .get ("referencia"),
            _ssp .get ("supplier"),
            _ssp .get ("source"),
            )






        integrity_errors =[]

        if not work_date :
            integrity_errors .append (
            "La fecha del parte es obligatoria y debe tener formato DD/MM/AAAA."
            )

        if not entry_lines_data :
            integrity_errors .append ("El parte debe contener al menos un bloque de trabajo.")

        for ld in entry_lines_data :
            blk =f"Tarea {ld['line_number']}"
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







        # Meter warnings — non-blocking. Missing or zero readings are
        # reported as warnings that the operator can acknowledge and
        # override. They do NOT prevent the work order from being saved.
        # Avisos de contadores — no bloqueantes. Las lecturas ausentes o
        # en cero se informan como avisos que el operario puede confirmar
        # y omitir. NO impiden guardar el parte.
        meter_warnings = []
        for ld in entry_lines_data :
            if ld ["machine_asset"]is not None :
                asset =ld ["machine_asset"]
                blk =f"Tarea {ld['line_number']}"
                if asset .has_odometer :
                    reading =ld .get ("odometer_reading")
                    if reading is None :
                        meter_warnings .append (
                        f"{blk}: no has introducido la lectura de km (cuentakilómetros) "
                        f"para {asset.code}. Se recomienda registrarla para el seguimiento del vehículo."
                        )
                    elif reading ==0 and not asset .first_repair :
                        meter_warnings .append (
                        f"{blk}: la lectura de km es cero para {asset.code} "
                        f"(ya tiene partes anteriores). Comprueba si es correcta."
                        )
                if asset .has_engine_hours :
                    reading =ld .get ("engine_hours_reading")
                    if reading is None :
                        meter_warnings .append (
                        f"{blk}: no has introducido la lectura del horómetro motor "
                        f"para {asset.code}. Se recomienda registrarla."
                        )
                    elif reading ==0 and not asset .first_repair :
                        meter_warnings .append (
                        f"{blk}: la lectura del horómetro motor es cero para {asset.code} "
                        f"(ya tiene partes anteriores). Comprueba si es correcta."
                        )
                if asset .has_crane_hours :
                    reading =ld .get ("crane_hours_reading")
                    if reading is None :
                        meter_warnings .append (
                        f"{blk}: no has introducido la lectura del horómetro grúa "
                        f"para {asset.code}. Se recomienda registrarla."
                        )
                    elif reading ==0 and not asset .first_repair :
                        meter_warnings .append (
                        f"{blk}: la lectura del horómetro grúa es cero para {asset.code} "
                        f"(ya tiene partes anteriores). Comprueba si es correcta."
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
            "meter_warnings":meter_warnings ,
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





        # If there are meter warnings and the operator has not yet
        # confirmed them, re-render the form so the JS can display
        # the meterWarningModal. Once the operator dismisses it and
        # clicks "Continuar de todas formas", the form is re-submitted
        # with meter_warnings_confirmed=1 and this block is skipped.
        # Si hay avisos de contadores y el operario aún no los ha
        # confirmado, re-renderizar para que el JS muestre el modal
        # de aviso. Al pulsar "Continuar de todas formas" el formulario
        # se reenvía con meter_warnings_confirmed=1 y se salta este bloque.
        _meter_confirmed =POST .get ("meter_warnings_confirmed","")=="1"
        if meter_warnings and not _meter_confirmed and _form_action !="save_blocks":
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
            "meter_warnings":meter_warnings ,
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

        if not POST .get ("save_confirmed")and _form_action !="save_blocks":
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
            "meter_warnings":[] ,
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

        # Resolve the operator's actual configured lunch-break window for the
        # R3 split-shift gap exception in validate_intra_gaps. No hardcoded
        # default window — None means no exception applies.
        #
        # Resolver la ventana de comida realmente configurada del operario
        # para la excepción de laguna de turno partido (R3) en
        # validate_intra_gaps. Sin ventana por defecto hardcodeada — None
        # significa que no se aplica ninguna excepción.
        _lunch_window =None
        if not _no_lunch_break and _lb_start and _lb_end :
            _lunch_window =(_lb_start .hour *60 +_lb_start .minute ,_lb_end .hour *60 +_lb_end .minute )
        elif _post_schedule and not _post_schedule .is_intensive :
            if _post_schedule .end_time_morning and _post_schedule .start_time_afternoon :
                _em =_post_schedule .end_time_morning
                _sa =_post_schedule .start_time_afternoon
                _lunch_window =(_em .hour *60 +_em .minute ,_sa .hour *60 +_sa .minute )

        _intra =run_intra_part_validation (_blocks ,lunch_window =_lunch_window )

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













        if work_date is not None and _form_action !="save_blocks":
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
                f"Añade los bloques que faltan o, si hubo ausencia, "
                f"añade un bloque con código PERSONAL en el campo "
                f"Máquina/Centro de Gasto y selecciona el motivo."
                ),
                "fecha":fecha_str ,
                "entradas_enriched":entradas_post_c ,
                "repuestos_enriched":repuestos_post_c ,
                "num_entradas":len (entry_lines_data ),
                "num_repuestos":len (spare_parts_data ),
                "min_date":_get_min_allowed_date (cu ).isoformat ()if _get_min_allowed_date (cu )else "",
                })
                return render (request ,self .template_name ,context )




























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





        # Non-destructive close: reuse the existing IN_PROGRESS work order
        # (or any digital WO for this operator) — set status to DONE and
        # append a new entry. Never delete — data must never be lost.
        # Cierre no destructivo: reutilizar el WorkOrder IN_PROGRESS existente
        # (o cualquier parte digital del operario) — cambiar status a DONE y
        # anadir una nueva entry. Nunca borrar — la informacion no debe perderse.
        edit_wo_pk =POST .get ("edit_wo_pk","").strip ()or _ip_wo_pk_close 
        _reuse_wo =None 
        if edit_wo_pk :
            try :
                _reuse_wo =_resolve_editable_work_order (
                int (edit_wo_pk ),cu ,company ,
                )
                logger .info (
                "# [FormView/close] Reutilizando WorkOrder pk=%d. "
                "No se borra — cierre no destructivo.",
                _reuse_wo .pk ,
                )
            except (WorkOrder .DoesNotExist ,ValueError ):
                _reuse_wo =None 

        try :
            with transaction .atomic ():
                worker_name =(
                cu .user .get_full_name ()or cu .user .username 
                ).upper ()

                date_tag =(
                work_date .strftime ("%d-%m-%Y")if work_date else "SIN-FECHA"
                )
                synthetic_name =f"{worker_name}_{date_tag}.pdf"

                if _reuse_wo is not None :
                    # Reuse existing work order — delete previous entries first
                    # to prevent duplication, then update status to DONE.
                    # Reutilizar parte existente — borrar las entries previas
                    # para evitar duplicación, luego actualizar status a DONE.
                    work_order =_reuse_wo 
                    work_order .entries .all ().delete ()
                    work_order .status =WorkOrder .Status .DONE 
                    work_order .save (update_fields =["status"])
                else :
                    # No existing WO found — create a new one.
                    # No se encontro parte existente — crear uno nuevo.
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

                # Determine next page number for the new entry.
                # Determinar el numero de pagina siguiente para la nueva entry.
                _next_page =work_order .entries .count ()+1 

                # Backup log — record full part payload before persisting.
                # Serves as a temporary recovery copy in the server log.
                # Log de respaldo — registrar el payload completo del parte
                # antes de persistir. Sirve de copia de recuperación temporal
                # en el log del servidor.
                try :
                    import json as _json_bk 
                    _bk_blocks =[
                    {
                        "n":_bk_ld ["line_number"],
                        "machine":_bk_ld ["machine_raw"],
                        "hc":(_bk_ld ["hc"].strftime ("%H:%M")
                              if _bk_ld ["hc"]else None ),
                        "hf":(_bk_ld ["hf"].strftime ("%H:%M")
                              if _bk_ld ["hf"]else None ),
                        "or_val":_bk_ld ["or_val"],
                        "fault":_bk_ld ["fault_description"],
                        "repair":_bk_ld ["repair_notes"],
                        "absence":(_bk_ld ["absence_category"].label
                                   if _bk_ld .get ("absence_category")else None ),
                    }
                    for _bk_ld in entry_lines_data 
                    ]
                    _bk_payload ={
                    "wo_pk":work_order .pk ,
                    "company":company .pk ,
                    "user":cu .user .username ,
                    "worker_name":worker_name ,
                    "work_date":work_date .isoformat (),
                    "lunch_start":(_lb_start .strftime ("%H:%M")
                                   if _lb_start else None ),
                    "lunch_end":(_lb_end .strftime ("%H:%M")
                                 if _lb_end else None ),
                    "no_lunch_break":_no_lunch_break ,
                    "blocks":_bk_blocks ,
                    }
                    logger .info (
                    "# [PARTE-BACKUP] %s",
                    _json_bk .dumps (_bk_payload ,ensure_ascii =False ),
                    )
                except Exception as _bk_exc :
                    logger .warning (
                    "# [PARTE-BACKUP] No se pudo registrar el respaldo: %s",
                    _bk_exc ,
                    )

                # has_diet — checkbox submitted as "1" when checked.
                # has_diet — checkbox enviado como "1" cuando está marcado.
                _has_diet = POST.get("has_diet", "") == "1"

                entry =WorkOrderEntry .objects .create (
                work_order =work_order ,
                page_number =_next_page ,
                worker_name =worker_name ,
                work_date =work_date ,
                uncertain_date =False ,
                extraction_confidence =WorkOrderEntry .Confidence .HIGH ,
                raw_gemini_response =None ,
                lunch_break_start =None if _no_lunch_break else _lb_start ,
                lunch_break_end =None if _no_lunch_break else _lb_end ,
                no_lunch_break =_no_lunch_break ,
                has_diet =_has_diet ,
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
                    is_on_site =ld .get ("is_on_site", False),
                    )
                    created_lines [ld ["line_number"]]=line 
                    created_line_pks .append (line .pk )

                    # Resolver el ticket de avería -- H10 Paso 4-bis
                    # (revisado S007), sustituye la elección manual de
                    # ticket_pk de H17. Solo aplica a bloques con una
                    # máquina real (nunca PERSONAL/EMPRESA_*, esos
                    # nunca llegan con ticket_action informado porque
                    # el JS no carga la resolución para ellos).
                    _ticket_action = ld.get("ticket_action")
                    _t_close = ld.get("ticket_closed", False)
                    if _ticket_action and ld["machine_asset"] is not None:
                        from chat.models import BreakdownTicket as _BT
                        from chat.services import get_or_create_ticket_for_machine
                        _bt = None
                        try:
                            if _ticket_action == "create":
                                _bt = get_or_create_ticket_for_machine(
                                    ld["machine_asset"], cu,
                                )
                            elif _ticket_action == "ask_reopen":
                                _bt = get_or_create_ticket_for_machine(
                                    ld["machine_asset"], cu,
                                    reopen=ld.get("ticket_reopen"),
                                )
                            elif _ticket_action == "choose":
                                if ld.get("ticket_create_new"):
                                    _bt = get_or_create_ticket_for_machine(
                                        ld["machine_asset"], cu,
                                        create_new=True,
                                    )
                                else:
                                    _bt = get_or_create_ticket_for_machine(
                                        ld["machine_asset"], cu,
                                        chosen_ticket_pk=ld.get("ticket_chosen_pk"),
                                    )
                        except ValueError as _tk_exc:
                            # Estado de UI obsoleto (p.ej. otro operario
                            # resolvió/cerró el ticket entre la carga del
                            # fragmento y el guardado del parte) -- no se
                            # bloquea el guardado completo del parte por
                            # esto, se omite el vínculo de ticket de esta
                            # línea y se registra para revisión manual.
                            logger.warning(
                                "# [FormView] Resolución de ticket "
                                "obsoleta para línea pk=%s (bloque "
                                "%s): %s -- vínculo omitido, revisar "
                                "manualmente.",
                                line.pk, ld["line_number"], _tk_exc,
                            )

                        if _bt is not None:
                            line.breakdown_ticket = _bt
                            line.ticket_closed    = _t_close
                            line.save(update_fields=[
                                "breakdown_ticket", "ticket_closed",
                            ])
                            if _t_close:
                                _bt.status      = _BT.STATUS_CLOSED
                                _bt.resolved_by = cu
                                _bt.resolved_at = now()
                                _bt.save(update_fields=[
                                    "status", "resolved_by", "resolved_at",
                                ])
                                logger.info(
                                    "# [FormView] Ticket pk=%s cerrado al"
                                    " cerrar parte por CU pk=%s.",
                                    _bt.pk, cu.pk,
                                )
                            else:
                                logger.info(
                                    "# [FormView] Línea pk=%s vinculada"
                                    " a ticket pk=%s (resolución: %s).",
                                    line.pk, _bt.pk, _ticket_action,
                                )

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

        # H10 Paso 4-bis (bloque B): si alguna tarea guardada quedo
        # vinculada a un ticket de averia, desviar a la revision de
        # repuestos pre-asignados antes de ir al historial -- el
        # mecanico confirma cuales se han colocado de verdad. Solo
        # ahora existe entry_line.pk real, por eso no puede hacerse
        # antes de guardar (mismo hallazgo que motivo el pivote de
        # S006).
        _lines_with_ticket = [
            _l .pk for _l in created_lines .values ()
            if _l .breakdown_ticket_id is not None
        ]
        if _lines_with_ticket :
            return redirect (
            _reverse_co ("panel:operator_parts_review",kwargs ={"entry_pk":entry .pk }),
            )

        if cu .role =="WORKSHOP":
            return redirect (_reverse_co ("panel:operator_history"))
        return redirect (_reverse_co ("panel:digital_work_order_list"))


class WorkOrderEntryPartsReviewView(WorkshopRequiredMixin, View):
    """
    H10 Paso 4-bis (bloque B). Post-save screen shown only when at
    least one WorkOrderEntryLine just created/edited carries a
    breakdown_ticket -- reuses the consumption widget already built in
    S006 (workorder_spare_parts._consumption_widget.html, Caso B
    autoloaded via SparePartPreAssignedListView) per line, scoped to
    each line's own ticket.

    Confirmed by Miguel Ángel (2026-07-07): el mecánico que trabajó la
    máquina es quien da conformidad a qué repuestos pre-asignados se
    han colocado de verdad -- los confirmados se consumen (ya
    materializado por SparePartConsumePreAssignedView, Caso B, sin
    cambios aquí), los que no se confirman siguen en pre-asignación
    tal cual, tanto si el ticket se cierra como si queda en pausa/en
    curso para retomar más tarde. No es un paso bloqueante -- el
    mecánico puede continuar sin confirmar nada si no toca ahora.

    GET /panel/operator/form/<entry_pk>/repuestos/

    ---

    H10 Paso 4-bis (bloque B). Pantalla posterior al guardado, mostrada
    solo cuando alguna WorkOrderEntryLine recién creada/editada lleva
    un breakdown_ticket -- reutiliza el widget de consumo ya construido
    en S006 (workorder_spare_parts._consumption_widget.html, Caso B
    autocargado vía SparePartPreAssignedListView) por línea, acotado al
    ticket propio de cada línea.

    Confirmado por Miguel Ángel (2026-07-07): el mecánico que trabajó
    la máquina es quien da conformidad a qué repuestos pre-asignados se
    han colocado de verdad -- los confirmados se consumen (ya
    materializado por SparePartConsumePreAssignedView, Caso B, sin
    cambios aquí), los que no se confirman siguen en pre-asignación tal
    cual, tanto si el ticket se cierra como si queda en pausa/en curso
    para retomar más tarde. No es un paso bloqueante -- el mecánico
    puede continuar sin confirmar nada si no toca ahora.

    GET /panel/operator/form/<entry_pk>/repuestos/
    """

    template_name = "panel/operator/parts_review.html"

    def get(self, request, entry_pk):
        from work_order_processor.models import WorkOrderEntry

        cu = request.user.company_user
        entry = get_object_or_404(
            WorkOrderEntry,
            pk=entry_pk,
            work_order__company=cu.company,
        )
        lines_with_ticket = list(
            entry.lines
            .filter(breakdown_ticket__isnull=False)
            .select_related("breakdown_ticket", "machine_asset")
            .order_by("line_number")
        )
        if not lines_with_ticket:
            # Estado de URL obsoleto (p. ej. se quitó el ticket de
            # todas las líneas tras un reintento) -- no hay nada que
            # revisar, seguir al historial directamente.
            from django.urls import reverse as _reverse_prv
            return redirect(_reverse_prv("panel:operator_history"))

        return render(request, self.template_name, {
            "company_user": cu,
            "active_nav": "operator_dashboard",
            "entry": entry,
            "lines_with_ticket": lines_with_ticket,
        })


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
        # Horas extra = suma de (horas_parte - 8) para cada parte con más de 8h.
        # Los días sin parte NO se descuentan. Solo se suman los excesos.
        # Overtime = sum of (part_hours - 8) for each part exceeding 8h.
        # Missing parts are NOT deducted. Only surpluses are summed.
        overtime_hours =sum (
        (wo ["horas_totales"]-Decimal ("8"))
        for wo in current_period_list 
        if wo .get ("horas_totales")is not None and wo ["horas_totales"]>Decimal ("8")
        )or Decimal ("0")




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
        start_time_afternoon =""
        first_hc =""

        if schedule is not None :
            first_hc =_fmt (schedule .start_time_morning )
            if not schedule .is_intensive :
                lunch_break_start =_fmt (schedule .end_time_morning )
                lunch_break_end =_fmt (schedule .start_time_afternoon )
                end_time_morning =_fmt (schedule .end_time_morning )
                start_time_afternoon =_fmt (schedule .start_time_afternoon )
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
        if activate :
            # Intensive shift: HF is end_time_morning (morning block ends at noon).
            # Jornada intensiva: HF es end_time_morning (el bloque termina al mediodia).
            _first_hf = end_time_morning if end_time_morning else end_time_afternoon
        else :
            # Split shift: HF is end_time_morning (end of morning block).
            # Jornada partida: HF es end_time_morning (fin del tramo de manana).
            _first_hf = end_time_morning

        _ctx = {
            'is_intensive_override': activate ,
            'show_lunch_break': bool (lunch_break_start ),
            'lunch_break_start': lunch_break_start ,
            'lunch_break_end': lunch_break_end ,
            'end_time_morning': end_time_morning ,
            'end_time_afternoon': end_time_afternoon ,
            'start_time_afternoon': start_time_afternoon ,
            'first_block_hc': _first_hc ,
            'first_block_hf': _first_hf ,
            'absence_categories': _json .dumps (_absence_cats) ,
            'absence_categories_list': _absence_cats ,
        }
        return _render (
            request ,
            'panel/operator/_schedule_fields_fragment.html',
            _ctx ,
        )







