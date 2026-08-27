# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_documentation_h30.py
"""
H30 (S48). Vistas nuevas del panel de documentación, contra
`DocumentIndexEntry` (cubo unificado, `cgs_grupo_alvarez`) -- migran
las pestañas Centros de Gasto/Personal del panel legado
(`panel/views_documentation.py`, construido sobre `MachineDocument`/
`PersonalDocument`, cubos residuales con 30/39 filas frente a las
11.000+ ya clasificadas aquí, ver anexo H30 sección "COMPLETADAS EN
S48"), y añaden la pestaña de EPIs, nueva.

Acceso: mismo criterio que el panel legado -- listados visibles para
cualquier usuario autenticado, subida restringida a DOCS_SUPERVISOR/
ADMIN (`DocsUploadAccessMixin`).

Vías de subida reales, las DOS siguen abiertas (Miguel Ángel, S48):
1. Carpeta vigilada por el agente local + Always-on Task (H28, ya en
   producción) -- este archivo no la toca.
2. Ficha del sujeto en el panel (`SubjectDocumentUploadView`, nueva
   aquí) -- el supervisor sube el documento nuevo directamente desde
   la ficha de la máquina/persona, sin escribir ningún nombre de
   archivo, solo la fecha -- ver `document_explorer.
   subject_upload_service`.
La vía de buzón de correo queda para más adelante, fuera de alcance
de esta sesión.
"""
from django.contrib.contenttypes.models import ContentType
from django.contrib.staticfiles.finders import find as find_static
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from email.message import EmailMessage as StdEmailMessage
from email.utils import make_msgid

from document_explorer import naming_service
from document_explorer.models import (
    DocumentAcknowledgment, DocumentIndexEntry, DocumentTypeCatalog,
    EpiDelivery, EpiItemCatalog, EpiReview, PersonIdentity,
)
from document_explorer.subject_upload_service import (
    SubjectUploadError, upload_subject_document,
)
from document_management.vigencia_service import DocumentSnapshot, is_current
from fleet.models import MachineAsset
from panel.mixins import CompanyUserRequiredMixin, DocsUploadAccessMixin
from panel.models import PanelNavigationState
from spare_parts.gcs_service import generate_signed_url
from whatsapp.services import send_epi_delivery_whatsapp_confirmation

BUCKET = "cgs_grupo_alvarez"


def _apply_sort(request, queryset, sort_columns, default_sort):
    """
    Mismo patrón server-side ya usado en panel/users/list.html --
    `?sort=campo&dir=asc|desc`, preservando el resto de filtros vía
    querystring en la propia plantilla.
    """
    sort_key = request.GET.get("sort", default_sort)
    sort_dir = request.GET.get("dir", "asc")
    if sort_key not in dict(sort_columns):
        sort_key = default_sort
    order = sort_key if sort_dir == "asc" else "-%s" % sort_key
    return queryset.order_by(order), sort_key, sort_dir


def _split_current_obsolete(entries):
    """
    Agrupa entries (ya filtradas a un sujeto) en (vigentes, obsoletas)
    por document_type -- reutiliza vigencia_service.is_current() tal
    cual (agnóstico de modelo, ya validado en H26). `is_obsolete=True`
    manda directo a obsoletas sin pasar por el cálculo de fechas (ya
    quedó decidido en el momento de la sustitución, no se recalcula
    cada vez que se lista).

    H30 (S50): cada entry vigente lleva ademas `needs_attention`
    (atributo Python, nunca de BD) -- True cuando su tipo necesita
    fecha (`tracks_expiry`) y esa fecha esta en blanco o ya paso.
    Miguel Angel, verbatim: "el seguro obligatorio tiene que estar al
    corriente del pago [...] la ITV tiene que estar vigente [...] si
    no hay vigentes [...] ya tenemos que tener un aviso visual ahi."
    Generalizado a CUALQUIER tipo tracks_expiry=True, no solo SEGURO/
    ITV -- misma logica que ya decide si hace falta perseguir fecha
    en el pipeline de ingesta (H30 S50, expiry_resolution_service):
    la ausencia de fecha en un tipo que la necesita es la señal
    completa, no hace falta una lista fija de codigos aqui tampoco.
    """
    from datetime import date

    today = date.today()
    current, obsolete = [], []
    by_type = {}
    for entry in entries:
        if entry.is_obsolete:
            obsolete.append(entry)
            continue
        by_type.setdefault(entry.document_type_id, []).append(entry)

    for _type_id, group in by_type.items():
        snapshots = {
            e.pk: DocumentSnapshot(
                identifier=e.pk, expiry_date=e.expiry_date,
                issue_date=e.issue_date,
            )
            for e in group
        }
        for entry in group:
            candidate = snapshots[entry.pk]
            siblings = [s for pk, s in snapshots.items() if pk != entry.pk]
            if is_current(candidate, siblings):
                entry.needs_attention = bool(
                    entry.document_type_id
                    and entry.document_type.tracks_expiry
                    and (not entry.expiry_date or entry.expiry_date < today)
                )
                current.append(entry)
            else:
                obsolete.append(entry)
    return current, obsolete


