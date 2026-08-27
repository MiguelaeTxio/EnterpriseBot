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
from django.urls import reverse
from django.utils import timezone
from django.views import View
from email.message import EmailMessage as StdEmailMessage
from email.utils import make_msgid
import unicodedata

from document_explorer import naming_service
from document_explorer.index_writer import ensure_folder_chain
from document_explorer.models import (
    DocumentAcknowledgment, DocumentIndexEntry, DocumentTypeCatalog,
    EpiDelivery, EpiItemCatalog, EpiReview, PersonIdentity, path_digest,
)
from document_explorer.subject_upload_service import (
    SubjectUploadError, upload_subject_document,
)
from document_management.vigencia_service import DocumentSnapshot, is_current
from fleet.models import MachineAsset
from hr_calendar.models import VacationPeriod
from panel.mixins import CompanyUserRequiredMixin, DocsUploadAccessMixin
from panel.models import PanelNavigationState
from spare_parts.gcs_service import generate_signed_url, upload_bytes
from whatsapp.services import send_epi_delivery_whatsapp_confirmation
from work_order_processor.models import WorkOrder, WorkOrderEntry

BUCKET = "cgs_grupo_alvarez"

# H31 (S76). Carpeta virtual dedicada a manuales/fichas técnicas de
# EPI del catálogo -- mismo criterio de nomenclatura que
# `_PLANTILLAS_CIRCULARES` (circulars_h31) y `_CUARENTENA`
# (document_explorer.buckets): prefijo `_` para distinguirla de las
# carpetas reales de DOC. PERSONAL/DOC. MAQUINAS. No pertenece a
# ningún sujeto -- domain_content_type/domain_object_id quedan nulos.
EPI_TECHNICAL_SHEETS_ROOT = "_FICHAS_TECNICAS_EPI"

# H31 (S76). Casillero de empresa del listado Personal -- valores
# reales de PersonIdentity.employer_company (texto libre del Excel de
# plantilla, confirmados contra BD real, S76) agrupados en las 4
# empresas reales que confirmó Miguel Ángel. Slug estable (sin
# acentos/espacios, para el valor del checkbox) -> (etiqueta visible,
# lista de valores crudos reales que agrupa). "TRANSGRUAL S.L." (con
# puntos) y "TRANSGRUAL Y ASITENCIA" son variantes de escritura de la
# misma empresa -- decisión explícita de Miguel Ángel (S76): "ya
# alguien dice que esto es un error, ya lo cambiamos en ese momento,
# de momento ponlo así." Los 160 PersonIdentity con employer_company
# vacío (sin cruzar contra el Excel, dato real S76) quedan en su
# propia opción "sin_empresa" -- ninguno se oculta en silencio.
COMPANY_FILTER_CHOICES = [
    ("adolfo_alvarez", "Grúas Adolfo Álvarez S.L.", ["GRUAS ADOLFO ALVAREZ SL"]),
    ("transgrual", "Transgrúal S.L.", [
        "TRANSGRUAL SL", "TRANSGRUAL S.L.", "TRANSGRUAL Y ASITENCIA",
    ]),
    ("aldi", "Grúas Aldi S.L.", ["GRUALDI S.L"]),
    ("asistencia_granada", "Asistencia y Grúas Granada", ["ASIST.GRUAS GRANADA"]),
    ("sin_empresa", "Sin empresa asignada", [""]),
]