def _attach_alert_flags(objects, content_type):
    """
    H30 (S50) -- mismo principio que `_attach_doc_counts` (misma
    limitacion real de GenericForeignKey sin GenericRelation inversa,
    se calcula aparte y se adjunta como atributo). Marca `obj.
    has_alert = True` cuando el sujeto tiene AL MENOS un documento
    vigente de un tipo `tracks_expiry=True` sin fecha o con fecha ya
    pasada -- para la columna de alerta del listado (Centros de
    Gasto/Personal). Solo sobre la pagina visible, nunca sobre el
    listado completo.
    """
    from datetime import date

    today = date.today()
    pks = [obj.pk for obj in objects]
    alert_pks = set(
        DocumentIndexEntry.objects.filter(
            bucket=BUCKET, domain_content_type=content_type,
            domain_object_id__in=pks, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            is_obsolete=False, document_type__tracks_expiry=True,
        ).filter(Q(expiry_date__isnull=True) | Q(expiry_date__lt=today))
        .values_list("domain_object_id", flat=True).distinct()
    )
    for obj in objects:
        obj.has_alert = obj.pk in alert_pks
    return objects


def _attach_doc_counts(objects, content_type):
    """
    `domain_object` es una GenericForeignKey sin `GenericRelation`
    declarada en el otro extremo (MachineAsset/PersonIdentity) -- no
    existe relación inversa por la que hacer `.annotate(Count(...))`
    directamente. Se calcula aparte, agrupando por `domain_object_id`,
    y se adjunta como atributo `doc_count` a cada objeto ya paginado
    (solo sobre la página visible, nunca sobre la lista completa).
    """
    pks = [obj.pk for obj in objects]
    counts = dict(
        DocumentIndexEntry.objects.filter(
            bucket=BUCKET, domain_content_type=content_type,
            domain_object_id__in=pks, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).values_list("domain_object_id").annotate(n=Count("id")),
    )
    for obj in objects:
        obj.doc_count = counts.get(obj.pk, 0)
    return objects


class DocumentationHubV2View(CompanyUserRequiredMixin, View):
    """GET: página completa, tres pestañas, listado inicial de Centros de Gasto.

    H31 (S75): la pestaña activa y los filtros de cada pestaña se
    restauran desde `PanelNavigationState` (nunca vuelve a la pestaña
    por defecto solo porque el usuario recargó o pulsó atrás -- ver
    panel/views_navigation_state.py). Solo la pestaña de Maquinaria se
    renderiza en el servidor (siempre lo hizo así); Personal/EPIs
    siguen cargándose vía htmx, pero ahora con `hx-trigger="load once"`
    en vez de `"click once"` cuando son la pestaña persistida como
    activa, y con sus filtros ya guardados inyectados en la propia URL
    de la petición htmx (ver hub.html)."""

    def get(self, request):
        nav_state = PanelNavigationState.objects.filter(
            company_user=request.user.company_user, screen_key="documentation_hub",
        ).first()
        state = nav_state.state if nav_state and isinstance(nav_state.state, dict) else {}
        active_tab = state.get("active_tab") or "maquinaria"
        if active_tab not in ("maquinaria", "personal", "epis"):
            active_tab = "maquinaria"
        filters = state.get("filters") if isinstance(state.get("filters"), dict) else {}

        _seed_request_get(request, filters.get("maquinaria"))
        machines_page = _machine_list_page(request)
        return render(request, "panel/documentation_h30/hub.html", {
            "active_tab": "maquinaria",
            "machines_page": machines_page,
            "active_nav": "documentation_hub",
            "persisted_active_tab": active_tab,
            "persisted_filters": filters,
        })


def _seed_request_get(request, persisted_filters):
    """
    H31 (S75). Rellena `request.GET` con los filtros persistidos
    (`q`/`sort`/`dir`) para las claves que la propia querystring real
    NO trae -- así una recarga sin parámetros en la URL sigue viendo
    los últimos filtros aplicados por el usuario, sin que un enlace
    explícito (que sí trae querystring) pierda nunca la prioridad.
    `request.GET` es un QueryDict inmutable por defecto; se sustituye
    por una copia mutable solo si hace falta cambiar algo.
    """
    if not persisted_filters:
        return
    mutable = None
    for key, value in persisted_filters.items():
        if key not in request.GET and value:
            if mutable is None:
                mutable = request.GET.copy()
            mutable[key] = value
    if mutable is not None:
        request.GET = mutable


def _machine_list_page(request):
    qs = MachineAsset.objects.filter(is_active=True)
    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(
            Q(code__icontains=search) | Q(brand_model__icontains=search)
            | Q(plate__icontains=search),
        )
    sort_columns = [("code", "Código"), ("brand_model", "Marca/modelo")]
    qs, sort_key, sort_dir = _apply_sort(request, qs, sort_columns, "code")
    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page"))
    page.object_list = _attach_doc_counts(
        list(page.object_list), ContentType.objects.get_for_model(MachineAsset),
    )
    page.object_list = _attach_alert_flags(
        page.object_list, ContentType.objects.get_for_model(MachineAsset),
    )
    return {
        "page": page, "sort_key": sort_key, "sort_dir": sort_dir,
        "search": search, "sort_columns_machine": sort_columns,
    }


class MachineListFragmentView(CompanyUserRequiredMixin, View):
    def get(self, request):
        ctx = _machine_list_page(request)
        return render(request, "panel/documentation_h30/_machine_results.html", ctx)


class MachineDetailView(CompanyUserRequiredMixin, View):
    def get(self, request, pk):
        machine = get_object_or_404(MachineAsset, pk=pk)
        ct = ContentType.objects.get_for_model(MachineAsset)
        entries = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, domain_content_type=ct, domain_object_id=machine.pk,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).select_related("document_type").order_by("-id")
        current, obsolete = _split_current_obsolete(entries)
        doc_types = DocumentTypeCatalog.objects.filter(
            is_active=True, domain__in=["MACHINE", "BOTH"],
        ).order_by("label")
        return render(request, "panel/documentation_h30/_machine_detail.html", {
            "machine": machine, "current": current, "obsolete": obsolete,
            "doc_types": doc_types, "active_nav": "documentation_hub",
            "family_choices": DocumentTypeCatalog.FAMILY_CHOICES,
        })


def _person_list_page(request):
    qs = PersonIdentity.objects.all()
    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(
            Q(first_surname__icontains=search)
            | Q(second_surname__icontains=search)
            | Q(given_name__icontains=search) | Q(dni__icontains=search),
        )
    sort_columns = [("first_surname", "Primer apellido"), ("dni", "DNI")]
    qs, sort_key, sort_dir = _apply_sort(
        request, qs, sort_columns, "first_surname",
    )
    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page"))
    page.object_list = _attach_doc_counts(
        list(page.object_list), ContentType.objects.get_for_model(PersonIdentity),
    )
    page.object_list = _attach_alert_flags(
        page.object_list, ContentType.objects.get_for_model(PersonIdentity),
    )
    return {
        "page": page, "sort_key": sort_key, "sort_dir": sort_dir,
        "search": search, "sort_columns_person": sort_columns,
    }


class PersonalListFragmentView(CompanyUserRequiredMixin, View):
    """Carga inicial de la pestana Personal (click once) -- formulario
    + resultados envueltos, una unica vez.

    H31 (S75): añade también el catálogo de EPIs y los tipos de
    notificación/circular con content_html real -- los necesita la
    barra de acción masiva de `_personal_pane.html` (punto 1 de la
    hoja de ruta). Se cargan una única vez aquí (carga inicial de la
    pestaña), nunca en `_person_list_page`/`PersonalResultsFragmentView`
    -- esas solo repintan la tabla de resultados en cada búsqueda o
    paginación, la barra de acción masiva no se vuelve a pintar."""

    def get(self, request):
        ctx = _person_list_page(request)
        ctx["epi_items"] = EpiItemCatalog.objects.filter(
            is_active=True,
        ).order_by("family", "label")
        ctx["notification_types"] = DocumentTypeCatalog.objects.filter(
            is_active=True, domain__in=["PERSONAL", "BOTH"],
        ).exclude(content_html="").order_by("label")
        return render(request, "panel/documentation_h30/_personal_pane.html", ctx)


class PersonalResultsFragmentView(CompanyUserRequiredMixin, View):
    """Busqueda/orden/paginacion dentro de Personal -- solo los
    resultados, el formulario nunca se vuelve a pintar (H30 S50, ver
    _personal_search_form.html)."""

    def get(self, request):
        ctx = _person_list_page(request)
        return render(request, "panel/documentation_h30/_personal_results.html", ctx)


class PersonalDetailView(CompanyUserRequiredMixin, View):
    def get(self, request, pk):
        person = get_object_or_404(
            PersonIdentity.objects.select_related(
                "company_user", "company_user__user",
            ),
            pk=pk,
        )
        ct = ContentType.objects.get_for_model(PersonIdentity)
        entries = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, domain_content_type=ct, domain_object_id=person.pk,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).select_related("document_type").order_by("-id")
        current, obsolete = _split_current_obsolete(entries)
        # H31 (S74). Avatar -- reutiliza el mismo mecanismo genérico
        # domain_content_type/domain_object_id que cualquier otro
        # documento vinculado, filtrando por el código de catálogo
        # IMAGEN ya sembrado (H30 S67). Sin campo dedicado nuevo en
        # PersonIdentity -- decisión confirmada por Miguel Ángel en
        # S73. El más reciente gana si hay más de una imagen vigente.
        avatar = entries.filter(document_type__code="IMAGEN").first()
        doc_types = DocumentTypeCatalog.objects.filter(
            is_active=True, domain__in=["PERSONAL", "BOTH"],
        ).order_by("label")
        notification_types = DocumentTypeCatalog.objects.filter(
            is_active=True, domain__in=["PERSONAL", "BOTH"],
        ).exclude(content_html="").order_by("label")
        epi_deliveries = EpiDelivery.objects.filter(
            person=person,
        ).select_related("epi").order_by("-delivery_date")
        epi_items = EpiItemCatalog.objects.filter(
            is_active=True,
        ).order_by("family", "label")
        return render(request, "panel/documentation_h30/_personal_detail.html", {
            "person": person, "current": current, "obsolete": obsolete,
            "avatar": avatar,
            "doc_types": doc_types, "epi_deliveries": epi_deliveries,
            "epi_items": epi_items,
            "notification_types": notification_types,
            "active_nav": "documentation_hub",
            "family_choices": DocumentTypeCatalog.FAMILY_CHOICES,
        })