def _apply_personal_filters(qs, request):
    """
    H31 (S76). Casillero Activos/Inactivos + casillero de empresa del
    listado Personal -- lógica literal de checkbox (ninguno marcado =
    ningún resultado, nunca "sin filtro" por sorpresa).

    Activos = `is_active_employee=True` (está en el Excel real de
    plantilla). Inactivos = `False` **o** `None` juntos -- decisión
    explícita de Miguel Ángel (S76), motivo real: en la ingesta de
    documentos históricos, las personas ya no activas nunca se
    marcaron `False` a propósito, simplemente no se cruzaron contra
    el Excel (`None`, "sin cruzar todavía"), así que en la práctica
    todo el histórico real vive en `None`, no en `False` (confirmado
    contra BD real S76: `True`=71, `False`=0, `None`=158). Miguel
    Ángel, verbatim: "los activos son los del Excel y los que no son
    activos no están en el Excel [...] no los vamos a desechar,
    los tratamos como históricos e inactivos."
    """
    active_filter = request.GET.getlist("active")
    if active_filter:
        active_q = Q()
        if "true" in active_filter:
            active_q |= Q(is_active_employee=True)
        if "false" in active_filter:
            active_q |= Q(is_active_employee=False) | Q(is_active_employee__isnull=True)
        qs = qs.filter(active_q)
    else:
        qs = qs.none()

    company_filter = request.GET.getlist("company")
    if company_filter:
        raw_by_slug = {slug: raws for slug, _label, raws in COMPANY_FILTER_CHOICES}
        company_q = Q()
        matched_any = False
        for slug in company_filter:
            raws = raw_by_slug.get(slug)
            if raws is None:
                continue
            matched_any = True
            company_q |= Q(employer_company__in=raws)
        qs = qs.filter(company_q) if matched_any else qs.none()
    else:
        qs = qs.none()

    return qs


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
            "personal_tab_qs": _build_personal_tab_querystring(filters),
        })


def _build_personal_tab_querystring(filters):
    """
    H31 (S76). Querystring lista para usar en el `hx-get` de la
    pestaña Personal -- incluye los casilleros Activos/Inactivos y
    Empresa con sus valores persistidos, o el valor por defecto de la
    PRIMERA vez que este usuario abre la pantalla (Miguel Ángel, S76:
    "la vista inicial por defecto [...] debe de ser activos"): solo
    `active=true` marcado, todas las empresas marcadas. A partir de
    ahí, lo que el usuario elija ya vive en `PanelNavigationState` y
    esta función solo lo traduce de vuelta a querystring -- toda la
    lógica de negocio vive aquí, en la vista, nunca en el template
    (DUMB TEMPLATES).
    """
    from urllib.parse import urlencode

    personal_filters = filters.get("personal") if isinstance(filters, dict) else None
    personal_filters = personal_filters if isinstance(personal_filters, dict) else {}

    params = [
        ("q", personal_filters.get("q", "")),
        ("sort", personal_filters.get("sort", "")),
        ("dir", personal_filters.get("dir", "asc")),
    ]
    active_values = personal_filters.get("active")
    if not isinstance(active_values, list):
        active_values = ["true"]
    for value in active_values:
        params.append(("active", value))

    company_values = personal_filters.get("company")
    if not isinstance(company_values, list):
        company_values = [slug for slug, _label, _raws in COMPANY_FILTER_CHOICES]
    for value in company_values:
        params.append(("company", value))

    return urlencode(params)


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
    qs = _apply_personal_filters(qs, request)
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
        "active_filter": request.GET.getlist("active"),
        "company_filter": request.GET.getlist("company"),
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
        ctx["company_filter_choices"] = COMPANY_FILTER_CHOICES
        return render(request, "panel/documentation_h30/_personal_pane.html", ctx)


class PersonalResultsFragmentView(CompanyUserRequiredMixin, View):
    """Busqueda/orden/paginacion dentro de Personal -- solo los
    resultados, el formulario nunca se vuelve a pintar (H30 S50, ver
    _personal_search_form.html)."""

    def get(self, request):
        ctx = _person_list_page(request)
        return render(request, "panel/documentation_h30/_personal_results.html", ctx)