class EpiIndividualDeliveryView(DocsUploadAccessMixin, View):
    """
    H31 (S74), punto 3 de la hoja de ruta. POST: registra una entrega
    individual de EPI desde la ficha de persona -- desplegable de
    EpiItemCatalog + fecha, crea un EpiDelivery real con
    extraction_method=MANUAL (panel), igual criterio que el resto de
    entregas manuales del sistema. Sin destination_machine aquí --
    ese campo es para EPIs con Centro de Gasto de destino (botiquines
    y similares), fuera de alcance de la entrega individual estándar
    de este punto.
    """

    def post(self, request, pk):
        person = get_object_or_404(PersonIdentity, pk=pk)
        epi_id = request.POST.get("epi_id", "")
        delivery_date = request.POST.get("delivery_date", "")
        if not epi_id or not delivery_date:
            return JsonResponse(
                {"ok": False, "error": "EPI y fecha de entrega son obligatorios."},
                status=400,
            )
        epi = get_object_or_404(EpiItemCatalog, pk=epi_id, is_active=True)
        delivery = EpiDelivery.objects.create(
            person=person, epi=epi, delivery_date=delivery_date,
            extraction_method=EpiDelivery.METHOD_MANUAL,
        )
        # H31 (S74), requisito explícito de Miguel Ángel: confirmación
        # WhatsApp al trabajador para que quede constancia por escrito
        # de la entrega. No bloqueante -- la entrega ya está en BD;
        # si el WhatsApp falla (sin teléfono, sin Company vinculada,
        # plantilla aún no aprobada por Meta...) se loguea y se
        # informa en la respuesta, pero la entrega NUNCA se revierte.
        whatsapp_sent = send_epi_delivery_whatsapp_confirmation(delivery)
        return JsonResponse({
            "ok": True,
            "whatsapp_sent": whatsapp_sent,
            "delivery": {
                "id": delivery.pk,
                "epi_label": epi.label,
                "delivery_date": delivery.delivery_date.isoformat(),
            },
        })


class PersonalUpdateView(DocsUploadAccessMixin, View):
    """
    H31 (S74). POST: edita los campos reales de PersonIdentity que
    tiene sentido de negocio corregir a mano desde el panel --
    given_name/first_surname/second_surname/phone/email. El resto de
    campos del modelo (dni, is_active_employee, employer_company,
    fechas de caducidad, ss_affiliation_number) son datos de
    `import_worker_machine_excel` -- editarlos a mano aquí quedaría
    sobrescrito por la siguiente importación real del Excel, así que
    se muestran de solo lectura en la ficha, nunca en este formulario.
    Mismo control de acceso que subir/eliminar documentos
    (DocsUploadAccessMixin) -- editar la ficha es una acción de
    escritura, no de simple consulta.
    """

    EDITABLE_FIELDS = (
        "given_name", "first_surname", "second_surname", "phone", "email",
    )

    def post(self, request, pk):
        person = get_object_or_404(PersonIdentity, pk=pk)
        updated_fields = []
        for field in self.EDITABLE_FIELDS:
            if field in request.POST:
                setattr(person, field, request.POST.get(field, "").strip())
                updated_fields.append(field)
        if not updated_fields:
            return JsonResponse(
                {"ok": False, "error": "Sin campos que actualizar."}, status=400,
            )
        try:
            person.full_clean(validate_unique=False)
        except ValidationError as exc:
            return JsonResponse(
                {"ok": False, "error": "; ".join(exc.messages)}, status=400,
            )
        person.save(update_fields=updated_fields)
        return JsonResponse({
            "ok": True,
            "person": {f: getattr(person, f) for f in self.EDITABLE_FIELDS},
        })


class NotificationEmlError(Exception):
    """Fallo esperado (no técnico) al construir el .eml de una notificación
    -- tipo sin content_html, o persona sin email. Se distingue de una
    excepción real para poder recolectar fallos por persona en la vista
    masiva sin abortar el resto del lote."""


def _build_notification_eml(person, document_type):
    """
    H31 (S74/S75). Construye el `.eml` real de una notificación/circular
    para UNA persona -- extraído de `PersonalNotificationSendView` (S74)
    para que la vista individual (GET, descarga directa) y la vista
    masiva (S75, POST, bucle + zip) compartan exactamente la misma
    lógica de construcción (principio DRY, mismo criterio que
    `ai_services`). Devuelve los bytes del mensaje MIME completo; nunca
    toca BD (el registro de `DocumentAcknowledgment` sigue siendo
    responsabilidad de cada vista que llama a esto, igual que antes).

    Lanza `NotificationEmlError` -- nunca HttpResponse -- para que
    ambas vistas decidan cómo comunicar el fallo (una respuesta 400
    directa en la individual, una entrada más en la lista de errores
    del lote en la masiva).
    """
    if not document_type.content_html.strip():
        raise NotificationEmlError(
            f"El tipo '{document_type.label}' todavía no tiene "
            f"contenido enriquecido cargado (content_html vacío).",
        )

    recipient = (person.email or "").strip()
    if not recipient:
        raise NotificationEmlError(
            f"{person} no tiene correo electrónico registrado -- no se "
            f"puede generar la notificación.",
        )

    msg = StdEmailMessage()
    msg["Subject"] = f"{document_type.label} -- {person}"
    msg["From"] = "notificaciones@grupoalvarez.local"
    msg["To"] = recipient

    msg.set_content(
        f"Notificación para {person}: {document_type.label}.\n"
        "Este cliente de correo no muestra HTML -- consulte la "
        "versión web o abra este mensaje con un cliente compatible."
    )

    logo_cid = make_msgid()
    html_body = f"""
        <html><body style="font-family: Arial, sans-serif;">
          <p style="margin-bottom:16px;">
            <img src="cid:{logo_cid[1:-1]}" alt="Grupo Álvarez" height="40">
          </p>
          <p>Estimado/a <strong>{person}</strong>,</p>
          {document_type.content_html}
          <p style="margin-top:24px;">Un saludo,<br>Grupo Álvarez</p>
        </body></html>
    """
    msg.add_alternative(html_body, subtype="html")

    logo_path = find_static("panel/img/grupo_alvarez_logo.png")
    if logo_path:
        with open(logo_path, "rb") as logo_file:
            msg.get_payload()[1].add_related(
                logo_file.read(), "image", "png", cid=logo_cid,
            )

    filename = f"notificacion_{document_type.code.lower()}_{person.pk}.eml"
    return bytes(msg), filename