def _group_current_by_family(current_entries, exclude_family_codes=()):
    """
    H31 (S76). Agrupa los documentos vigentes por la `family` real del
    catálogo -- campo que ya existía exactamente para esto desde H30
    (S49, ver docstring de `DocumentTypeCatalog.family`: "Agrupación
    del acordeón de la ficha"), nunca usado hasta ahora en la ficha de
    persona real. Orden fijo según `FAMILY_CHOICES` (nunca alfabético)
    para que el acordeón se vea siempre en el mismo orden sesión a
    sesión. Los documentos sin `document_type` o sin `family` asignada
    caen en un grupo "Sin familia asignada" al final -- nunca se
    descartan en silencio.

    Punto 5 de la hoja de ruta S76 (Miguel Ángel: "no puede ser que
    veas 50 reconocimientos médicos de primeras, tiene que ver solo el
    último"): `current_entries` ya viene deduplicado por
    `_split_current_obsolete()` -- un vigente por tipo cuando el tipo
    participa en vigencia (`tracks_expiry`); para tipos sin fecha
    (DNI, contratos...) puede haber más de uno si de verdad hay varios
    documentos vigentes simultáneos (p. ej. anverso/reverso) -- no se
    fuerza a uno solo aquí, eso sería perder información real.

    `exclude_family_codes` (H31, S77): families que se muestran en su
    propio acordeón de primer nivel (Laboral, Salud) en vez de aquí
    dentro de Documentación -- se omiten del todo en este bucle para
    no duplicar el documento en dos sitios de la misma ficha. El
    documento sigue existiendo una sola vez en BD; solo cambia dónde
    se pinta.
    """
    by_family = {}
    for entry in current_entries:
        family_code = entry.document_type.family if entry.document_type else ""
        if family_code in exclude_family_codes:
            continue
        by_family.setdefault(family_code, []).append(entry)

    ordered = []
    for code, label in DocumentTypeCatalog.FAMILY_CHOICES:
        if code in exclude_family_codes:
            continue
        if code in by_family:
            ordered.append({
                "code": code, "label": label, "documents": by_family[code],
            })
    if "" in by_family:
        ordered.append({
            "code": "", "label": "Sin familia asignada",
            "documents": by_family[""],
        })
    return ordered


def _normalize_person_name(value):
    """
    H31 (S77). Mayúsculas + espacios colapsados + acentos eliminados,
    para comparar `WorkOrderEntry.worker_name` (texto libre del
    histórico PDF) contra el nombre completo de una `PersonIdentity`.
    ---
    H31 (S77). Uppercase + collapsed whitespace + stripped accents, to
    compare `WorkOrderEntry.worker_name` (free-text historical PDF
    field) against a `PersonIdentity`'s full name.
    """
    value = (value or "").strip().upper()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(value.split())


def _historical_pdf_entries_for_person(person):
    """
    H31 (S77). Vincula entradas del histórico `PDF_UPLOAD` a esta
    `PersonIdentity` por coincidencia EXACTA de nombre normalizado
    (mayúsculas, sin acentos, espacios colapsados) -- criterio
    confirmado por Miguel Ángel tras sondeo real en S77: 504 de 545
    entradas (92.5%) casan así, sin ambigüedad de apellido parcial.
    Las que no casan (histórico de alguien fuera de la plantilla
    activa de hoy) se quedan sin vincular a propósito -- nunca se
    adivina por parecido de apellido, mismo espíritu que la regla ya
    existente de histórico (S73).

    Recorre el histórico completo (hoy ~545 filas con worker_name) en
    Python por cada ficha abierta -- volumen asumible a día de hoy;
    revisar si el histórico PDF crece mucho más.
    ---
    H31 (S77). Links `PDF_UPLOAD` historical entries to this
    `PersonIdentity` by EXACT normalized-name match (uppercase,
    accents stripped, whitespace collapsed) -- criterion confirmed by
    Miguel Ángel after a real survey in S77: 504/545 entries (92.5%)
    match this way, no partial-surname ambiguity. Entries that don't
    match (historical record of someone outside today's active
    roster) are deliberately left unlinked -- never guessed by
    surname resemblance, same spirit as the existing historical rule
    (S73).

    Scans the full historical set (today ~545 rows with worker_name)
    in Python on every ficha load -- acceptable volume today; revisit
    if the PDF historical set grows much further.
    """
    full_name = _normalize_person_name(
        f"{person.given_name} {person.first_surname} {person.second_surname}",
    )
    if not full_name:
        return WorkOrderEntry.objects.none()
    candidates = WorkOrderEntry.objects.filter(
        work_order__source=WorkOrder.Source.PDF_UPLOAD,
    ).exclude(worker_name="").select_related("work_order")
    matched_ids = [
        entry.pk for entry in candidates
        if _normalize_person_name(entry.worker_name) == full_name
    ]
    return WorkOrderEntry.objects.filter(
        pk__in=matched_ids,
    ).select_related("work_order").order_by("-work_date")


def _group_epi_deliveries_by_family(epi_deliveries):
    """
    H31 (S76). Mismo criterio que `_group_current_by_family()` para
    documentos, aplicado a EPIs -- Miguel Ángel: "tenemos otra selva
    en la propia ficha [...] los EPIs ahora mismo es una lista a lo
    bruto." Agrupa por `EpiItemCatalog.family` (texto libre, sin
    choices fijas a diferencia de `DocumentTypeCatalog.family` --
    orden alfabético estable, no hay una lista cerrada que respetar).
    Dentro de cada familia, una fila por EPI (código), mostrando solo
    la entrega MÁS RECIENTE -- el historial completo de entregas del
    mismo EPI (revisiones, sustituciones) vive aparte, bajo demanda
    (`PersonalEpiItemHistoryView`), mismo patrón que el historial de
    documentos.

    Adjunta también `delivery.epi.technical_docs` -- ficha(s)
    técnica(s)/manual(es) del EPI, vía el mecanismo genérico real ya
    existente desde H30 S73 (`DocumentIndexEntry.domain_content_type`/
    `domain_object_id` apuntando a `EpiItemCatalog`, mismo patrón que
    `PersonIdentity`/`MachineAsset`) -- nunca un campo FK único nuevo
    (esa vía se probó y se retiró en la misma sesión S76, redundante y
    no soportaba los casos reales con más de un documento por EPI).
    """
    by_family = {}
    latest_by_epi = {}
    for delivery in epi_deliveries:
        epi_id = delivery.epi_id
        current_latest = latest_by_epi.get(epi_id)
        if current_latest is None or delivery.delivery_date > current_latest.delivery_date:
            latest_by_epi[epi_id] = delivery

    epi_ct = ContentType.objects.get_for_model(EpiItemCatalog)
    epi_ids = [delivery.epi_id for delivery in latest_by_epi.values()]
    technical_docs_by_epi = {}
    for doc in DocumentIndexEntry.objects.filter(
        bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
        domain_content_type=epi_ct, domain_object_id__in=epi_ids,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).order_by("name"):
        technical_docs_by_epi.setdefault(doc.domain_object_id, []).append(doc)

    for delivery in latest_by_epi.values():
        delivery.epi.technical_docs = technical_docs_by_epi.get(delivery.epi_id, [])
        family = delivery.epi.family or "Sin familia asignada"
        by_family.setdefault(family, []).append(delivery)

    return [
        {"label": family, "deliveries": sorted(items, key=lambda d: d.epi.label)}
        for family, items in sorted(by_family.items())
    ]


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
        _laboral_salud_codes = (
            DocumentTypeCatalog.FAMILY_LABORAL,
            DocumentTypeCatalog.FAMILY_SALUD_BAJAS_PERSONA,
        )
        families = _group_current_by_family(
            current, exclude_family_codes=_laboral_salud_codes,
        )
        # H31 (S77). Documentos de las dos families que se sacan de
        # Documentación a su propio acordeón de primer nivel -- el
        # documento es el mismo de siempre (DocumentIndexEntry), solo
        # cambia dónde se pinta (ver docstring de
        # _group_current_by_family, parámetro exclude_family_codes).
        laboral_documents = [
            entry for entry in current
            if entry.document_type
            and entry.document_type.family == DocumentTypeCatalog.FAMILY_LABORAL
        ]
        salud_documents = [
            entry for entry in current
            if entry.document_type
            and entry.document_type.family == DocumentTypeCatalog.FAMILY_SALUD_BAJAS_PERSONA
        ]
        # H31 (S77). Vacaciones real -- VacationPeriod.operator (FK a
        # CompanyUser) + PersonIdentity.company_user (OneToOne, S74),
        # sin nada que resolver por nombre. Vacío para personal de
        # plantilla sin cuenta de panel vinculada.
        vacation_periods = (
            VacationPeriod.objects.filter(
                operator=person.company_user,
            ).order_by("-date_start")
            if person.company_user_id else VacationPeriod.objects.none()
        )
        # H31 (S77). Partes de trabajo digitales -- uploaded_by es el
        # propio operario autenticado (ver panel/views_operator.py y
        # hr_calendar/services.py), vínculo 100% fiable, sin
        # resolución por nombre.
        digital_work_orders = (
            WorkOrder.objects.filter(
                uploaded_by=person.company_user,
                source__in=[WorkOrder.Source.DIGITAL, WorkOrder.Source.GENERATED],
            ).order_by("-upload_date")
            if person.company_user_id else WorkOrder.objects.none()
        )
        # H31 (S77). Histórico PDF resuelto por nombre normalizado --
        # ver _historical_pdf_entries_for_person().
        historical_pdf_entries = _historical_pdf_entries_for_person(person)
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
        epi_families = _group_epi_deliveries_by_family(epi_deliveries)
        epi_items = EpiItemCatalog.objects.filter(
            is_active=True,
        ).order_by("family", "label")
        return render(request, "panel/documentation_h30/_personal_detail.html", {
            "person": person, "current": current, "obsolete": obsolete,
            "families": families,
            "laboral_documents": laboral_documents,
            "salud_documents": salud_documents,
            "vacation_periods": vacation_periods,
            "digital_work_orders": digital_work_orders,
            "historical_pdf_entries": historical_pdf_entries,
            "avatar": avatar,
            "doc_types": doc_types, "epi_deliveries": epi_deliveries,
            "epi_families": epi_families,
            "epi_items": epi_items,
            "notification_types": notification_types,
            "active_nav": "documentation_hub",
            "family_choices": DocumentTypeCatalog.FAMILY_CHOICES,
        })