class PersonalNotificationSendView(DocsUploadAccessMixin, View):
    """
    H31 (S74), punto 4 de la hoja de ruta. Genera y sirve para
    descarga un `.eml` real con el contenido enriquecido de un tipo
    documental de circular/notificación (DocumentTypeCatalog.
    content_html, punto 1 de esta misma hoja de ruta) -- sustituye a
    PersonalTestEmlView (S73, prueba de concepto con contenido fijo,
    retirada aquí junto con su botón en la plantilla, punto 7).

    Misma técnica ya validada con Outlook real en S73 (email.message.
    EmailMessage.add_alternative, subtype='html'), con dos añadidos
    reales de este punto:
    1. Logo corporativo incrustado como adjunto INLINE con
       Content-ID (add_related) -- nunca <img src> remoto, porque
       Outlook y la mayoría de clientes de correo bloquean imágenes
       remotas por defecto; la incrustación inline es la única forma
       de que se vea siempre, sin depender de que el destinatario
       decida descargar imágenes ni de que gruasalvarez.com siga
       accesible en ese momento.
    2. Registra un DocumentAcknowledgment real (extraction_method=
       MANUAL) al generar el .eml -- deja constancia de que la
       notificación se envió, mismo principio que EpiDelivery para
       los EPIs (una fila por entrega/envío, nunca un documento
       nuevo duplicado).

    Sigue sin haber envío SMTP real desde el servidor -- el proyecto
    no tiene EMAIL_BACKEND configurado (verificado en
    enterprise_core/settings.py). El .eml se descarga y el supervisor
    lo abre/reenvía desde su propio Outlook, exactamente el flujo ya
    confirmado por Miguel Ángel en S73.

    S75: la construcción del .eml en sí vive ahora en
    `_build_notification_eml` (ver arriba), compartida con
    `PersonalNotificationMassSendView`. Esta vista solo resuelve el
    tipo documental, llama al helper, registra el DocumentAcknowledgment
    y sirve la descarga -- sin cambio de comportamiento observable.
    """

    def get(self, request, pk):
        person = get_object_or_404(PersonIdentity, pk=pk)
        type_code = request.GET.get("tipo", "").strip()
        if not type_code:
            return HttpResponse(
                "Falta el parámetro 'tipo' (código del tipo documental "
                "a notificar).", status=400,
            )
        document_type = get_object_or_404(
            DocumentTypeCatalog, code=type_code, is_active=True,
        )

        try:
            eml_bytes, filename = _build_notification_eml(person, document_type)
        except NotificationEmlError as exc:
            return HttpResponse(str(exc), status=400)

        DocumentAcknowledgment.objects.create(
            person=person,
            document_type=document_type,
            delivery_date=timezone.localdate(),
            extraction_method=DocumentAcknowledgment.METHOD_MANUAL,
        )

        response = HttpResponse(eml_bytes, content_type="message/rfc822")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class EpiMassDeliveryView(DocsUploadAccessMixin, View):
    """
    H31 (S75), punto 1 de la hoja de ruta. POST: entrega masiva de UN
    EPI a un conjunto de personas seleccionadas (casillero del listado
    Personal) -- mismo backend que `EpiIndividualDeliveryView` (S74),
    en bucle sobre `person_ids`, un `EpiDelivery(extraction_method=
    MANUAL)` real por persona, sin destination_machine (mismo alcance
    que la entrega individual estándar). WhatsApp de confirmación
    igual de no bloqueante que en la entrega individual -- un fallo de
    WhatsApp de una persona nunca revierte su entrega ya comprometida
    en BD, ni afecta al resto del lote.

    `person_ids` llega como lista de pks (checkboxes marcados en el
    listado). Personas repetidas o inexistentes se ignoran sin abortar
    el resto -- se informan en `errors` de la respuesta.
    """

    def post(self, request):
        person_ids = request.POST.getlist("person_ids")
        epi_id = request.POST.get("epi_id", "")
        delivery_date = request.POST.get("delivery_date", "")

        if not person_ids:
            return JsonResponse(
                {"ok": False, "error": "No hay ninguna persona seleccionada."},
                status=400,
            )
        if not epi_id or not delivery_date:
            return JsonResponse(
                {"ok": False, "error": "EPI y fecha de entrega son obligatorios."},
                status=400,
            )
        epi = get_object_or_404(EpiItemCatalog, pk=epi_id, is_active=True)

        created = []
        errors = []
        whatsapp_sent_count = 0
        for person_id in person_ids:
            try:
                person = PersonIdentity.objects.get(pk=person_id)
            except (PersonIdentity.DoesNotExist, ValueError):
                errors.append({"person_id": person_id, "error": "Persona no encontrada."})
                continue
            delivery = EpiDelivery.objects.create(
                person=person, epi=epi, delivery_date=delivery_date,
                extraction_method=EpiDelivery.METHOD_MANUAL,
            )
            if send_epi_delivery_whatsapp_confirmation(delivery):
                whatsapp_sent_count += 1
            created.append({"person_id": person.pk, "delivery_id": delivery.pk})

        return JsonResponse({
            "ok": True,
            "created_count": len(created),
            "whatsapp_sent_count": whatsapp_sent_count,
            "created": created,
            "errors": errors,
        })


class PersonalNotificationMassSendView(DocsUploadAccessMixin, View):
    """
    H31 (S75), punto 1 de la hoja de ruta. POST: envío masivo de UNA
    circular/notificación a un conjunto de personas seleccionadas --
    mismo backend que `PersonalNotificationSendView` (S74) vía
    `_build_notification_eml`, en bucle sobre `person_ids`. A
    diferencia de la vista individual (un único `.eml` servido
    directo), aquí se generan varios `.eml` a la vez -- se empaquetan
    en un único `.zip` de descarga (un archivo por persona, nombrado
    igual que en la individual) para que el navegador no tenga que
    manejar N descargas simultáneas.

    Cada persona con éxito registra su propio `DocumentAcknowledgment`
    real (mismo criterio que la individual -- una fila por envío).
    Las personas sin email registrado o sin content_html en el tipo
    (situación ya cubierta por la individual) se omiten del zip y se
    listan en `X-Mass-Errors` (cabecera JSON) -- nunca abortan el
    resto del lote. Si NINGUNA persona resulta válida, se devuelve
    JSON de error puro (sin zip) para que el frontend lo muestre igual
    que cualquier otro fallo, sin intentar descargar un zip vacío.
    """

    def post(self, request):
        import io
        import json
        import zipfile

        person_ids = request.POST.getlist("person_ids")
        type_code = request.POST.get("tipo", "").strip()

        if not person_ids:
            return JsonResponse(
                {"ok": False, "error": "No hay ninguna persona seleccionada."},
                status=400,
            )
        if not type_code:
            return JsonResponse(
                {"ok": False, "error": "Falta el tipo de circular/notificación."},
                status=400,
            )
        document_type = get_object_or_404(
            DocumentTypeCatalog, code=type_code, is_active=True,
        )

        errors = []
        zip_buffer = io.BytesIO()
        created_count = 0
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for person_id in person_ids:
                try:
                    person = PersonIdentity.objects.get(pk=person_id)
                except (PersonIdentity.DoesNotExist, ValueError):
                    errors.append({"person_id": person_id, "error": "Persona no encontrada."})
                    continue
                try:
                    eml_bytes, filename = _build_notification_eml(person, document_type)
                except NotificationEmlError as exc:
                    errors.append({"person_id": person.pk, "error": str(exc)})
                    continue
                zf.writestr(filename, eml_bytes)
                DocumentAcknowledgment.objects.create(
                    person=person,
                    document_type=document_type,
                    delivery_date=timezone.localdate(),
                    extraction_method=DocumentAcknowledgment.METHOD_MANUAL,
                )
                created_count += 1

        if created_count == 0:
            return JsonResponse(
                {"ok": False, "error": "Ninguna persona válida para el envío.", "errors": errors},
                status=400,
            )

        response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
        safe_type = type_code.lower()
        today = timezone.localdate().isoformat()
        response["Content-Disposition"] = (
            f'attachment; filename="notificaciones_masivas_{safe_type}_{today}.zip"'
        )
        response["X-Mass-Created-Count"] = str(created_count)
        response["X-Mass-Errors"] = json.dumps(errors)
        return response