class PersonalDocumentTypeHistoryView(CompanyUserRequiredMixin, View):
    """
    H31 (S76), punto 5 de la hoja de ruta. GET: historial COMPLETO
    (vigente + obsoletos) de UN tipo documental para UNA persona --
    fragmento cargado bajo demanda, nunca mostrado de primeras en la
    ficha. Miguel Ángel, verbatim (S75): "no puede ser que tenga aquí
    50 reconocimientos médicos y que tú veas los 50 [...] tiene que
    ver el último. Y ahora, cuando quieras ver historial [...] ya te
    metes ahí, que te salgan todos."
    """

    def get(self, request, pk, type_code):
        person = get_object_or_404(PersonIdentity, pk=pk)
        document_type = get_object_or_404(DocumentTypeCatalog, code=type_code)
        ct = ContentType.objects.get_for_model(PersonIdentity)
        entries = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, domain_content_type=ct, domain_object_id=person.pk,
            document_type=document_type, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).order_by("-expiry_date", "-id")
        return render(
            request, "panel/documentation_h30/_personal_document_history.html",
            {"person": person, "document_type": document_type, "entries": entries},
        )


class PersonalEpiItemHistoryView(CompanyUserRequiredMixin, View):
    """
    H31 (S76). GET: historial COMPLETO de entregas de UN EPI para UNA
    persona -- mismo patrón que `PersonalDocumentTypeHistoryView`,
    cargado bajo demanda en el mismo modal genérico del frontend.
    """

    def get(self, request, pk, epi_id):
        person = get_object_or_404(PersonIdentity, pk=pk)
        epi = get_object_or_404(EpiItemCatalog, pk=epi_id)
        deliveries = EpiDelivery.objects.filter(
            person=person, epi=epi,
        ).order_by("-delivery_date")
        return render(
            request, "panel/documentation_h30/_personal_epi_history.html",
            {"person": person, "epi": epi, "deliveries": deliveries},
        )