def _epi_list_page(request):
    qs = EpiDelivery.objects.select_related("person", "epi").order_by(
        "-delivery_date",
    )
    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(
            Q(person__first_surname__icontains=search)
            | Q(person__given_name__icontains=search)
            | Q(epi__label__icontains=search),
        )
    sort_columns = [
        ("delivery_date", "Fecha de entrega"),
        ("person__first_surname", "Trabajador"),
        ("epi__label", "EPI"),
    ]
    qs, sort_key, sort_dir = _apply_sort(
        request, qs, sort_columns, "-delivery_date",
    )
    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page"))
    return {
        "page": page, "sort_key": sort_key, "sort_dir": sort_dir,
        "search": search, "sort_columns_epi": sort_columns,
    }


class EpiTabFragmentView(CompanyUserRequiredMixin, View):
    """Carga inicial de la pestana EPIs (click once) -- formulario +
    resultados envueltos + catalogo lateral, una unica vez."""

    def get(self, request):
        ctx = _epi_list_page(request)
        ctx["catalog"] = EpiItemCatalog.objects.filter(is_active=True).order_by(
            "family", "label",
        )
        return render(request, "panel/documentation_h30/_epi_pane.html", ctx)


class EpiResultsFragmentView(CompanyUserRequiredMixin, View):
    """Busqueda/orden/paginacion dentro de EPIs -- solo los resultados,
    el formulario y el catalogo lateral nunca se vuelven a pintar
    (H30 S50, ver _epi_search_form.html)."""

    def get(self, request):
        ctx = _epi_list_page(request)
        return render(request, "panel/documentation_h30/_epi_results.html", ctx)


class DocumentViewView(CompanyUserRequiredMixin, View):
    """GET: redirige a la URL firmada (GCS) real del documento -- 'Ver'."""

    def get(self, request, pk):
        entry = get_object_or_404(
            DocumentIndexEntry, pk=pk, deleted_at__isnull=True,
        )
        url = generate_signed_url(entry.bucket, entry.blob_name)
        return redirect(url)


class DocumentDeleteView(DocsUploadAccessMixin, View):
    """POST: borrado blando (papelera) -- nunca toca GCS (4.12)."""

    def post(self, request, pk):
        entry = get_object_or_404(
            DocumentIndexEntry, pk=pk, deleted_at__isnull=True,
        )
        entry.deleted_at = timezone.now()
        company_user = getattr(request.user, "company_user", None)
        if company_user:
            entry.deleted_by = company_user
        entry.save(update_fields=["deleted_at", "deleted_by"])
        return JsonResponse({"ok": True})


class SubjectDocumentUploadView(DocsUploadAccessMixin, View):
    """
    POST: sube uno o VARIOS documentos nuevos a la vez desde la ficha
    de un sujeto -- domain ('machine'|'personal'), subject_pk,
    document_type_code, file[] (uno o varios), expiry_date
    (YYYY-MM-DD, se aplica igual a todos los archivos del lote --
    Miguel Ángel, S48: "si queremos meter en una carpeta varias ITVs,
    darle al botón y subirlo todo de golpe"). Ver
    document_explorer.subject_upload_service para el flujo por
    archivo (contraste OCR/Gemini + sustitución con marcado
    is_obsolete).
    """

    def post(self, request, domain, subject_pk):
        document_type_code = request.POST.get("document_type_code", "")
        expiry_date_str = request.POST.get("expiry_date", "")
        uploaded_files = request.FILES.getlist("file")

        if not uploaded_files or not document_type_code:
            return JsonResponse(
                {"error": "Falta el archivo o el tipo documental."},
                status=400,
            )

        document_type = get_object_or_404(
            DocumentTypeCatalog, code=document_type_code, is_active=True,
        )

        typed_date = None
        if expiry_date_str:
            from datetime import date
            try:
                year, month, day = (int(x) for x in expiry_date_str.split("-"))
                typed_date = date(year, month, day)
            except ValueError:
                return JsonResponse(
                    {"error": "Fecha con formato inválido."}, status=400,
                )

        if domain == "machine":
            subject = get_object_or_404(MachineAsset, pk=subject_pk)
            ct = ContentType.objects.get_for_model(MachineAsset)
            subject_label = "%s -- %s" % (subject.code, subject.brand_model)
        else:
            subject = get_object_or_404(PersonIdentity, pk=subject_pk)
            ct = ContentType.objects.get_for_model(PersonIdentity)
            subject_label = "%s %s, %s" % (
                subject.first_surname, subject.second_surname,
                subject.given_name,
            )

        results = []
        errors = []
        for uploaded_file in uploaded_files:
            data = uploaded_file.read()
            try:
                result = upload_subject_document(
                    subject=subject, domain_content_type=ct,
                    document_type=document_type, data=data,
                    original_filename=uploaded_file.name,
                    typed_date=typed_date, subject_label=subject_label,
                )
            except SubjectUploadError as exc:
                errors.append({"file": uploaded_file.name, "error": str(exc)})
                continue
            entry_result = {
                "entry_id": result["entry"].pk,
                "entry_name": result["entry"].name,
                "superseded_count": result["superseded_count"],
            }
            if result["warning"]:
                entry_result["warning"] = {
                    "system_date": result["warning"]["system_date"].isoformat(),
                    "typed_date": result["warning"]["typed_date"].isoformat(),
                    "source": result["warning"]["source"],
                }
            results.append(entry_result)

        return JsonResponse({
            "ok": not errors, "uploaded": results, "errors": errors,
        })


class DocumentTypeQuickCreateView(DocsUploadAccessMixin, View):
    """
    H30 (S51). Atajo de alta de tipo documental nuevo desde el propio
    flujo de subida del panel -- para cuando el supervisor no
    encuentra el tipo en el desplegable, sin salir a la pantalla del
    Catálogo de tipos del explorador (`document_explorer.
    DocumentTypeCatalogCreateView`, restringida a admin). Abierto a
    ADMIN y DOCS_SUPERVISOR, decisión explícita de Miguel Ángel (S51):
    "a todo lo que haya dentro [de documentación] deben de poder
    acceder tanto administradores como supervisores de documentación."

    `family` es obligatoria y se elige de las choices fijas del
    modelo (10 familias + la 11.ª "Otros documentos" añadida en esta
    misma sesión, migración 0032) -- nunca texto libre ni creación de
    familia nueva, decisión de S49 explícitamente no revertida en S51.

    `code` se deriva automáticamente del `label` con el mismo
    `naming_service._sanitize_token()` que usa el motor de
    renombrado, para no pedirle al supervisor un código técnico
    aparte. `domain` se fija según la pestaña de origen (`machine` /
    `personal`) -- no `BOTH`; si un tipo aplica a los dos dominios a
    la vez, es un alta que debe hacerse desde el Catálogo de tipos del
    explorador (fuera de alcance de este atajo).

    ---

    Shortcut to add a new document type from the panel's own upload
    flow -- for when the supervisor cannot find the type in the
    dropdown, without leaving to the explorer's Type Catalog screen
    (`document_explorer.DocumentTypeCatalogCreateView`, admin-only).
    Open to ADMIN and DOCS_SUPERVISOR, Miguel Ángel's explicit S51
    decision.
    """

    def post(self, request, domain):
        if domain == "machine":
            catalog_domain = DocumentTypeCatalog.DOMAIN_MACHINE
        elif domain == "personal":
            catalog_domain = DocumentTypeCatalog.DOMAIN_PERSONAL
        else:
            return JsonResponse({"error": "Dominio no válido."}, status=400)

        label = (request.POST.get("label") or "").strip()
        family = (request.POST.get("family") or "").strip()
        tracks_expiry = request.POST.get("tracks_expiry") in ("true", "on", "1")

        valid_families = dict(DocumentTypeCatalog.FAMILY_CHOICES)
        if not label:
            return JsonResponse(
                {"error": "Falta el nombre visible del tipo documental."},
                status=400,
            )
        if family not in valid_families:
            return JsonResponse(
                {"error": "Falta elegir una familia documental válida."},
                status=400,
            )

        code = naming_service._sanitize_token(label)
        if not code:
            return JsonResponse(
                {"error": "El nombre visible no genera un código válido."},
                status=400,
            )

        if DocumentTypeCatalog.objects.filter(code=code).exists():
            return JsonResponse(
                {
                    "error": (
                        "Ya existe un tipo documental con código «%s» "
                        "-- revisa el desplegable, puede que ya esté "
                        "ahí con otro nombre visible." % code
                    ),
                },
                status=409,
            )

        document_type = DocumentTypeCatalog.objects.create(
            code=code, label=label, domain=catalog_domain,
            family=family, tracks_expiry=tracks_expiry,
        )
        return JsonResponse({
            "ok": True,
            "code": document_type.code,
            "label": document_type.label,
            "tracks_expiry": document_type.tracks_expiry,
        })