class EpiTechnicalSheetUploadView(DocsUploadAccessMixin, View):
    """
    H31 (S76, corregido en la misma sesión). POST: sube un manual de
    uso o ficha técnica de UN EPI del catálogo.

    Corrección real: la primera versión de esta vista escribía en un
    campo `EpiItemCatalog.technical_sheet` (FK única) recién creado --
    duplicaba sin saberlo un mecanismo YA EXISTENTE desde H30 S73
    (`DocumentIndexEntry.domain_content_type`/`domain_object_id`
    apuntando a `EpiItemCatalog`, mismo patrón genérico que ya usan
    `PersonIdentity`/`MachineAsset`), que además ya tenía 7 documentos
    reales vinculados (verificado contra BD, S76). El campo nuevo se
    retiró (migración 0065); esta vista ahora escribe sobre el
    mecanismo real. A diferencia de una FK única, este SÍ soporta
    varios documentos por EPI (ficha técnica + declaración de
    conformidad, caso real ya existente) -- cada subida AÑADE un
    documento nuevo, nunca sustituye al anterior (4.12: ni siquiera se
    plantea "sustituir", el archivo real nunca se toca ni se borra).
    """

    def post(self, request, epi_id):
        epi = get_object_or_404(EpiItemCatalog, pk=epi_id)
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return JsonResponse(
                {"ok": False, "error": "Falta el archivo de la ficha técnica."},
                status=400,
            )

        document_type = get_object_or_404(
            DocumentTypeCatalog, code="FICHA_TECNICA_EPI",
        )
        data = uploaded_file.read()
        extension = (
            uploaded_file.name.rsplit(".", 1)[-1].lower()
            if "." in uploaded_file.name else "bin"
        )
        today = timezone.now().date()
        filename = "%s_FICHA_TECNICA_%s_%s.%s" % (
            epi.code, today.isoformat(), DocumentIndexEntry.objects.count(), extension,
        )
        target_folder = "%s/%s" % (EPI_TECHNICAL_SHEETS_ROOT, epi.code)
        ensure_folder_chain(BUCKET, target_folder)
        blob_name = "%s/%s" % (target_folder, filename)
        content_type = (
            "application/pdf" if extension == "pdf" else "application/octet-stream"
        )
        upload_bytes(BUCKET, blob_name, data, content_type=content_type)

        epi_ct = ContentType.objects.get_for_model(EpiItemCatalog)
        entry = DocumentIndexEntry.objects.create(
            bucket=BUCKET,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            blob_name=blob_name,
            blob_name_hash=path_digest(blob_name),
            parent_path=target_folder,
            parent_path_hash=path_digest(target_folder),
            name=filename,
            size_bytes=len(data),
            content_type=content_type,
            document_type=document_type,
            domain_content_type=epi_ct,
            domain_object_id=epi.pk,
        )
        return JsonResponse({
            "ok": True,
            "technical_sheet": {
                "id": entry.pk,
                "url": reverse("panel:documentation_document_view", args=[entry.pk]),
            },
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
    H31 (S74, ampliado S76). POST: edita los campos reales de
    PersonIdentity que tiene sentido de negocio corregir a mano desde
    el panel -- datos personales/contacto/dirección + fecha de alta/
    baja en la empresa (S76, Miguel Ángel: "echo en falta la
    dirección [...] fecha de alta, fecha de baja"). El resto de
    campos del modelo (dni, is_active_employee, employer_company,
    fechas de caducidad, ss_affiliation_number) son datos de
    `import_worker_machine_excel` -- editarlos a mano aquí quedaría
    sobrescrito por la siguiente importación real del Excel, así que
    se muestran de solo lectura en la ficha, nunca en este formulario.
    Mismo control de acceso que subir/eliminar documentos
    (DocsUploadAccessMixin) -- editar la ficha es una acción de
    escritura, no de simple consulta.
    """

    TEXT_EDITABLE_FIELDS = (
        "given_name", "first_surname", "second_surname", "phone", "email",
        "address_street", "postal_code", "city", "province",
    )
    DATE_EDITABLE_FIELDS = ("hire_date", "termination_date")
    EDITABLE_FIELDS = TEXT_EDITABLE_FIELDS + DATE_EDITABLE_FIELDS

    def post(self, request, pk):
        from datetime import date

        person = get_object_or_404(PersonIdentity, pk=pk)
        updated_fields = []
        for field in self.TEXT_EDITABLE_FIELDS:
            if field in request.POST:
                setattr(person, field, request.POST.get(field, "").strip())
                updated_fields.append(field)
        for field in self.DATE_EDITABLE_FIELDS:
            if field in request.POST:
                raw_value = request.POST.get(field, "").strip()
                if raw_value:
                    try:
                        year, month, day = (int(x) for x in raw_value.split("-"))
                        setattr(person, field, date(year, month, day))
                    except ValueError:
                        return JsonResponse(
                            {
                                "ok": False,
                                "error": "Fecha con formato inválido en %s." % field,
                            },
                            status=400,
                        )
                else:
                    setattr(person, field, None)
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
