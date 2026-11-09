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
from django.db import IntegrityError
from django.db.models import Count, F, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce, Replace
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views import View
from email.message import EmailMessage as StdEmailMessage
from email.utils import make_msgid
from html import escape as html_escape
from datetime import date, datetime
import base64
import hashlib
import logging
import re
import unicodedata

from analytics.views import _resolve_work_period
from document_explorer import (
    naming_service,
    personal_intake_service,
    postal_code_service,
)
from document_explorer import local_download_service
from document_explorer.index_writer import ensure_folder_chain
from document_explorer.models import (
    DocumentAcknowledgment, DocumentIndexEntry,
    DocumentTypeCatalog, DrivingLicenceCategory, EpiDelivery,
    EpiDeliveryBatchTemplate, EpiItemCatalog, JobPosition,
    PersonalDossierTemplate, PersonGroupTemplate, PersonIdentity,
    PersonIdPhoto, path_digest,
)
from document_explorer.epi_delivery_document_service import (
    build_epi_delivery_pdf_bytes, resolve_company_fiscal_profile,
)
from document_explorer.required_documentation_service import (
    attach_driving_grants, attach_subtype_documents,
    get_required_type_ids, resolve_required_document_status,
)
from document_explorer.vigencia_selector import current_fn_for
from document_explorer.subject_upload_service import (
    SubjectUploadError, upload_subject_document,
)
from document_management.models import DocumentSubstitutionLog
from document_management.pdf_merge_service import (
    EmptyDocumentListError, build_index_page, convert_to_pdf_bytes, merge_pdfs,
)
from document_management.vigencia_service import (
    DocumentSnapshot, evaluate_substitution,
)
from fleet.models import MachineAsset
from hr_calendar.models import AbsencePeriod, VacationPeriod
from ivr_config.models import Company, CompanyUser, Section, WorkPeriod
from panel.mixins import (
    CompanyUserRequiredMixin, DocsUploadAccessMixin, FleetAccessMixin,
)
from panel.models import PanelNavigationState
from panel.navigation_persistence import get_saved_state_key
from panel.views_task_photos import _build_photo_entries
from spare_parts.gcs_service import (
    download_bytes,
    generate_signed_url,
    upload_bytes,
)
from whatsapp.services import send_epi_delivery_whatsapp_confirmation
from work_order_processor.models import (
    WorkOrder,
    WorkOrderEntry,
    WorkOrderEntryLine,
)

logger = logging.getLogger(__name__)

# S145: "Sacado del dossier <nombre> (#<id>)" -- nota que deja
# dossier_service.extract_document en lo sacado de un dossier.
_SOURCE_DOSSIER_RE = re.compile(r"Sacado del dossier .*?\(#(\d+)\)")

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
    (
        "adolfo_alvarez",
        "Grúas Adolfo Álvarez S.L.",
        ["GRUAS ADOLFO ALVAREZ SL"],
    ),
    (
        "transgrual",
        "TRANSGRUAL S.L.",
        [
            "TRANSGRUAL SL",
            "TRANSGRUAL S.L.",
            "TRANSGRUAL Y ASITENCIA",
        ],
    ),
    ("aldi", "GRUALDI S.L.", ["GRUALDI S.L"]),
    (
        "asistencia_granada",
        "Asistencia y Grúas Granada",
        ["ASIST.GRUAS GRANADA"],
    ),
    ("sin_empresa", "Sin empresa asignada", [""]),
]


# S146 (Miguel Ángel): "hay que preguntar a qué empresa va y sacar el
# desplegable de empresas posibles" -- nada de escribirla a mano
# (Transgrual, TRANSGRUAL, Grualdi, GRUALDI S.L....). En el alta se
# guarda siempre el texto canónico de cada empresa (el primero de su
# lista en COMPANY_FILTER_CHOICES), que es el que reconoce también el
# código de su carpeta local (TR, GR, GL, AGG).
ALTA_COMPANY_CHOICES = [
    (raws[0], label) for slug, label, raws in COMPANY_FILTER_CHOICES
    if slug != "sin_empresa"
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
            active_q |= Q(is_active_employee=False) | Q(
                is_active_employee__isnull=True
            )
        qs = qs.filter(active_q)
    else:
        qs = qs.none()

    company_filter = request.GET.getlist("company")
    if company_filter:
        raw_by_slug = {
            slug: raws for slug, _label, raws in COMPANY_FILTER_CHOICES
        }
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

    # H30 (S123): filtro por requisito de documentación -- Miguel Ángel:
    # "podemos filtrar también por requisitos". "" = todos, "none" =
    # sin requisito, un pk = ese requisito. (Incidente S123: la primera
    # versión se insertó entre el `if company_filter` y su `else`, que
    # quedó colgado de este filtro y vaciaba la lista con "Todos".)
    requirement_filter = request.GET.get("requirement", "")
    if requirement_filter == "none":
        qs = qs.filter(job_position__isnull=True)
    elif requirement_filter.isdigit():
        qs = qs.filter(job_position_id=int(requirement_filter))

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


def _split_current_obsolete(entries, required_type_ids=frozenset()):
    """
    Agrupa entries (ya filtradas a un sujeto) en (vigentes, obsoletas)
    por document_type -- reutiliza vigencia_service.is_current() tal
    cual (agnóstico de modelo, ya validado en H26). `is_obsolete=True`
    manda directo a obsoletas sin pasar por el cálculo de fechas (ya
    quedó decidido en el momento de la sustitución, no se recalcula
    cada vez que se lista).

    H30 (S50): cada entry vigente lleva ademas `needs_attention`
    (atributo Python, nunca de BD) -- True cuando su tipo necesita
    fecha (`tracks_expiry`) y esa fecha ya pasó de verdad.

    CORREGIDO EN H31 (S100), confirmado explícitamente por Miguel
    Ángel: antes también se marcaba cuando la fecha estaba en blanco
    (mismo criterio que `_attach_alert_flags`, mismo incidente real:
    muchos tipos de PERSONAL con `tracks_expiry=True` -- ALTA,
    MOD_145, IDC, CONTRATO... -- no tienen ninguna fecha de caducidad
    que imprimir, su vigencia se decide por `issue_date`, nunca por
    caducidad. Con la regla vieja salían siempre en rojo, estuvieran
    bien o mal. Ahora solo una caducidad real ya pasada dispara el
    aviso -- un tipo sin fecha nunca alerta por sí solo.

    `required_type_ids` (S119, corregido tras el incidente real de
    Alberto Javier Álvarez Díaz): pk de `DocumentTypeCatalog` exigidos
    ahora mismo por el requisito de documentación del sujeto (ver
    `required_documentation_service.get_required_type_ids`) -- decide,
    vía `current_fn_for`, si un tipo caducado y sin sustituto sigue
    contando como "vigente caducado" (se ve en la tabla, en rojo, con
    su fecha) o desaparece sin más (criterio general `is_current()`).
    Sin este conjunto (valor por defecto), TODO tipo caducado y sin
    sustituto desaparece -- correcto para un llamador que no conoce
    ningún requisito real (p. ej. el historial de un tipo suelto sin
    mirar a quién pertenece), nunca para pintar la ficha completa de un
    sujeto con requisito asignado.
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
        # S117 -- vigencia_service deja al llamador filtrar los tipos
        # acumulables (DocumentTypeCatalog.is_cumulative, S107: varias
        # instancias vigentes A LA VEZ -- cursos, entregas,
        # nombramientos...), y aquí nunca se hacía: una persona con
        # varias entregas de información solo veía la última como
        # vigente. En un tipo acumulable todo lo no obsoleto es vigente.
        if group[0].document_type_id and group[0].document_type.is_cumulative:
            for entry in group:
                entry.needs_attention = bool(
                    entry.document_type.tracks_expiry
                    and entry.document_type.expires
                    and entry.expiry_date
                    and entry.expiry_date < today
                )
                current.append(entry)
            continue
        snapshots = {
            e.pk: DocumentSnapshot(
                identifier=e.pk, expiry_date=e.expiry_date,
                issue_date=e.issue_date, indexed_at=e.indexed_at,
            )
            for e in group
        }
        # S119 (corregido tras el incidente de Alberto Javier Álvarez
        # Díaz): el criterio ya no es por dominio, es por si ESTE tipo
        # está en el requisito de ESTE sujeto -- ver vigencia_selector.
        current_fn = current_fn_for(
            group[0].document_type, required_type_ids,
        )
        for entry in group:
            candidate = snapshots[entry.pk]
            siblings = [s for pk, s in snapshots.items() if pk != entry.pk]
            if current_fn(candidate, siblings):
                entry.needs_attention = bool(
                    entry.document_type_id
                    and entry.document_type.tracks_expiry
                    and entry.document_type.expires
                    and entry.expiry_date
                    and entry.expiry_date < today
                )
                current.append(entry)
            else:
                obsolete.append(entry)
    return current, obsolete


def _attach_required_document_alerts(
    objects, content_type, requirement_field="job_position",
):
    """
    H31 (S119). Alert flags for a listing (Personal or MachineAsset)
    -- based ONLY on the subject's `JobPosition.required_document_
    types` (via `requirement_field`, "job_position" or "document_
    requirement" -- both FK to the SAME catálogo único), never on any
    document type it happens to have. Replaces the old pair
    (`_attach_alert_flags` + `_attach_missing_required_alert`) for
    Personal, y el uso genérico de `_attach_alert_flags` para Centros
    de Gasto/`MachineAsset` -- ambos alertaban de CUALQUIER tipo
    caducado que el sujeto tuviera, exigido o no (Miguel Ángel,
    verbatim, incidente real: "avisamos a una persona que es
    administrativa [...] de que tiene cumplido el carnet de conducir o
    el CAP" -- documentos que su puesto actual no exige en absoluto).

    AMPLIADO S119: "los requisitos documentales no son ni para
    personas ni para máquinas [...] la gestión es global" -- un único
    catálogo (`JobPosition`), asignado por `job_position` en
    `PersonIdentity` o por `document_requirement` en `MachineAsset`.
    Esta función sirve a los dos con el mismo cálculo, parametrizando
    solo el nombre del campo FK -- nunca dos implementaciones de la
    misma regla.

    Same rule as `required_documentation_service.
    resolve_required_document_status` (nunca duplicar la decisión sin
    motivo, pero aquí en forma de lote -- una consulta para todos los
    requisitos de la página en vez de uno por sujeto), incluida la
    correccion del mismo incidente: un tipo obligatorio cuyo único
    documento ya caducó cuenta como "caducado", nunca como "falta" --
    `is_current()` lo habría excluido de la competición por estar
    caducado y sin sustituto, ocultándolo como si no existiera.
    """
    from datetime import date

    from document_explorer.models import DrivingLicenceGrant
    from document_explorer.required_documentation_service import (
        DRIVING_CARD_CODE,
        IDENTITY_CODES,
        evaluate_driving_categories,
        latest_driving_card,
    )

    requirement_fk_id = requirement_field + "_id"
    objects_by_requirement = {}
    for obj in objects:
        requirement_id = getattr(obj, requirement_fk_id, None)
        if requirement_id:
            objects_by_requirement.setdefault(
                requirement_id, [],
            ).append(obj)
        obj.has_alert = False
        obj.alert_labels = []
    if not objects_by_requirement:
        return objects

    # S128: un requisito desactivado no genera avisos -- sus sujetos
    # quedan sin tipos exigidos (los `.get(..., [])` de abajo).
    requirements = list(JobPosition.objects.filter(
        pk__in=objects_by_requirement.keys(), is_active=True,
    ).prefetch_related(
        "required_document_types", "required_driving_categories",
    ))
    required_by_requirement = {
        jp.pk: list(jp.required_document_types.all())
        for jp in requirements
    }
    # H30 (S120). Clases de permiso exigidas por requisito -- mismo
    # cálculo que la ficha (`evaluate_driving_categories`), en lote.
    categories_by_requirement = {
        jp.pk: list(jp.required_driving_categories.all())
        for jp in requirements
    }
    all_object_ids = [
        obj.pk
        for group in objects_by_requirement.values() for obj in group
    ]
    all_type_ids = {
        dt.pk
        for types in required_by_requirement.values() for dt in types
    }
    rows = DocumentIndexEntry.objects.filter(
        bucket=BUCKET, domain_content_type=content_type,
        domain_object_id__in=all_object_ids,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
        document_type_id__in=all_type_ids,
    ).values_list(
        "domain_object_id", "document_type_id", "document_type__code",
        "document_type__label", "document_type__tracks_expiry",
        "issue_date", "expiry_date",
    )
    docs_by_object = {}
    for (
        object_id, type_id, code, label, tracks_expiry,
        issue_date, expiry_date,
    ) in rows:
        docs_by_object.setdefault(object_id, {}).setdefault(
            type_id, [],
        ).append((code, label, tracks_expiry, issue_date, expiry_date))

    today = date.today()
    # H30 (S120). Carnés y clases solo de los sujetos cuyo requisito
    # exige alguna clase -- dos consultas para toda la página.
    category_object_ids = [
        obj.pk
        for requirement_id, group in objects_by_requirement.items()
        if categories_by_requirement.get(requirement_id)
        for obj in group
    ]
    cards_by_object = {}
    grants_by_card = {}
    if category_object_ids:
        for card in DocumentIndexEntry.objects.filter(
            bucket=BUCKET, domain_content_type=content_type,
            domain_object_id__in=category_object_ids,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            document_type__code=DRIVING_CARD_CODE,
        ).only("pk", "domain_object_id", "issue_date", "expiry_date"):
            cards_by_object.setdefault(
                card.domain_object_id, [],
            ).append(card)
        all_card_ids = [
            card.pk for cards in cards_by_object.values() for card in cards
        ]
        for grant in DrivingLicenceGrant.objects.filter(
            entry_id__in=all_card_ids,
        ).select_related("category"):
            grants_by_card.setdefault(grant.entry_id, []).append(grant)

    for requirement_id, group in objects_by_requirement.items():
        required_types = required_by_requirement.get(requirement_id, [])
        required_categories = categories_by_requirement.get(
            requirement_id, [],
        )
        for obj in group:
            docs_by_type = docs_by_object.get(obj.pk, {})
            present_codes = {
                doc[0] for docs in docs_by_type.values() for doc in docs
            }
            has_identity_doc = bool(set(IDENTITY_CODES) & present_codes)
            labels = []
            for document_type in required_types:
                docs = docs_by_type.get(document_type.pk, [])
                if not docs:
                    if (
                        document_type.code in IDENTITY_CODES
                        and has_identity_doc
                    ):
                        continue
                    labels.append("Falta: %s" % document_type.label)
                    continue
                _code, label, tracks_expiry, issue_date, expiry_date = max(
                    docs, key=lambda doc: doc[4] or doc[3] or date.min,
                )
                # S120 (decisión 1): con clases exigidas, el carné solo
                # cuenta para "falta" -- la caducidad es de las clases.
                if (
                    document_type.code == DRIVING_CARD_CODE
                    and required_categories
                ):
                    continue
                if (
                    tracks_expiry and document_type.expires
                    and expiry_date and expiry_date < today
                ):
                    labels.append(
                        "Caducado: %s — caducó el %s" % (
                            label, expiry_date.strftime("%d/%m/%Y"),
                        ),
                    )
            if required_categories:
                card = latest_driving_card(
                    cards_by_object.get(obj.pk, []),
                    frozenset(grants_by_card),
                )
                grants = grants_by_card.get(card.pk, []) if card else []
                category_missing, category_expired = (
                    evaluate_driving_categories(
                        required_categories, card, grants, today,
                    )
                )
                labels.extend(
                    "Falta: %s" % item.label for item in category_missing
                )
                labels.extend(
                    "Caducado: %s" % text for text in category_expired
                )
            obj.has_alert = bool(labels)
            obj.alert_labels = sorted(labels)
    return objects


class DocumentationHubV2View(CompanyUserRequiredMixin, View):
    """GET: página completa, tres pestañas, listado inicial de Centros de
    Gasto.

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
            company_user=request.user.company_user,
            screen_key="documentation_hub",
        ).first()
        state = (
            nav_state.state
            if nav_state and isinstance(nav_state.state, dict)
            else {}
        )
        valid_tabs = (
            "maquinaria", "personal", "epis", "accesorios", "vacaciones",
            "fichajes", "horarios", "calendario", "requisitos", "avisos",
            "circulares",
            "plantillas", "bandeja", "revisiones", "repostajes",
            "solicitudes",
        )
        # H30 (S126): "Bandeja de entrada" solo para quien puede subir
        # documentación (mismos roles que DocsUploadAccessMixin).
        can_use_inbox = request.user.company_user.role in (
            CompanyUser.ROLE_ADMIN, CompanyUser.ROLE_ADMIN_SUPERVISOR,
            CompanyUser.ROLE_DOCS_SUPERVISOR,
        )
        if not can_use_inbox:
            valid_tabs = tuple(t for t in valid_tabs if t != "bandeja")
        # H24 (S129): "Fichajes" lleva posiciones GPS -- solo los roles
        # de SupervisorAccessMixin.
        can_view_clock_events = request.user.company_user.role in (
            CompanyUser.ROLE_ADMIN, CompanyUser.ROLE_ADMIN_SUPERVISOR,
            CompanyUser.ROLE_SUPERVISOR, CompanyUser.ROLE_WORKSHOPBOSS,
        )
        if not can_view_clock_events:
            valid_tabs = tuple(
                t for t in valid_tabs
                if t not in ("fichajes", "horarios", "solicitudes")
            )
        # H30 (S119): "Circulares", "Plantillas" y "Requisitos" pasan
        # de botones "Gestionar..." en la barra de acción de Personal a
        # pestañas propias del hub -- Miguel Ángel: "las gestiones
        # deben ir en pestañas en la vista principal de documentación,
        # [...] eliminamos la palabra gestionar". Sin botón "Volver"
        # (se probó uno en Requisitos y Miguel Ángel cayó en la cuenta
        # él mismo de que sobraba): las propias pestañas del hub ya son
        # el camino de vuelta. "Requisitos" se enlaza además desde
        # Centros de Gasto (?tab=requisitos) -- un enlace directo pisa
        # lo persistido (es una navegación deliberada), y se persiste
        # igual que un clic de pestaña normal.
        requested_tab = request.GET.get("tab")
        if requested_tab in valid_tabs:
            active_tab = requested_tab
            if not nav_state:
                nav_state = PanelNavigationState(
                    company_user=request.user.company_user,
                    screen_key="documentation_hub", state={},
                )
            nav_state.state = {**state, "active_tab": active_tab}
            nav_state.save()
        else:
            active_tab = state.get("active_tab") or "maquinaria"
            if active_tab not in valid_tabs:
                active_tab = "maquinaria"
        filters = (
            state.get("filters")
            if isinstance(state.get("filters"), dict)
            else {}
        )

        # S117: la pestaña "Centros de Gasto" ya no se pinta aquí -- la
        # carga por htmx el panel compartido de maquinaria (puerta
        # "docs", fleet.views.MachineAssetDocsPaneView), que guarda su
        # propia navegación. Decisión de Miguel Ángel: sustituye al
        # listado primitivo de S48-S50.
        return render(request, "panel/documentation_h30/hub.html", {
            "active_tab": "maquinaria",
            "active_nav": "documentation_hub",
            "persisted_active_tab": active_tab,
            "persisted_filters": filters,
            "personal_tab_qs": _build_personal_tab_querystring(filters),
            "can_use_inbox": can_use_inbox,
            "can_view_clock_events": can_view_clock_events,
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

    personal_filters = (
        filters.get("personal") if isinstance(filters, dict) else None
    )
    personal_filters = (
        personal_filters if isinstance(personal_filters, dict) else {}
    )

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
        company_values = [
            slug for slug, _label, _raws in COMPANY_FILTER_CHOICES
        ]
    for value in company_values:
        params.append(("company", value))

    # H30 (S123): filtro por requisito ("" = todos).
    requirement_value = personal_filters.get("requirement", "")
    if isinstance(requirement_value, str) and requirement_value:
        params.append(("requirement", requirement_value))
    # H24 (S144): "Alta en el fichaje", "Sección" y "Horario".
    for key in ("onboarding", "section", "schedule"):
        value = personal_filters.get(key, "")
        if isinstance(value, str) and value:
            params.append((key, value))

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


# H30 (S119), punto 7: documentos que forman parte del "libro de taller"
# de una máquina, junto a sus partes y mantenimientos.
MACHINE_WORKSHOP_DOCUMENT_TYPES = (
    "LIBRO_HISTORIAL", "ORDEN_TRABAJO_MANTENIMIENTO",
)
MACHINE_WORKSHOP_LIST_LIMIT = 100


def _machine_workshop_context(machine, entries):
    """
    Workshop section of a machine file: work-order lines, maintenance
    logs and workshop documents, read-only.
    ---
    H30 (S119), punto 7 -- sección Taller de la ficha de máquina, solo
    consulta (Miguel Ángel, S118: "el libro historial que ya tenemos
    debido a los partes digitales que hacen los mecánicos, podemos
    incluirlos en las fichas"):
    - Partes: `WorkOrderEntryLine` con esta máquina (fecha y mecánico del
      `WorkOrderEntry`, tipo, avería, horas `delta_hours`). El total de
      horas es un agregado sobre TODAS las líneas, aunque la tabla solo
      muestre las últimas `MACHINE_WORKSHOP_LIST_LIMIT`.
    - Mantenimientos: `fleet.MaintenanceLog` de la máquina.
    - Documentos LIBRO_HISTORIAL y ORDEN_TRABAJO_MANTENIMIENTO, vigentes
      y obsoletos, más recientes primero.
    """
    from django.db.models import Count, Sum

    from fleet.models import MaintenanceLog

    lines_qs = WorkOrderEntryLine.objects.filter(
        machine_asset=machine, entry__work_date__isnull=False,
    )
    lines_totals = lines_qs.aggregate(total=Sum("delta_hours"), n=Count("id"))
    work_lines = list(
        lines_qs.select_related("entry").order_by(
            "-entry__work_date", "-id",
        )[:MACHINE_WORKSHOP_LIST_LIMIT]
    )
    logs_qs = MaintenanceLog.objects.filter(machine_asset=machine)
    logs_totals = logs_qs.aggregate(
        total=Sum("charged_hours"), n=Count("id"),
    )
    maintenance_logs = list(
        logs_qs.order_by("-date", "-id")[:MACHINE_WORKSHOP_LIST_LIMIT]
    )
    workshop_documents = sorted(
        (
            entry for entry in entries
            if entry.document_type_id
            and entry.document_type.code in MACHINE_WORKSHOP_DOCUMENT_TYPES
        ),
        key=lambda entry: (
            entry.expiry_date or entry.issue_date or date.min, entry.pk,
        ),
        reverse=True,
    )
    return {
        "work_lines": work_lines,
        "work_lines_count": lines_totals["n"] or 0,
        "work_lines_total_hours": lines_totals["total"] or 0,
        "work_lines_truncated": (lines_totals["n"] or 0) > len(work_lines),
        "maintenance_logs": maintenance_logs,
        "maintenance_count": logs_totals["n"] or 0,
        "maintenance_total_hours": logs_totals["total"] or 0,
        "workshop_documents": workshop_documents,
        "has_workshop_data": bool(
            work_lines or maintenance_logs or workshop_documents
        ),
        "workshop_list_limit": MACHINE_WORKSHOP_LIST_LIMIT,
    }


class MachineDetailView(CompanyUserRequiredMixin, View):
    """
    Ficha de una máquina (centro de gasto): documentación vigente e
    histórico y, desde S117, sus DATOS editables en la propia ficha.

    S117 -- decisión de Miguel Ángel: emular Personal. Se entra a la
    ficha pulsando el código interno en el listado (como el nombre en
    Personal) y los datos del centro de gasto se editan AQUÍ, en el
    apartado "Datos del centro de gasto" (análogo a "Datos personales"),
    en vez de en un modal del listado -- el botón Editar y el de
    Documentación del listado desaparecen. Mismo formulario
    (fleet.forms.MachineAssetForm) y misma normalización del código que
    la edición anterior; guardar solo para ADMIN/DOCS_SUPERVISOR (mismos
    roles que FleetManageAccessMixin), lectura para el resto.
    """

    EDIT_ROLES = {"ADMIN", "ADMIN_SUPERVISOR", "DOCS_SUPERVISOR"}

    def _can_edit(self, request):
        return request.user.company_user.role in self.EDIT_ROLES

    def _render(self, request, machine, form, saved=False, status=200):
        ct = ContentType.objects.get_for_model(MachineAsset)
        entries = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, domain_content_type=ct, domain_object_id=machine.pk,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).select_related("document_type").order_by("-id")
        # H30 (S118), punto 1: los documentos SIN TIPO no pasan por el
        # cálculo de vigencia -- agrupados todos bajo document_type=None,
        # is_current() dejaría uno solo "vigente" y mandaría el resto a
        # obsoletos, y sin la tabla plana "Obsoletos" desaparecerían de
        # la ficha. Se listan todos aparte, con su nombre de archivo,
        # para poder tiparlos con "Tipo".
        untyped_documents = [
            entry for entry in entries if not entry.document_type_id
        ]
        # S119: qué tipos exige el requisito de ESTA máquina en
        # concreto -- decide si un tipo caducado y sin sustituto sigue
        # contando como vigente (ver docstring de _split_current_obsolete).
        required_type_ids = get_required_type_ids(machine)
        current, _obsolete = _split_current_obsolete(
            [entry for entry in entries if entry.document_type_id],
            required_type_ids,
        )
        machine_domains = [
            DocumentTypeCatalog.DOMAIN_MACHINE,
            DocumentTypeCatalog.DOMAIN_BOTH,
        ]
        # H30 (S118), punto 1 -- mismo formato que la ficha de Personal
        # (PersonalDetailView): acordeón por familia del catálogo,
        # "+ Subir" por familia limitado a los tipos que esta máquina
        # todavía no tiene (vigentes o históricos: si ya existe uno, se
        # sustituye con "Actualizar" en su fila), aviso por familia de
        # los vigentes con caducidad real ya pasada.
        # S123: los tipos acumulables (varios vigentes a la vez) se
        # ofrecen siempre -- "Actualizar" no es la vía para añadir otro.
        # S130, Miguel Ángel: "he intentado subir el recibo del seguro
        # de la furgoneta X12 y no podía elegir recibo del seguro" -- la
        # X12 ya tenía uno y "+ Subir" escondía los tipos ya presentes.
        # Ahora ofrece SIEMPRE todos los tipos de la familia: la subida
        # ya aplica la sustitución (subject_upload_service: el más
        # reciente queda vigente, el anterior pasa a histórico), igual
        # que "Actualizar" en su fila.
        missing_types_by_family = {}
        for dt in DocumentTypeCatalog.objects.filter(
            domain__in=machine_domains, is_active=True,
        ).order_by("label"):
            missing_types_by_family.setdefault(dt.family, []).append(dt)
        # H30 (S119): "Falta" y "Caducado" del triángulo por familia
        # salen SOLO del requisito de documentación de la máquina
        # (MachineAsset.document_requirement, mismo catálogo único
        # JobPosition que Personal) -- ver resolve_required_document_
        # status.
        missing_required_types_by_family, attention_types_by_family = (
            resolve_required_document_status(machine)
        )
        # H30 (S119), punto 4: aviso en rojo en la cabecera de
        # Documentación con cada vigente de caducidad ya pasada. YA NO
        # es una señal general aparte del requisito -- `current` sale
        # de `_split_current_obsolete(entries, required_type_ids)`
        # (más arriba, en MachineDetailView), así que un tipo caducado
        # y sin sustituto solo sigue siendo "vigente" (needs_attention
        # incluido) si además es obligatorio para ESTA máquina. Sin
        # ningún requisito asignado -- el caso de las 318 máquinas de
        # hoy -- este banner sale vacío, coherente con el listado y con
        # el triángulo por familia de arriba: mismo criterio en los
        # tres sitios, nunca dos reglas distintas conviviendo.
        expired_current_documents = sorted(
            (entry for entry in current if entry.needs_attention),
            key=lambda entry: (entry.expiry_date, entry.document_type.label),
        )
        families = _group_current_by_family(
            current, include_empty_families=missing_types_by_family.keys(),
        )
        doc_types = DocumentTypeCatalog.objects.filter(
            is_active=True, domain__in=machine_domains,
        ).order_by("label")
        all_document_types = DocumentTypeCatalog.objects.filter(
            is_active=True, domain__in=machine_domains,
        ).order_by("family", "label")
        # S117 -- "Volver" regresa a la pantalla desde la que se entró
        # (p. ej. Centros de gasto del taller), nunca a una URL fija:
        # back_url validado con el helper compartido safe_back_url
        # (mismo host, sin open-redirect); sin back_url, el hub de
        # Documentación, que era el único origen hasta ahora.
        from panel.url_utils import safe_back_url

        back_url = safe_back_url(
            request, request.GET.get("back_url"),
            reverse("panel:documentation_hub"),
        )
        # S123: primer tramo del breadcrumb, según la puerta de origen.
        back_label = (
            "Taller mecánico — Centros de gasto"
            if back_url.split("?")[0] == reverse("panel:fleet_list")
            else "Documentación"
        )
        # H30 (S118): foto de la máquina -- solo la elegida
        # explícitamente, y solo si el documento sigue vivo.
        avatar = machine.avatar_document
        if avatar and (avatar.deleted_at or avatar.purged_at):
            avatar = None
        entries_list = list(entries)
        # H30 (S121): accesorios de elevación entregados ahora a esta
        # máquina -- solo consulta, el CRUD vive en su pestaña del hub.
        from document_explorer.lifting_accessory_service import (
            accessories_for_machine,
        )
        from panel.views_lifting_accessories import _annotate

        lifting_accessories = _annotate(accessories_for_machine(machine))
        # H30 (S131): revisiones por horas y km (plan, revisiones hechas
        # y lecturas), apartado propio de la ficha.
        from panel.views_machine_service import machine_service_context

        return render(
            request,
            "panel/documentation_h30/_machine_detail.html",
            {
                **_machine_workshop_context(machine, entries_list),
                **machine_service_context(machine, request.user.company_user),
                # H30 (S139, invasora): botones "Gestión" y "Averías" de
                # la sección Taller, solo para quien puede abrirlas
                # (mismos roles que Centros de gasto, FleetAccessMixin).
                "can_manage_workshop": (
                    request.user.company_user.role
                    in FleetAccessMixin.allowed_roles
                ),
                "service_open": request.GET.get("service_open") == "1",
                "lifting_accessories": lifting_accessories,
                "lifting_accessories_expired": any(
                    accessory.is_expired for accessory in lifting_accessories
                ),
                "machine": machine,
                "families": families,
                "avatar": avatar,
                "untyped_documents": untyped_documents,
                "missing_types_by_family": missing_types_by_family,
                "missing_required_types_by_family": (
                    missing_required_types_by_family
                ),
                "attention_types_by_family": attention_types_by_family,
                "expired_current_documents": expired_current_documents,
                "has_expired_documents": bool(expired_current_documents),
                # S119, punto 6: casillas marcadas (PanelNavigationState).
                "selected_document_ids": _machine_selected_ids(
                    request,
                    machine.pk,
                ),
                "all_document_types": all_document_types,
                "doc_types": doc_types,
                "active_nav": "documentation_hub",
                "back_url": back_url,
                "back_label": back_label,
                "form": form,
                "can_edit_machine": self._can_edit(request),
                "machine_saved": saved,
                "machine_form_open": saved or form.errors,
                # S119, punto 5: con errores de validación se reabre ya en
                # modo edición, para poder corregir sin volver a confirmar.
                "start_in_edit_mode": bool(form.errors),
            },
            status=status,
        )

    def get(self, request, pk):
        from fleet.forms import MachineAssetForm

        machine = get_object_or_404(MachineAsset, pk=pk)
        form = MachineAssetForm(instance=machine, company=machine.company)
        return self._render(
            request, machine, form, saved=request.GET.get("saved") == "1",
        )

    def post(self, request, pk):
        from urllib.parse import urlencode

        from fleet.forms import MachineAssetForm

        machine = get_object_or_404(MachineAsset, pk=pk)
        if not self._can_edit(request):
            return HttpResponse(
                "No tienes permiso para editar este centro de gasto.",
                status=403,
            )
        from document_explorer import machine_local_folder_service

        # H31 (S148): carpeta local de antes del cambio, tomada antes de
        # validar el formulario (is_valid ya vuelca los datos nuevos en
        # la máquina y el código decide cuál es su carpeta); si cambia de
        # familia, el agente la mueve.
        previous_local = machine_local_folder_service.current_local_folder(
            machine)
        form = MachineAssetForm(
            request.POST, instance=machine, company=machine.company,
        )
        if form.is_valid():
            updated = form.save(commit=False)
            updated.code = updated.code.strip().upper()
            updated.save()
            # H30 (S119), punto 5: si cambian familia o código, la
            # carpeta y los nombres canónicos de sus documentos le
            # siguen (punto 3).
            from document_explorer.machine_folder_service import (
                sync_machine_documents,
            )

            sync_machine_documents(updated)
            machine_local_folder_service.follow_change(
                updated, previous_local,
                requested_by=request.user.company_user)
            params = {"saved": "1"}
            if request.GET.get("back_url"):
                params["back_url"] = request.GET["back_url"]
            return redirect(
                "%s?%s"
                % (
                    reverse(
                        "panel:documentation_machine_detail", args=[machine.pk]
                    ),
                    urlencode(params),
                )
            )
        return self._render(request, machine, form, status=400)


def _attach_person_avatars(persons, person_ct):
    """
    Attach `avatar_entry_id` to each person of the visible list.
    ---
    H31 (S118) -- miniatura de la foto en el listado de Personal, como
    en Centros de gasto. Mismo criterio exacto que la ficha
    (PersonalDetailView): la foto elegida (`avatar_document`) y, si no
    hay, la IMAGEN más reciente de la persona. Una sola query para
    todas las personas sin foto elegida, nunca una por fila.
    """
    without_choice = [
        person.pk for person in persons if not person.avatar_document_id
    ]
    fallback = {}
    if without_choice:
        for person_pk, entry_pk in DocumentIndexEntry.objects.filter(
            bucket=BUCKET, domain_content_type=person_ct,
            domain_object_id__in=without_choice,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__code="IMAGEN",
            deleted_at__isnull=True, purged_at__isnull=True,
        ).order_by("-id").values_list("domain_object_id", "pk"):
            fallback.setdefault(person_pk, entry_pk)
    # H31 (S134): la foto de carné recortada manda sobre las demás.
    # S136: con su fecha, que va en la dirección de la miniatura
    # (`?v=`, igual que en la ficha). La foto se sirve con caché de un
    # día: sin la versión, el listado seguía mostrando la anterior (la
    # de Paraschiv, de lado, ya girada en la ficha).
    photo_versions = dict(PersonIdPhoto.objects.filter(
        person_id__in=[person.pk for person in persons],
    ).values_list("person_id", "extracted_at"))
    for person in persons:
        person.avatar_entry_id = (
            person.avatar_document_id or fallback.get(person.pk)
        )
        extracted_at = photo_versions.get(person.pk)
        person.has_id_photo = extracted_at is not None
        person.id_photo_version = (
            int(extracted_at.timestamp()) if extracted_at else 0
        )
    return persons


def _person_list_page(request, ids_only=False):
    """
    The Personal list (filters, search, sort). With ids_only, only the
    ordered pks.
    ---
    El listado de Personal con sus filtros, búsqueda y orden. Con
    `ids_only`, solo los pks en el orden de la lista, sin alertas ni
    avatares (S144: anterior/siguiente en la ficha).
    """
    qs = PersonIdentity.objects.select_related(
        "job_position", "company_user__workday_schedule",
    )
    # H31 (S113). Miguel Ángel: "si tuviésemos una casilla que dijese
    # mostrar [...] que mostrase en el listado de trabajadores
    # justamente los trabajadores que están en el grupo de reparto".
    # Con `only_selected=1` y una lista de pks (la propia selección
    # JS, cargada de un grupo o marcada a mano -- da igual el origen),
    # el listado se filtra EXACTAMENTE a esos pks, saltándose del
    # todo los casilleros de Estado/Empresa -- nunca los combina con
    # ellos, para no ocultar a nadie del grupo por no cumplir un
    # filtro de empresa/estado que no pintaba nada aquí.
    only_selected = request.GET.get("only_selected") == "1"
    selected_ids = [
        pk for pk in request.GET.get("selected_ids", "").split(",") if pk
    ]
    if only_selected and selected_ids:
        qs = qs.filter(pk__in=selected_ids)
    else:
        qs = _apply_personal_filters(qs, request)
    # H24 (S144): filtro "Alta en el fichaje" (estado calculado en
    # panel/personal_access.py, no es una columna de BD).
    from panel.personal_access import (
        ONBOARDING_CHOICES,
        filter_by_onboarding,
        onboarding_filter,
        onboarding_states,
    )

    onboarding_raw = request.GET.get("onboarding", "")
    onboarding_codes = onboarding_filter(onboarding_raw)
    if onboarding_codes is not None and not only_selected:
        qs = qs.filter(pk__in=[
            p.pk for p in filter_by_onboarding(
                qs.select_related("company_user"), onboarding_codes)
        ])
    # H24 (S144): filtros "Sección" (la vigente hoy) y "Horario" (el que
    # le toca), los mismos que la pestaña Horarios (Miguel Ángel:
    # "copiamos el pipeline de horarios [...] en la pestaña de
    # personal"). Se calculan en Python, como en Horarios.
    from budgets.models import Base
    from panel.views_worker_schedules import (
        NO_SCHEDULE,
        NO_SECTION,
        _rows as schedule_rows,
        _schedules,
        _sections,
    )

    company = request.user.company_user.company
    section_raw = request.GET.get("section", "")
    schedule_raw = request.GET.get("schedule", "")
    if (section_raw or schedule_raw) and not only_selected:
        wanted = []
        for row in schedule_rows(company, list(qs.select_related(
                "company_user__workday_schedule"))):
            if section_raw == NO_SECTION and row.state.section is not None:
                continue
            if section_raw.isdigit() and (
                    row.state.section is None
                    or row.state.section.pk != int(section_raw)):
                continue
            if schedule_raw == NO_SCHEDULE and row.schedule is not None:
                continue
            if schedule_raw.isdigit() and (
                    row.schedule is None
                    or row.schedule.pk != int(schedule_raw)):
                continue
            wanted.append(row.person.pk)
        qs = qs.filter(pk__in=wanted)
    search = request.GET.get("q", "").strip()
    if search:
        # S110: buscar "ALVAREZ VIEIRA" no encontraba a nadie -- el
        # texto completo se comparaba contra CADA campo por separado
        # (first_surname__icontains=search), pero apellidos y nombre
        # viven en campos distintos (first_surname="ALVAREZ",
        # second_surname="VIEIRA"), asi que ninguno contenia la cadena
        # completa. Se parte la busqueda en palabras y se exige que
        # CADA palabra aparezca en ALGUNO de los campos (AND entre
        # palabras, OR entre campos por palabra), para que coincidan
        # aunque las palabras esten repartidas entre first_surname/
        # second_surname/given_name.
        # S113: Miguel Ángel pidió que la búsqueda alcance también al
        # requisito de documentación asignado (p. ej. escribir
        # "general" encuentra a todos los que tienen ese requisito) --
        # mismo criterio AND-entre-palabras/OR-entre-campos de arriba,
        # un campo más a la lista. select_related("job_position") ya
        # aplicado arriba cubre el JOIN sin coste extra; al ser FK
        # (no M2M), no hay riesgo de duplicar filas.
        # S137: Miguel Ángel, "¿puedo buscar un operario por el número de
        # teléfono?". Los dos teléfonos entran en la búsqueda comparando
        # solo cifras: se quitan espacios, puntos, guiones y paréntesis
        # del teléfono guardado y de la palabra buscada, así que
        # "600 12 34 56", "600123456" o "+34 600..." coinciden igual.
        qs = qs.annotate(
            phone_digits=_phone_digits("phone"),
            phone2_digits=_phone_digits("phone_secondary"),
        )
        for word in search.split():
            match = (
                Q(first_surname__icontains=word)
                | Q(second_surname__icontains=word)
                | Q(given_name__icontains=word) | Q(dni__icontains=word)
                | Q(job_position__name__icontains=word)
                | Q(nickname__icontains=word)
            )
            digits = "".join(ch for ch in word if ch.isdigit())
            if digits:
                match |= (
                    Q(phone_digits__contains=digits)
                    | Q(phone2_digits__contains=digits)
                )
            qs = qs.filter(match)
    # H31 (S100): Miguel Ángel pidió ordenar también por Nombre, Alta y
    # Documentos (todas menos DNI). `domain_object` es una
    # GenericForeignKey sin `GenericRelation` inversa -- no admite
    # `.annotate(Count(...))` directo, así que el conteo se anota vía
    # Subquery correlacionada por `domain_object_id`, sobre el queryset
    # COMPLETO (antes de paginar), para que el `order_by` de
    # `_apply_sort` pueda usarlo (mismo patrón que usa desde S117 el
    # panel compartido de maquinaria, fleet.views).
    person_ct = ContentType.objects.get_for_model(PersonIdentity)
    doc_count_subquery = (
        DocumentIndexEntry.objects.filter(
            bucket=BUCKET,
            domain_content_type=person_ct,
            domain_object_id=OuterRef("pk"),
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
        )
        .order_by()
        .values("domain_object_id")
        .annotate(n=Count("id"))
        .values("n")
    )
    qs = qs.annotate(doc_count=Coalesce(Subquery(doc_count_subquery), 0))
    sort_columns = [
        ("first_surname", "Primer apellido"), ("given_name", "Nombre"),
        ("hire_date", "Alta"), ("doc_count", "Documentos"),
        # H30 (S123), punto 6: ordenar por requisito de documentación.
        ("job_position__name", "Requisito"),
    ]
    # H24 (S144): "Alta en el fichaje" se ordena en Python (no es un
    # campo de BD); la base, por apellidos y nombre.
    sort_columns.append(("onboarding", "Alta en el fichaje"))
    # H24 (S144): sección y horario, también en Python.
    python_sorts = ("onboarding", "section", "schedule")
    sort_columns += [("section", "Sección"), ("schedule", "Horario")]
    if request.GET.get("sort") in python_sorts:
        qs = qs.order_by("first_surname", "second_surname", "given_name")
        sort_key = request.GET.get("sort")
        sort_dir = "desc" if request.GET.get("dir") == "desc" else "asc"
    else:
        qs, sort_key, sort_dir = _apply_sort(
            request, qs,
            [c for c in sort_columns if c[0] not in python_sorts],
            "first_surname",
        )
    if sort_key == "job_position__name":
        # Dentro de un mismo requisito, por apellidos y nombre.
        qs = qs.order_by(
            *qs.query.order_by, "first_surname", "second_surname",
            "given_name",
        )
    # H31 (S109). Miguel Ángel, tras un fallo real al paginar (la
    # página 2 no cargaba nada): "aquí nos convendría no paginar [...]
    # entonces cuando seleccionamos no los vamos a seleccionar a
    # todos." Con la lista ya en su propio contenedor con scroll
    # (`#personal-results-scroll`, S109), paginar ya no aporta nada
    # real y además rompe "seleccionar todos" (solo marcaba los 50 de
    # la página visible). Límite generoso (nunca "sin límite" real,
    # por si el censo crece mucho en el futuro) en vez de retirar
    # `Paginator` del todo -- mismo mecanismo, un único "page" que
    # cabe siempre entero.
    paginator = Paginator(qs, 2000)
    page = paginator.get_page(request.GET.get("page"))
    if ids_only:
        return _ordered_person_pks(
            company, list(page.object_list), sort_key, sort_dir,
        )
    page.object_list = _attach_required_document_alerts(
        list(page.object_list), person_ct,
    )
    page.object_list = _attach_person_avatars(page.object_list, person_ct)
    page.object_list = _attach_contract_alerts(page.object_list)
    states = onboarding_states(page.object_list)
    for person in page.object_list:
        person.onboarding = states[person.pk]
    # H24 (S144): sección vigente y horario que le toca (como Horarios).
    for row in schedule_rows(company, page.object_list):
        row.person.ws_row = row
    page.object_list = _python_sorted(
        list(page.object_list), sort_key, sort_dir)
    return {
        "page": page, "sort_key": sort_key, "sort_dir": sort_dir,
        "search": search, "sort_columns_person": sort_columns,
        "active_filter": request.GET.getlist("active"),
        "company_filter": request.GET.getlist("company"),
        "requirement_filter": request.GET.get("requirement", ""),
        "onboarding_filter": onboarding_raw,
        "onboarding_checked": onboarding_codes,
        "onboarding_choices": ONBOARDING_CHOICES,
        "section_filter": section_raw,
        "schedule_filter": schedule_raw,
        "no_section": NO_SECTION,
        "no_schedule": NO_SCHEDULE,
        "ws_sections": _sections(company),
        "ws_schedules": _schedules(company),
        # S147: base de los marcados (Administración > Usuarios).
        "ws_bases": Base.objects.filter(company=company).order_by("name"),
    }


def _clear_last_person_pointer(request):
    """
    H31 (S94). Limpia last_person_pk de 'documentation_hub' -- se
    llama al visitar el LISTADO de Personal (PersonalListFragmentView/
    PersonalResultsFragmentView), nunca la ficha de una persona
    concreta (PersonalDetailView es quien lo fija). Así el enlace
    "Documentación" del sidebar deja de apuntar a una ficha concreta
    en cuanto el usuario vuelve al listado desde dentro de
    Documentación -- Miguel Ángel, verbatim: "al principio volveré yo
    cuando desde la propia documentación yo cambie [...] ahí es cuando
    debe de cambiar."
    """
    cu = request.user.company_user
    nav_state, _created = PanelNavigationState.objects.get_or_create(
        company_user=cu, screen_key="documentation_hub",
        defaults={"state": {}},
    )
    state = nav_state.state if isinstance(nav_state.state, dict) else {}
    if state.get("last_person_pk") is not None:
        state["last_person_pk"] = None
        nav_state.state = state
        nav_state.save(update_fields=["state", "updated_at"])


def _python_sorted(people, sort_key, sort_dir):
    """
    Sorts that are not DB columns (onboarding, section, schedule).
    ---
    Los órdenes que no son columnas de BD: "Alta en el fichaje"
    (necesita `person.onboarding`), "Sección" y "Horario" (necesitan
    `person.ws_row`). Los que no tienen sección u horario, al final.
    """
    if sort_key == "onboarding":
        return sorted(
            people,
            key=lambda p: (p.onboarding.rank, p.onboarding.when is None,
                           p.onboarding.when or 0),
            reverse=sort_dir == "desc",
        )
    if sort_key in ("section", "schedule"):
        def _sort_value(person):
            row = person.ws_row
            if sort_key == "section":
                value = row.state.section.name if row.state.section else ""
            else:
                value = row.schedule.label if row.schedule else ""
            return value.upper()

        return sorted(
            [p for p in people if _sort_value(p)], key=_sort_value,
            reverse=sort_dir == "desc",
        ) + [p for p in people if not _sort_value(p)]
    return people


def _ordered_person_pks(company, people, sort_key, sort_dir):
    """
    Pks of the list in its order, computing only what the sort needs.
    ---
    Los pks del listado en su orden; solo calcula el estado del alta o
    la sección/horario si el orden los necesita.
    """
    if sort_key == "onboarding":
        from panel.personal_access import onboarding_states

        states = onboarding_states(people)
        for person in people:
            person.onboarding = states[person.pk]
    elif sort_key in ("section", "schedule"):
        from panel.views_worker_schedules import _rows as schedule_rows

        for row in schedule_rows(company, people):
            row.person.ws_row = row
    return [p.pk for p in _python_sorted(people, sort_key, sort_dir)]


def personal_list_neighbours(request, pk):
    """
    Previous and next person of the Personal list, with its saved filters.
    ---
    S144, Miguel Ángel: "debería dejarme pasar hacia el anterior o
    hacia la siguiente persona sin salir de ahí (según el filtro
    escogido)". Rehace el listado con los filtros y el orden que el
    usuario dejó en Personal (los mismos que restaura la pestaña) y
    devuelve (anterior, siguiente, posición 1-based, total). Si la
    persona no está en esa lista, (None, None, None, total).
    """
    import copy

    from django.http import QueryDict

    state = PanelNavigationState.objects.filter(
        company_user=request.user.company_user,
        screen_key="documentation_hub",
    ).values_list("state", flat=True).first()
    filters = state.get("filters") if isinstance(state, dict) else None
    fake = copy.copy(request)
    fake.GET = QueryDict(_build_personal_tab_querystring(filters or {}))
    pks = _person_list_page(fake, ids_only=True)
    if pk not in pks:
        return None, None, None, len(pks)
    index = pks.index(pk)
    previous_pk = pks[index - 1] if index > 0 else None
    next_pk = pks[index + 1] if index + 1 < len(pks) else None
    people = PersonIdentity.objects.in_bulk(
        [p for p in (previous_pk, next_pk) if p])
    return (
        people.get(previous_pk), people.get(next_pk), index + 1, len(pks),
    )


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
        _clear_last_person_pointer(request)
        ctx = _person_list_page(request)
        ctx["epi_items"] = EpiItemCatalog.objects.filter(
            is_active=True,
        ).order_by("family", "label")
        # S126: las que requieren firma NO van por aquí (solo por
        # "Preparar para Docuten", decisión de S124) -- antes salían en
        # los dos desplegables y parecían el mismo.
        ctx["notification_types"] = DocumentTypeCatalog.objects.filter(
            is_active=True, is_notification_template=True,
            requires_signature=False,
        ).exclude(content_html="").order_by("label")
        # H30 (S124): solo las circulares que requieren firma
        # certificada se preparan para Docuten.
        # Incluye las de PDF fijo (sin texto, con plantilla en PDF:
        # Plan Nacional de calor, S124).
        ctx["docuten_types"] = DocumentTypeCatalog.objects.filter(
            is_active=True, is_notification_template=True,
            requires_signature=True,
        ).filter(
            ~Q(content_html="")
            | Q(current_template__name__iendswith=".pdf")
        ).order_by("label")
        from worksites.models import Worksite
        ctx["docuten_worksites"] = Worksite.objects.filter(
            is_active=True,
        ).order_by("name")
        ctx["company_filter_choices"] = COMPANY_FILTER_CHOICES
        # H35 (S105): plantillas de dosier para la nueva acción masiva
        # "Generar dosieres" -- mismo criterio que epi_items/
        # notification_types de arriba, cargado una única vez en la
        # carga inicial de la pestaña.
        company = request.user.company_user.company
        # S130: selección de personas guardada (como Centros de gasto).
        saved_selection = get_saved_state_key(
            request.user.company_user, "personal_selection", "selection", [],
        )
        ctx["saved_person_selection"] = (
            saved_selection if isinstance(saved_selection, list) else []
        )
        # H24 (S144): pestaña de acciones elegida la última vez.
        ctx["person_actions_tab"] = get_saved_state_key(
            request.user.company_user, "personal_actions", "tab", "doc",
        )
        ctx["dossier_templates"] = company.dossier_templates.filter(
            scope=PersonalDossierTemplate.SCOPE_PERSONAL,
        ).order_by("name")
        # H31 (S109): grupos de reparto guardados -- sin filtro de
        # Company a propósito (PersonGroupTemplate cruza empresas por
        # diseño), cargado una única vez igual que el resto de esta
        # barra de acción masiva.
        # S147: en árbol (panel/person_groups.py), con los padres que
        # se pliegan recordados por usuario (screen_key "person_groups").
        from panel.person_groups import (
            collapsed_state, group_tree, parent_choices,
        )

        ctx["person_group_nodes"] = group_tree(
            request.user.company_user)
        ctx["person_group_parents"] = parent_choices(
            editor=request.user.company_user)
        # S147: por carpetas de creador (Generales/Usuarios/Propios).
        ctx["person_groups_collapsed"] = collapsed_state(
            request.user.company_user)
        # H31 (S109): catálogo de puestos para la acción masiva nueva
        # "Asignar puesto" -- mismo criterio que person_groups, cargado
        # una única vez en la carga inicial de la pestaña.
        ctx["job_positions"] = JobPosition.objects.order_by("name")
        # S146 (Miguel Ángel): en el alta la empresa y la sección se
        # eligen de un desplegable, nunca se escriben a mano.
        ctx["intake_company_choices"] = ALTA_COMPANY_CHOICES
        ctx["intake_section_choices"] = Section.objects.filter(
            company=company,
        ).order_by("name")
        # H31 (S113): lotes de EPIs guardados para la nueva acción
        # masiva de entrega -- mismo criterio que job_positions/
        # person_groups de arriba, cargado una única vez.
        ctx["epi_batch_templates"] = (
            EpiDeliveryBatchTemplate.objects.prefetch_related(
                "items",
            ).order_by("name")
        )
        # H31 (S129): exportar a Excel con plantilla, mismos roles que
        # la exportación de partes (lleva DNI, dirección y n.º de SS).
        ctx["can_export_personal"] = request.user.company_user.role in (
            CompanyUser.ROLE_ADMIN, CompanyUser.ROLE_ADMIN_SUPERVISOR,
            CompanyUser.ROLE_SUPERVISOR, CompanyUser.ROLE_WORKSHOPBOSS,
        )
        # H24 (S141): "Dar acceso al fichaje", mismos roles que crear
        # usuarios (SupervisorAccessMixin).
        ctx["can_create_accounts"] = request.user.company_user.role in (
            CompanyUser.ROLE_ADMIN, CompanyUser.ROLE_ADMIN_SUPERVISOR,
            CompanyUser.ROLE_SUPERVISOR, CompanyUser.ROLE_WORKSHOPBOSS,
        )
        # H31 (S136): "Volver a sacar la foto" masivo, mismos roles que
        # la gestión de la foto en la ficha.
        ctx["can_manage_photo"] = request.user.company_user.role in (
            CompanyUser.ROLE_DOCS_SUPERVISOR, CompanyUser.ROLE_ADMIN,
            CompanyUser.ROLE_ADMIN_SUPERVISOR,
        )
        return render(
            request, "panel/documentation_h30/_personal_pane.html", ctx
        )


def _phone_digits(field):
    """
    Phone field without spaces, dots, dashes or brackets (DB side).

    ---

    El teléfono sin espacios, puntos, guiones ni paréntesis, calculado
    en la propia consulta (S137, búsqueda de Personal por teléfono).
    """
    expr = F(field)
    for char in (" ", ".", "-", "(", ")", "/"):
        expr = Replace(expr, Value(char), Value(""))
    return expr


class PersonalResultsFragmentView(CompanyUserRequiredMixin, View):
    """Busqueda/orden/paginacion dentro de Personal -- solo los
    resultados, el formulario nunca se vuelve a pintar (H30 S50, ver
    _personal_search_form.html)."""

    def get(self, request):
        _clear_last_person_pointer(request)
        ctx = _person_list_page(request)
        return render(
            request, "panel/documentation_h30/_personal_results.html", ctx
        )


def _group_current_by_family(
    current_entries,
    exclude_family_codes=(),
    include_empty_families=(),
    for_person=False,
):
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

    `include_empty_families` (H31, S102): conjunto de códigos de
    familia que deben aparecer igual aunque no tengan ningún documento
    vigente (`documents: []`), en vez de desaparecer del todo del
    acordeón -- necesario para que exista un sitio real donde colgar
    el botón de subida por familia (pipeline de subida sin muestra).
    INCIDENTE REAL S102: la primera versión metía TODAS las familias
    de `FAMILY_CHOICES` sin distinción -- en la ficha de una PERSONA
    aparecían "Circulación", "Financiero" o "Bajas de máquina" (0),
    familias que son puramente de dominio MACHINE/COMPANY y no tienen
    ningún tipo documental de personal en el catálogo. El llamador
    debe pasar aquí solo las familias que de verdad tienen al menos un
    tipo activo del dominio relevante (ver `missing_types_by_family`,
    calculado ya con ese mismo filtro de dominio) -- nunca la lista
    completa de `FAMILY_CHOICES` a ciegas. Vacío por defecto -- no
    cambia el comportamiento de ningún otro llamador existente.
    """
    by_family = {}
    for entry in current_entries:
        family_code = entry.document_type.family if entry.document_type else ""
        if family_code in exclude_family_codes:
            continue
        by_family.setdefault(family_code, []).append(entry)

    ordered = []
    for code, _label in DocumentTypeCatalog.FAMILY_CHOICES:
        if code in exclude_family_codes:
            continue
        # S125: en la ficha de persona, Circulación se llama Conducción.
        label = DocumentTypeCatalog.family_label(code, for_person=for_person)
        if code in by_family:
            ordered.append({
                "code": code, "label": label, "documents": by_family[code],
            })
        elif code in include_empty_families:
            ordered.append({"code": code, "label": label, "documents": []})
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


def _partes_summary(entry_ids):
    """
    H31 (S77). Resumen agregado de Partes de trabajo -- NUNCA un
    listado plano parte a parte (Miguel Ángel, verbatim: "no sirve de
    nada ver un listado [...] parte día uno, parte día dos [...] qué
    sentido tiene eso para un supervisor"). Reutiliza exactamente el
    mismo dato que ya usa el Laboratorio de Análisis (H20,
    `analytics/views.py`) -- `WorkOrderEntryLine.delta_hours`, mismo
    criterio de exclusión de la hora fantasma de vacaciones
    (`exclude(vacation_period__isnull=False)`, ver
    AnalyticsLabDataView._line_cost) -- para no inflar las horas
    reales con el bloque administrativo de vacaciones.

    Devuelve: horas totales del periodo, desglose por máquina (horas
    por máquina, orden descendente) y resumen diario (fecha + horas
    ese día) -- exactamente lo que Miguel Ángel pidió: "las horas que
    ha echado [...] en qué máquina ha estado trabajando [...] el
    parte del día, resumen, con toda la hora del periodo."
    ---
    H31 (S77). Aggregated Partes de trabajo summary -- NEVER a flat
    part-by-part listing. Reuses the exact same data the Analytics Lab
    (H20) already computes -- `WorkOrderEntryLine.delta_hours`, same
    vacation-ghost-line exclusion criterion as
    `AnalyticsLabDataView._line_cost` -- so real worked hours aren't
    inflated by the administrative vacation block.

    Returns: total hours for the period, breakdown by machine (hours
    per machine, descending), and a daily summary (date + hours that
    day).
    """
    from collections import defaultdict

    lines = WorkOrderEntryLine.objects.filter(
        entry_id__in=entry_ids, delta_hours__isnull=False,
    ).exclude(vacation_period__isnull=False).select_related(
        "entry", "machine_asset",
    )

    hours_by_machine = defaultdict(float)
    machine_labels = {}
    hours_by_day = defaultdict(float)

    for line in lines:
        hours = float(line.delta_hours)
        if line.machine_asset:
            key = line.machine_asset.pk
            machine_labels[key] = (
                f"{line.machine_asset.code} — {line.machine_asset.brand_model}"
            )
        else:
            key = None
            machine_labels[None] = "Sin máquina resuelta"
        hours_by_machine[key] += hours
        if line.entry.work_date:
            hours_by_day[line.entry.work_date] += hours

    total_hours = sum(hours_by_machine.values())
    by_machine = sorted(
        (
            {"label": machine_labels[key], "hours": hours}
            for key, hours in hours_by_machine.items()
        ),
        key=lambda row: row["hours"], reverse=True,
    )
    by_day = sorted(
        (
            {"date": day, "hours": hours}
            for day, hours in hours_by_day.items()
        ),
        key=lambda row: row["date"],
    )
    return total_hours, by_machine, by_day


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
        if (
            current_latest is None
            or delivery.delivery_date > current_latest.delivery_date
        ):
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
        delivery.epi.technical_docs = technical_docs_by_epi.get(
            delivery.epi_id, []
        )
        family = delivery.epi.family or "Sin familia asignada"
        by_family.setdefault(family, []).append(delivery)

    return [
        {
            "label": family,
            "deliveries": sorted(items, key=lambda d: d.epi.label),
        }
        for family, items in sorted(by_family.items())
    ]


def _parse_date_param(raw):
    """
    H31 (S77). Parsea un parámetro GET de fecha YYYY-MM-DD (input
    HTML type="date"); devuelve None ante cualquier valor vacío o
    inválido, nunca lanza excepción.
    ---
    H31 (S77). Parses a YYYY-MM-DD GET date parameter (HTML
    type="date" input); returns None on any empty or invalid value,
    never raises.
    """
    from datetime import date as _date
    if not raw:
        return None
    try:
        return _date.fromisoformat(raw)
    except ValueError:
        return None


class PersonalWorkdayDetailView(CompanyUserRequiredMixin, View):
    """
    H31 (S77). Detalle real de un día concreto dentro de Partes de
    trabajo -- el resumen agregado se queda como está (confirmado por
    Miguel Ángel), pero además "debe de poder verse el parte en sí
    [...] qué repuestos se gastaron, el tiempo que se echó, cuántas
    tareas hubo, en qué estuvo cada tarea, qué máquinas se tocaron ese
    día." Reutiliza el mismo modal genérico de historial
    (`openHistoryModal`, ya usado por documentos/EPIs) -- nunca un
    modal nuevo.

    Une los `WorkOrderEntry` digitales (`uploaded_by` fiable) y los
    del histórico PDF vinculados por nombre normalizado (mismo
    criterio que el resto de Partes de trabajo), filtrados a la fecha
    pedida, y expone sus `WorkOrderEntryLine` (máquina, horas,
    descripción, reparación, repuestos vía `SparePartLine`).
    ---
    H31 (S77). Real detail of a specific day within Partes de
    trabajo. Reuses the same generic history modal already used by
    documents/EPIs. Unions digital `WorkOrderEntry` rows (reliable
    `uploaded_by` link) and historical PDF rows matched by normalized
    name, filtered to the requested date, and exposes their
    `WorkOrderEntryLine` rows (machine, hours, description, repair
    notes, spare parts via `SparePartLine`).
    """

    def get(self, request, pk, date_iso):
        person = get_object_or_404(
            PersonIdentity.objects.select_related("company_user"), pk=pk,
        )
        try:
            target_date = date.fromisoformat(date_iso)
        except ValueError:
            return HttpResponse("Fecha inválida.", status=400)

        entry_ids = []
        if person.company_user_id:
            entry_ids += list(
                WorkOrderEntry.objects.filter(
                    work_order__uploaded_by=person.company_user,
                    work_order__source=WorkOrder.Source.DIGITAL,
                    work_date=target_date,
                ).values_list("pk", flat=True),
            )
        entry_ids += list(
            _historical_pdf_entries_for_person(person).filter(
                work_date=target_date,
            ).values_list("pk", flat=True),
        )

        entries = WorkOrderEntry.objects.filter(
            pk__in=entry_ids,
        ).order_by("pk")

        lines = WorkOrderEntryLine.objects.filter(
            entry_id__in=entry_ids,
        ).exclude(vacation_period__isnull=False).select_related(
            "entry", "machine_asset", "breakdown_ticket",
        ).prefetch_related("spare_parts", "photos").order_by(
            "entry__page_number", "line_number",
        )
        lines_by_entry = {}
        for line in lines:
            # H31 (S77). photo_entries -- misma resolución de URL
            # firmada de GCS que ya usa el widget de fotos real
            # (_build_photo_entries, panel/views_task_photos.py),
            # nunca calculada en la plantilla (directriz "plantillas
            # tontas").
            line.photo_entries = _build_photo_entries(line.photos.all())
            lines_by_entry.setdefault(line.entry_id, []).append(line)

        # H31 (S77). Presentación tipo documento -- Miguel Ángel:
        # "quiero este formato [el del formulario real del operario,
        # panel/operator/form_entry.html] pero ya solo que se vea
        # únicamente, sin el modo de edición, sin las indicaciones
        # para realizar el parte [...] como si fuera el documento del
        # parte digital." Un bloque por WorkOrderEntry (normalmente
        # uno por día, pero se soporta más de uno sin asumir nada),
        # cada uno con sus tareas -- mismos campos reales del
        # formulario (fecha, dieta, pausa de comida; por tarea:
        # máquina, H.C./H.F., O.R., avería, reparación, in situ,
        # ticket, fotos, repuestos), nunca los widgets de edición.
        parte_blocks = [
            {"entry": entry, "lines": lines_by_entry.get(entry.pk, [])}
            for entry in entries
        ]

        return render(
            request, "panel/documentation_h30/_personal_workday_detail.html",
            {"target_date": target_date, "parte_blocks": parte_blocks},
        )


class PersonalDetailView(CompanyUserRequiredMixin, View):
    """
    H31 (S94, corregido en la misma sesión tras aclaración explícita
    de Miguel Ángel). main_accordion_open: sección del acordeón
    principal de la ficha (Datos personales/Laboral/Salud/
    Documentación/EPIs) persistida en PanelNavigationState
    (screen_key='personal_ficha'), por PERSONA (no global) -- cada
    ficha recuerda su propia última sección abierta, independiente de
    las demás. Miguel Ángel, verbatim: "si yo busco otra persona,
    cuando salga a esa persona me tendría que presentar lo primero de
    esa persona" -- es decir, cada pk tiene su propio puntero.

    Además, visitar esta vista marca 'documentation_hub' (active_tab=
    'personal', last_person_pk=pk) -- así el enlace "Documentación"
    del sidebar (ver panel/context_processors.
    documentation_sidebar_link_context) sabe que hay que volver
    DIRECTAMENTE a esta ficha concreta, no al listado, hasta que el
    usuario vuelva al listado de Personal desde dentro de
    Documentación (PersonalTabFragmentView/PersonalResultsFragmentView
    limpian last_person_pk al visitarse). Miguel Ángel, verbatim:
    "cuando yo vuelva a documentación, debe de ponerme por donde
    estaba [...] al principio volveré yo cuando desde la propia
    documentación yo cambie [...] me meta en otra pestaña, ahí es
    cuando debe de cambiar."
    """

    def get(self, request, pk):
        cu = request.user.company_user

        nav_state, _created = PanelNavigationState.objects.get_or_create(
            company_user=cu, screen_key="documentation_hub",
            defaults={"state": {}},
        )
        _hub_state = (
            nav_state.state if isinstance(nav_state.state, dict) else {}
        )
        _hub_state["active_tab"] = "personal"
        _hub_state["last_person_pk"] = pk
        nav_state.state = _hub_state
        nav_state.save(update_fields=["state", "updated_at"])

        ficha_nav_state = PanelNavigationState.objects.filter(
            company_user=cu, screen_key="personal_ficha",
        ).first()
        _ficha_state = (
            ficha_nav_state.state
            if ficha_nav_state and isinstance(ficha_nav_state.state, dict)
            else {}
        )
        _person_accordion = (
            _ficha_state.get("person_accordion")
            if isinstance(_ficha_state.get("person_accordion"), dict) else {}
        )
        main_accordion_open = _person_accordion.get(
            str(pk), "collapseDatosPersonales",
        )
        if main_accordion_open not in (
            "collapseDatosPersonales", "collapseLaboralMain",
            "collapseSaludMain", "collapseDocumentacionMain",
            "collapseEpisMain", "collapseAccesoriosMain",
            "collapsePeriodosMain",
        ):
            main_accordion_open = "collapseDatosPersonales"

        # H31 (S103). Selección de documentos para dossieres/adjuntos
        # -- misma fila de PanelNavigationState que el acordeón
        # (person_accordion), clave nueva "document_selection" por
        # persona (ver panel/views_navigation_state.py,
        # NESTED_MERGE_KEYS). Lista de IDs de DocumentIndexEntry
        # marcados por el usuario en esta ficha; persiste entre
        # cambios de pestaña/acordeón porque vive en BD, no en el DOM.
        _document_selection = (
            _ficha_state.get("document_selection")
            if isinstance(_ficha_state.get("document_selection"), dict) else {}
        )
        selected_document_ids = _document_selection.get(str(pk)) or []
        if not isinstance(selected_document_ids, list):
            selected_document_ids = []
        # S125: mismo filtro que la vista previa -- el contador decía 2
        # con la lista vacía (documentos ya en la papelera o retirados).
        selected_document_ids = _alive_selected_ids(
            selected_document_ids, PersonIdentity, pk,
        )

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
        # S119: qué tipos exige el requisito de ESTA persona en
        # concreto -- decide si un tipo caducado y sin sustituto sigue
        # contando como vigente (ver docstring de _split_current_obsolete).
        required_type_ids = get_required_type_ids(person)
        current, obsolete = _split_current_obsolete(
            entries, required_type_ids,
        )
        # H30 (S123). Los documentos laborales acumulables (contrato,
        # alta, IDC, baja...) de periodos ANTERIORES al actual pasan al
        # historial de su tipo. Miguel Ángel, sobre su propia ficha:
        # "si vamos a estar metiendo [...] un contrato y otro y otro,
        # al final tengo 15 contratos ahí [...] ¿entonces lo del
        # historial para qué sirve?". Cada periodo sigue con su
        # contrato en "Periodos de contratación"; Documentos muestra
        # solo el juego del periodo en curso (o el último).
        employment = _person_employment_periods(person)
        current, obsolete = _move_previous_period_documents(
            current, obsolete, employment["periods"],
        )
        # S125: en Laboral, solo el vigente de cada tipo; el resto (con
        # o sin fecha) al historial del tipo.
        current, obsolete = _keep_latest_laboral_per_type(current, obsolete)
        # H30 (S120). Matriz de clases del carné de conducir (columnas
        # 9-12 del reverso) colgada de cada carné vigente, para la
        # tabla de clases de su fila -- ver attach_driving_grants.
        attach_driving_grants(current, person)
        # H30 (S120). Documentos de un subtipo (parent_type) dentro de
        # la fila del documento vigente de su tipo padre, nunca como
        # fila propia -- ver attach_subtype_documents.
        current, obsolete = attach_subtype_documents(
            entries, current, obsolete,
        )
        # S145 (Miguel Ángel: "cuando ya he partido, ese documento no
        # sé dónde he ido a parar"): lo sacado de un dossier lleva el
        # botón "Original", que abre el dossier del que salió.
        for entry in current:
            match = _SOURCE_DOSSIER_RE.search(entry.curator_note or "")
            entry.source_dossier_pk = int(match.group(1)) if match else None
        # H31 (S119): "Falta"/"Caducado" del puesto ya NO se calculan
        # aqui a partir de `current` (cualquier documento vigente con
        # `needs_attention`) -- ver `resolve_required_document_status`
        # mas abajo, unica fuente para ambos, ceñida a los tipos
        # obligatorios del puesto de la persona.
        _laboral_salud_codes = (
            DocumentTypeCatalog.FAMILY_LABORAL,
            DocumentTypeCatalog.FAMILY_SALUD_BAJAS_PERSONA,
        )
        # H31 (S102). Pipeline de subida "sin muestra" -- Miguel
        # Ángel: "cada grupo documental [tenga] su propio pipeline de
        # subida, que se encarga de ver qué tipos tienen muestra y
        # desplegar únicamente los que no la tienen." Un único cálculo
        # aquí (sin una query por familia): todos los tipos activos de
        # personal, menos los que esta persona ya tiene vigentes o
        # históricos (cualquier entrada viva, aunque esté marcada
        # obsoleta -- si ya existe una, se actualiza con el botón
        # "Actualizar" de su fila, no con el pipeline por familia).
        # Sin opción de crear tipo nuevo aquí (retirada en la misma
        # sesión, ver `_personal_detail.html`) -- la creación de
        # `DocumentTypeCatalog` queda limitada al administrador; un
        # tipo que no existe en el catálogo se sube por el Explorador
        # de archivos, nunca desde este modal.
        # S123: los tipos acumulables (contratos, altas, cursos...) se
        # ofrecen siempre, aunque la persona ya tenga alguno -- Miguel
        # Ángel: "¿cómo subo el contrato nuevo?". Con uno ya subido,
        # "+ Subir" no ofrecía "Contrato laboral".
        # S130: igual que en la ficha de máquina, "+ Subir" ofrece
        # siempre todos los tipos de la familia, también los que ya
        # tiene (la subida aplica la sustitución: el anterior pasa a
        # histórico).
        missing_types_by_family = {}
        for dt in DocumentTypeCatalog.objects.filter(
            domain__in=[
                DocumentTypeCatalog.DOMAIN_PERSONAL,
                DocumentTypeCatalog.DOMAIN_BOTH,
            ],
            is_active=True,
        ).order_by("label"):
            missing_types_by_family.setdefault(dt.family, []).append(dt)
        # H31 (S109), punto 3 corregido: el triangulo de "documento
        # FALTANTE" ya NO usa missing_types_by_family (catalogo
        # completo, 70-80 tipos -- eso sigue alimentando solo el
        # boton "+ Subir", que debe seguir ofreciendo cualquier tipo
        # opcional). El triangulo usa exclusivamente los tipos
        # obligatorios del PUESTO de la persona
        # (`JobPosition.required_document_types`) -- Miguel Angel:
        # "no es cuestion de marcar cuando falte uno de los 70 u 80
        # tipos [...] sino de los documentos que realmente son
        # necesarios [...] dependiendo del tipo de puesto". Sin
        # puesto asignado, ningun tipo se marca como faltante -- nunca
        # se asume un conjunto por defecto.
        #
        # H31 (S119): "Falta" y "Caducado" del triángulo salen SOLO de
        # los tipos obligatorios del puesto de la persona EN ESTE
        # MOMENTO (`JobPosition.required_document_types`, nunca un
        # conjunto fijo en el código -- Miguel Ángel: "no se puede
        # hardcodear nada, ni los grupos que hay, ni los documentos").
        # Un tipo obligatorio caducado sin sustituto cuenta como
        # "Caducado", nunca como "Falta" -- `resolve_required_document_
        # status` mira el documento MÁS MODERNO de cada tipo exigido,
        # sin pasar por `is_current()` (que lo habría excluido de la
        # competición por estar caducado y sin sustituto, como si no
        # existiera). Sin puesto asignado, ningún tipo se marca como
        # obligatorio -- nunca se asume un conjunto por defecto.
        missing_required_types_by_family, attention_types_by_family = (
            resolve_required_document_status(person)
        )
        # INCIDENTE REAL S102: `include_empty_families` recibe SOLO
        # las familias con algún tipo de dominio PERSONAL/BOTH
        # pendiente (`missing_types_by_family`) -- nunca el
        # `FAMILY_CHOICES` completo, o aparecen en la ficha de una
        # persona familias puramente de MACHINE/COMPANY (Circulación,
        # Financiero, Bajas de máquina...) sin ningún tipo aplicable.
        families = _group_current_by_family(
            current, exclude_family_codes=_laboral_salud_codes,
            include_empty_families=missing_types_by_family.keys(),
            for_person=True,
        )
        # H31 (S109). Miguel Ángel, con captura de pantalla real: el
        # triángulo de "Identidad y personal (base)" (dentro del
        # acordeón de segundo nivel) sí funcionaba bien, pero no subía
        # al acordeón de PRIMER nivel "Documentación" que lo envuelve
        # -- "Salud" y "Laboral" sí lo mostraban porque para ellos el
        # primer nivel ES la familia, sin un segundo nivel de por
        # medio. Se agrega aquí si CUALQUIERA de las familias del
        # acordeón genérico (nunca Laboral/Salud, que ya tienen su
        # propio triángulo de primer nivel) tiene algo que avisar.
        documentacion_alert_titles = []
        for fam in families:
            fam_missing = missing_required_types_by_family.get(fam["code"])
            fam_attention = attention_types_by_family.get(fam["code"])
            if fam_missing:
                documentacion_alert_titles.append(
                    "Falta (%s): %s"
                    % (
                        fam["label"],
                        ", ".join(dt.label for dt in fam_missing),
                    ),
                )
            if fam_attention:
                documentacion_alert_titles.append(
                    "Caducado (%s): %s" % (
                        fam["label"], ", ".join(fam_attention),
                    ),
                )
        documentacion_has_alert = bool(documentacion_alert_titles)
        # H31 (S77). Documentos de las dos families que se sacan de
        # Documentación a su propio acordeón de primer nivel -- el
        # documento es el mismo de siempre (DocumentIndexEntry), solo
        # cambia dónde se pinta (ver docstring de
        # _group_current_by_family, parámetro exclude_family_codes).
        laboral_documents = [
            entry
            for entry in current
            if entry.document_type
            and entry.document_type.family
            == DocumentTypeCatalog.FAMILY_LABORAL
        ]
        # S125: aviso por antigüedad (o caducidad) del contrato vigente.
        contract_alert = _contract_alert(person)
        contract_review = _contract_review_info(person)
        for entry in laboral_documents:
            is_contract = entry.document_type.code == "CONTRATO"
            entry.contract_alert = contract_alert if is_contract else None
            entry.contract_review = contract_review if is_contract else ""
        salud_documents = [
            entry
            for entry in current
            if entry.document_type
            and entry.document_type.family
            == DocumentTypeCatalog.FAMILY_SALUD_BAJAS_PERSONA
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
        # H24 (S130). Ausencias que no son vacaciones ni baja, por la
        # ficha (person), tenga o no cuenta de panel.
        absence_periods = AbsencePeriod.objects.filter(
            person=person,
        ).select_related("category").order_by("-date_start")
        # H31 (S77). Partes de trabajo digitales -- uploaded_by es el
        # propio operario autenticado (ver panel/views_operator.py),
        # vínculo 100% fiable, sin resolución por nombre. Solo
        # source=DIGITAL -- GENERATED es la tarea fantasma
        # administrativa de vacaciones (hr_calendar/services.py), ya
        # visible en el bloque Vacaciones de este mismo acordeón; no
        # es "trabajo real" y no debe contar aquí.
        digital_work_orders = (
            WorkOrder.objects.filter(
                uploaded_by=person.company_user,
                source=WorkOrder.Source.DIGITAL,
            )
            if person.company_user_id else WorkOrder.objects.none()
        )
        # H31 (S77). Histórico PDF resuelto por nombre normalizado --
        # ver _historical_pdf_entries_for_person().
        historical_pdf_entries = _historical_pdf_entries_for_person(person)

        # H31 (S77). Filtro de Partes de trabajo -- periodo de cobro
        # REAL (ivr_config.WorkPeriod, ver Key Learning H20/S010: no
        # es el mes natural, es el periodo de liquidación real -- p.
        # ej. 21 a 20 del mes siguiente para horas extra, aunque el
        # periodo ordinario sea 1 a 31), más rango manual de fechas.
        # El periodo, si se elige, tiene prioridad sobre el rango
        # manual (mismo dato, más preciso).
        work_periods = (
            WorkPeriod.objects.filter(
                company_user=person.company_user,
            ).order_by("-start_date")
            if person.company_user_id else WorkPeriod.objects.none()
        )
        partes_period_id = request.GET.get("partes_period", "").strip()
        partes_from = _parse_date_param(request.GET.get("partes_from"))
        partes_to = _parse_date_param(request.GET.get("partes_to"))
        partes_sort = request.GET.get("partes_sort", "desc")
        if partes_sort not in ("asc", "desc"):
            partes_sort = "desc"

        # H31 (S77). Por defecto, el periodo de cobro ACTIVO (el que
        # cubre hoy), nunca "Todos" -- petición explícita de Miguel
        # Ángel: "se deben mostrar por defecto los partes del periodo
        # activo." Se aplica solo si el usuario no ha tocado ningún
        # control del filtro todavía (sin partes_period NI partes_from
        # NI partes_to en la querystring real).
        partes_explicit_filter = bool(
            partes_period_id or "partes_from" in request.GET
            or "partes_to" in request.GET,
        )
        selected_period = None
        if partes_period_id:
            selected_period = next(
                (p for p in work_periods if str(p.pk) == partes_period_id),
                None,
            )
        elif not partes_explicit_filter and person.company_user_id:
            selected_period = _resolve_work_period(
                person.company_user, timezone.now().date(),
            )
        if selected_period:
            partes_from = selected_period.start_date
            partes_to = selected_period.end_date

        if partes_from:
            digital_work_orders = digital_work_orders.filter(
                entries__work_date__gte=partes_from,
            )
            historical_pdf_entries = historical_pdf_entries.filter(
                work_date__gte=partes_from,
            )
        if partes_to:
            digital_work_orders = digital_work_orders.filter(
                entries__work_date__lte=partes_to,
            )
            historical_pdf_entries = historical_pdf_entries.filter(
                work_date__lte=partes_to,
            )
        digital_work_orders = digital_work_orders.distinct()

        # H31 (S77). Resumen agregado -- NUNCA listado plano parte a
        # parte (Miguel Ángel: "no sirve de nada ver un listado [...]
        # qué sentido tiene eso para un supervisor"). Ver docstring de
        # _partes_summary().
        _digital_entry_ids = list(WorkOrderEntry.objects.filter(
            work_order__in=digital_work_orders,
        ).values_list("pk", flat=True))
        _historical_entry_ids = list(historical_pdf_entries.values_list(
            "pk", flat=True,
        ))
        partes_total_hours, partes_by_machine, partes_by_day = _partes_summary(
            _digital_entry_ids + _historical_entry_ids,
        )
        if partes_sort == "desc":
            partes_by_day = list(reversed(partes_by_day))

        # H31 (S74). Avatar -- reutiliza el mismo mecanismo genérico
        # domain_content_type/domain_object_id que cualquier otro
        # documento vinculado, filtrando por el código de catálogo
        # IMAGEN ya sembrado (H30 S67). El más reciente gana si hay
        # más de una imagen vigente.
        # H35 (S105): Miguel Ángel pidió poder usar como foto de
        # perfil cualquier documento-imagen YA indexado con su tipo
        # real (DNI, carnet de gruista, etc.) sin perder esa
        # clasificación -- el mecanismo IMAGEN de S73 reasignaba el
        # tipo, así que no servía para esto. `avatar_document` (campo
        # dedicado nuevo) tiene prioridad si está relleno; si no, cae
        # al mecanismo IMAGEN de siempre, sin romper fichas ya usando
        # "Cambiar foto".
        avatar = (
            person.avatar_document
            or entries.filter(document_type__code="IMAGEN").first()
        )
        # H31 (S134): la foto de carné recortada (PersonIdPhoto) manda
        # sobre las dos anteriores. Sin cargar la imagen: solo si existe
        # y de qué documento sale.
        id_photo = PersonIdPhoto.objects.filter(person=person).values(
            "source_id", "source__document_type__label", "extracted_at",
            "is_manual",
        ).first()
        # S136: documentos de los que se puede sacar la foto a mano en
        # la ventana de gestión, en el mismo orden que la búsqueda
        # automática (vigentes primero).
        from document_explorer.id_photo_service import candidates

        photo_sources = list(candidates(person).values(
            "pk", "document_type__label", "expiry_date", "is_obsolete",
        )[:30])
        photo_url = (
            "%s?v=%s" % (
                reverse("panel:documentation_personal_photo",
                        args=[person.pk]),
                int(id_photo["extracted_at"].timestamp()),
            )
            if id_photo else (
                reverse("panel:documentation_document_view",
                        args=[avatar.pk])
                if avatar else ""
            )
        )
        doc_types = DocumentTypeCatalog.objects.filter(
            is_active=True, domain__in=["PERSONAL", "BOTH"],
        ).order_by("label")
        # S126: las que requieren firma van solo por Docuten (S124).
        notification_types = DocumentTypeCatalog.objects.filter(
            is_active=True, is_notification_template=True,
            requires_signature=False,
        ).exclude(content_html="").order_by("label")
        epi_deliveries = EpiDelivery.objects.filter(
            person=person,
        ).select_related("epi").order_by("-delivery_date")
        epi_families = _group_epi_deliveries_by_family(epi_deliveries)
        epi_items = EpiItemCatalog.objects.filter(
            is_active=True,
        ).order_by("family", "label")
        # H31 (S109). Catálogo completo para el selector de "Cambiar
        # tipo" de un documento -- Miguel Ángel, tras encontrar un
        # documento mal clasificado (una carta de baja voluntaria
        # tipada como CONTRATO por un falso positivo de la señal de
        # contenido): "no encuentro ni en la suya ni en la de ningún
        # otro el mecanismo para poder cambiar el tipo de un
        # documento". No existía ningún camino en el panel para
        # corregir una clasificación equivocada sin pasar por una
        # campaña completa de retipado -- este selector cubre el caso
        # de UN documento suelto, mismo criterio de agrupación por
        # familia que el resto de selectores de tipos de esta ficha.
        all_document_types = DocumentTypeCatalog.objects.filter(
            is_active=True, domain__in=["PERSONAL", "BOTH"],
        ).order_by("family", "label")
        # H24 (S129): fichajes en la ficha, solo para quien ve la pestaña
        # Fichajes (llevan posiciones GPS).
        import os as _os_clk
        from django.utils import timezone as _tz_clk
        _today_clk = _tz_clk.localdate()
        can_view_clock = request.user.company_user.role in (
            CompanyUser.ROLE_ADMIN, CompanyUser.ROLE_ADMIN_SUPERVISOR,
            CompanyUser.ROLE_SUPERVISOR, CompanyUser.ROLE_WORKSHOPBOSS,
        )
        # H24 (S144): bloque Sección de la ficha.
        from panel.views_personal_medical_leave import (
            medical_leave_block_context,
        )
        from panel.views_personal_section import section_block_context

        # S144: anterior/siguiente según los filtros de Personal.
        (nav_previous, nav_next, nav_position,
         nav_total) = personal_list_neighbours(request, person.pk)
        return render(
            request,
            "panel/documentation_h30/_personal_detail.html",
            {
                **section_block_context(request, person),
                "nav_previous": nav_previous,
                "nav_next": nav_next,
                "nav_position": nav_position,
                "nav_total": nav_total,
                # H24 (S144): bajas médicas (acordeón Laboral).
                **medical_leave_block_context(request, person),
                "can_view_clock_events": can_view_clock,
                "clock_date_from": _today_clk.replace(day=1),
                "clock_date_to": _today_clk,
                "google_maps_api_key": (
                    _os_clk.environ.get("GOOGLE_MAPS_API_KEY", "")
                    if can_view_clock
                    else ""
                ),
                "google_maps_map_id": _os_clk.environ.get(
                    "GOOGLE_MAPS_MAP_ID", ""
                ),
                "person": person,
                "current": current,
                "obsolete": obsolete,
                "families": families,
                "laboral_documents": laboral_documents,
                "contract_alert": contract_alert,
                "salud_documents": salud_documents,
                "missing_types_by_family": missing_types_by_family,
                "missing_required_types_by_family": (
                    missing_required_types_by_family
                ),
                "attention_types_by_family": attention_types_by_family,
                "documentacion_has_alert": documentacion_has_alert,
                "documentacion_alert_title": ". ".join(
                    documentacion_alert_titles
                ),
                "job_positions": JobPosition.objects.order_by("name"),
                "all_document_types": all_document_types,
                "vacation_periods": vacation_periods,
                "absence_periods": absence_periods,
                "partes_total_hours": partes_total_hours,
                "partes_by_machine": partes_by_machine,
                "partes_by_day": partes_by_day,
                "partes_digital_count": len(_digital_entry_ids),
                "partes_historical_count": len(_historical_entry_ids),
                "work_periods": work_periods,
                "selected_period": selected_period,
                "partes_from": partes_from,
                "partes_to": partes_to,
                "partes_sort": partes_sort,
                "partes_filtered": bool(
                    partes_period_id
                    or partes_from
                    or partes_to
                    or partes_sort != "desc",
                ),
                "avatar": avatar,
                "id_photo": id_photo,
                "photo_sources": photo_sources,
                "photo_url": photo_url,
                "can_manage_photo": request.user.company_user.role
                in (
                    CompanyUser.ROLE_DOCS_SUPERVISOR,
                    CompanyUser.ROLE_ADMIN,
                    CompanyUser.ROLE_ADMIN_SUPERVISOR,
                ),
                "doc_types": doc_types,
                "epi_deliveries": epi_deliveries,
                "epi_families": epi_families,
                "epi_items": epi_items,
                # H30 (S121): accesorios de elevación entregados ahora a esta
                # persona (su responsable) -- solo consulta, el CRUD vive en
                # su pestaña del hub.
                "lifting_accessories": _person_lifting_accessories(
                    person,
                    request.user.company_user.company,
                ),
                # H30 (S122): periodos de contratación (altas) con su
                # contrato emparejado a ±15 días, o "falta contrato".
                "employment": employment,
                # H31 (S113): lotes de EPIs guardados para el nuevo flujo de
                # entrega desde la ficha individual (mismo modal que la
                # acción masiva de Personal).
                "epi_batch_templates": (
                    EpiDeliveryBatchTemplate.objects.prefetch_related(
                        "items",
                    )
                ).order_by(
                    "name"
                ),
                "notification_types": notification_types,
                "active_nav": "documentation_hub",
                "main_accordion_open": main_accordion_open,
                "selected_document_ids": selected_document_ids,
            },
        )


def _move_previous_period_documents(current, obsolete, periods_newest_first):
    """
    H30 (S123). Moves the cumulative LABORAL documents dated before the
    latest employment period (start minus the period matching window)
    from `current` to `obsolete`, so the person detail page shows only
    the current set and the rest lives in each type's history.

    ---

    Pasa de `current` a `obsolete` los documentos LABORAL acumulables
    fechados antes del último periodo de contratación (su alta menos la
    ventana de emparejamiento de periodos, para que el IDC o el
    contrato fechados unos días antes del alta sigan contando como de
    ese periodo). Sin fecha: se quedan a la vista, para poder
    corregirlos. Sin periodos: no se toca nada. Solo afecta a la ficha
    de persona; avisos y requisitos siguen con `_split_current_obsolete`.
    """
    from datetime import timedelta

    from document_explorer import employment_period_service as periods

    if not periods_newest_first:
        return current, obsolete
    latest_start = periods_newest_first[0].start_date
    if not latest_start:
        return current, obsolete
    cutoff = latest_start - timedelta(days=periods.MATCH_WINDOW_DAYS)
    kept, moved = [], []
    for entry in current:
        document_type = entry.document_type if entry.document_type_id else None
        is_previous = (
            document_type is not None
            and document_type.is_cumulative
            and document_type.family == DocumentTypeCatalog.FAMILY_LABORAL
            and entry.issue_date is not None
            and entry.issue_date < cutoff
        )
        (moved if is_previous else kept).append(entry)
    return kept, obsolete + moved


def _contract_alert(person):
    """
    Age (or expiry) alert of the person's current contract.

    ---

    Aviso del contrato vigente de un trabajador activo (H30, S125). No
    hay forma de saber cuándo acaba un indefinido o un fin de obra, así
    que se avisa por antigüedad para que el supervisor revise si falta
    un contrato más reciente. Miguel Ángel: más de 1 año amarillo, más
    de 2 naranja, más de 3 rojo; un temporal con fin ya pasado,
    caducado. El vigente es el contrato, prórroga o modificación de
    fecha más reciente.

    Revisión (S125): si el supervisor pulsa "Correcto", la antigüedad
    cuenta desde ese día (contador a cero) y un temporal caducado
    revisado después de su fin deja de salir como caducado. Un contrato
    nuevo cuenta desde su propia fecha. Devuelve {level, css, text,
    reviewed_text} o None.
    """
    from document_explorer.employer_service import person_contracts

    if person.is_active_employee is not True:
        return None
    return _contract_alert_for(person, person_contracts(person).first())


def _contract_alert_for(person, latest):
    """
    Contract alert of a person given their latest contract document.

    ---

    Aviso del contrato de una persona dado su contrato vigente ya
    resuelto -- la ficha lo busca de uno en uno y el listado de todos a
    la vez (`_attach_contract_alerts`), con la misma regla.
    """
    from datetime import date

    if latest is None:
        return None
    today = date.today()
    reviewed = person.contract_reviewed_at
    reviewed_text = ""
    if reviewed:
        reviewer = person.contract_reviewed_by
        reviewed_text = "Revisado el %s%s" % (
            reviewed.strftime("%d/%m/%Y"),
            " por %s" % (
                reviewer.user.get_full_name() or reviewer.user.username
            ) if reviewer and reviewer.user_id else "",
        )
    expired = latest.expiry_date and latest.expiry_date < today
    if expired and not (reviewed and reviewed >= latest.expiry_date):
        return {
            "level": 3, "css": "text-bg-danger",
            "text": "Contrato caducado el %s" % (
                latest.expiry_date.strftime("%d/%m/%Y")
            ),
            "reviewed_text": reviewed_text,
        }
    since = max(
        (d for d in (latest.issue_date, reviewed) if d), default=None,
    )
    if since is None:
        return None
    age_days = (today - since).days
    for years, level, css in (
        (3, 3, "text-bg-danger"),
        (2, 2, "contract-alert-orange"),
        (1, 1, "text-bg-warning"),
    ):
        if age_days > 365 * years:
            return {
                "level": level, "css": css,
                "text": "Contrato sin revisar desde hace más de %d año%s "
                        "(%s): comprobar si hay uno más reciente" % (
                            years, "" if years == 1 else "s",
                            since.strftime("%d/%m/%Y"),
                        ),
                "reviewed_text": reviewed_text,
            }
    return None


class PersonalContractReviewedView(DocsUploadAccessMixin, View):
    """
    POST: review, restore or clear the current contract review (JSON).

    ---

    POST: revisión del contrato vigente (H30, S125). Respuesta JSON para
    que el botón muestre el resultado real.

    - action=review (por defecto): "Correcto" -- el aviso de antigüedad
      vuelve a contar desde hoy. Devuelve la revisión anterior para
      poder deshacer al momento.
    - action=restore (+ previous_date AAAA-MM-DD o vacío, previous_by):
      "Deshacer" -- deja exactamente la revisión anterior al clic.
    - action=clear: "Anular revisión" -- quita la revisión; el aviso
      vuelve a calcularse desde la fecha del contrato (en el peor caso
      reaparece un aviso, nunca se esconde uno).
    Miguel Ángel (S125): "si pulso correcto, ¿hay algún botón para
    revertir por si pulso sin querer?"
    """

    def post(self, request, pk):
        from datetime import date

        person = PersonIdentity.objects.filter(pk=pk).first()
        if person is None:
            return JsonResponse(
                {"ok": False, "error": "La persona no existe."}, status=404,
            )
        action = request.POST.get("action", "review")
        previous = {
            "previous_date": (
                person.contract_reviewed_at.isoformat()
                if person.contract_reviewed_at else ""
            ),
            "previous_by": person.contract_reviewed_by_id or "",
        }
        if action == "review":
            person.contract_reviewed_at = date.today()
            person.contract_reviewed_by = request.user.company_user
        elif action == "restore":
            raw_date = request.POST.get("previous_date", "")
            raw_by = request.POST.get("previous_by", "")
            try:
                person.contract_reviewed_at = (
                    date.fromisoformat(raw_date) if raw_date else None
                )
            except ValueError:
                return JsonResponse(
                    {"ok": False, "error": "Fecha anterior no válida."},
                    status=400,
                )
            person.contract_reviewed_by = (
                CompanyUser.objects.filter(
                    pk=int(raw_by), company=request.user.company_user.company,
                ).first() if str(raw_by).isdigit() else None
            )
        elif action == "clear":
            person.contract_reviewed_at = None
            person.contract_reviewed_by = None
        else:
            return JsonResponse(
                {"ok": False, "error": "Acción no válida."}, status=400,
            )
        person.save(update_fields=[
            "contract_reviewed_at", "contract_reviewed_by", "updated_at",
        ])
        return JsonResponse({"ok": True, **previous})


def _contract_review_info(person):
    """
    "Reviewed on ... by ..." line for the contract row, or "".

    ---

    Línea "Revisado el ... por ..." para la fila del contrato, con o
    sin aviso activo -- para poder anular una revisión hecha sin querer
    aunque el aviso ya no se vea.
    """
    reviewed = person.contract_reviewed_at
    if not reviewed:
        return ""
    reviewer = person.contract_reviewed_by
    return "Revisado el %s%s" % (
        reviewed.strftime("%d/%m/%Y"),
        " por %s" % (
            reviewer.user.get_full_name() or reviewer.user.username
        ) if reviewer and reviewer.user_id else "",
    )


def _attach_contract_alerts(objects):
    """
    Contract alert of every active person of a listing, in one query.

    ---

    Aviso del contrato de cada activo de un listado, con una sola
    consulta (H30, S125). Pone `contract_alert` en cada objeto (None si
    no hay).

    S128: ya NO es independiente del requisito. Miguel Ángel: las
    insignias del listado "nos ciñamos única y exclusivamente a los
    requisitos [...] si no tiene requisito, no se muestra. Y si tiene
    el requisito y el requisito no está activo, tampoco". Solo sale
    para quien tiene un requisito ACTIVO que exige el contrato
    (CONTRATO, prórroga o modificación). La ficha sigue mostrándolo
    siempre (`_contract_alert`).
    """
    from document_explorer.employer_service import CONTRACT_TYPE_CODES

    requirement_ids = {
        obj.job_position_id for obj in objects
        if obj.is_active_employee is True and obj.job_position_id
    }
    contract_requirement_ids = set(JobPosition.objects.filter(
        pk__in=requirement_ids, is_active=True,
        required_document_types__code__in=CONTRACT_TYPE_CODES,
    ).values_list("pk", flat=True))
    active_ids = {
        obj.pk for obj in objects
        if obj.is_active_employee is True
        and obj.job_position_id in contract_requirement_ids
    }
    latest_by_person = {}
    for entry in DocumentIndexEntry.objects.filter(
        entry_kind=DocumentIndexEntry.KIND_FILE,
        domain_content_type=ContentType.objects.get_for_model(PersonIdentity),
        domain_object_id__in=active_ids,
        document_type__code__in=CONTRACT_TYPE_CODES,
        is_obsolete=False, deleted_at__isnull=True, purged_at__isnull=True,
    ).order_by(
        "domain_object_id", "-issue_date", "-period_start_date",
        "-indexed_at", "-pk",
    ):
        latest_by_person.setdefault(entry.domain_object_id, entry)
    for obj in objects:
        obj.contract_alert = (
            _contract_alert_for(obj, latest_by_person.get(obj.pk))
            if obj.pk in active_ids else None
        )
    return objects


def _keep_latest_laboral_per_type(current, obsolete):
    """
    Only the current document of each cumulative LABORAL type stays in
    the person detail page; the rest goes to that type's history.

    ---

    H30 (S125). En Laboral, de cada tipo acumulable solo queda a la
    vista el vigente: el de fecha de emisión más reciente; un documento
    sin fecha nunca gana a uno con fecha; a igualdad, el último subido
    (y si ninguno tiene fecha, el último subido). El resto, con o sin
    fecha, pasa al historial de su tipo. Solo cambia dónde se pinta en
    la ficha de persona: en BD nada queda obsoleto y la subida sigue sin
    sustituir contratos/altas/IDC entre sí (S122).

    Miguel Ángel, S125, con captura real: "si metemos 50 altas, se van
    a ver las 50 altas, no mostramos la vigente [...] una persona que
    lleve 40 años [...] va a tener 80 altas, 80 contratos". Sustituye la
    excepción de S123 que dejaba a la vista los documentos sin fecha
    "para poder corregirlos": ahora se corrigen desde el historial.
    """
    from datetime import date

    def recency(entry):
        return (
            entry.issue_date is not None,
            entry.issue_date or date.min,
            entry.indexed_at.timestamp() if entry.indexed_at else 0,
            entry.pk,
        )

    latest = {}
    for entry in current:
        document_type = entry.document_type if entry.document_type_id else None
        if (
            document_type is None
            or not document_type.is_cumulative
            or document_type.family != DocumentTypeCatalog.FAMILY_LABORAL
        ):
            continue
        best = latest.get(document_type.pk)
        if best is None or recency(entry) > recency(best):
            latest[document_type.pk] = entry
    kept, moved = [], []
    for entry in current:
        document_type = entry.document_type if entry.document_type_id else None
        is_older = (
            document_type is not None
            and document_type.pk in latest
            and latest[document_type.pk] is not entry
        )
        (moved if is_older else kept).append(entry)
    return kept, obsolete + moved


def _person_employment_periods(person):
    """
    Employment periods of a person, ready to paint.

    ---

    H30 (S122). Periodos de contratación de una persona -- cada alta
    con su contrato emparejado a ±15 días o "falta contrato", la baja
    que lo cierra, y aparte las altas sin fecha y los contratos que no
    se emparejan con ninguna alta. Miguel Ángel: "tengo dos contratos,
    tres contratos, pero solamente está apareciendo el primero".
    """
    from document_explorer import employment_period_service as periods

    person_ct = ContentType.objects.get_for_model(PersonIdentity)
    by_code = {code: [] for code in periods.PERIOD_CODES}
    for entry in DocumentIndexEntry.objects.filter(
        bucket=BUCKET, domain_content_type=person_ct,
        domain_object_id=person.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
        # S125: un obsoleto (duplicado exacto, carpeta "obsoleto") no
        # es un periodo -- salía como "Alta sin fecha".
        is_obsolete=False,
        document_type__code__in=periods.PERIOD_CODES,
    ).select_related("document_type"):
        by_code[entry.document_type.code].append(entry)

    built, undated_altas = periods.build_periods(
        by_code[periods.ALTA_CODE],
        [
            entry for code in periods.CONTRACT_COVER_CODES
            for entry in by_code[code]
        ],
        by_code[periods.BAJA_CODE],
        [
            entry for code in periods.CONTRACT_SUBTYPE_CODES
            for entry in by_code[code]
        ],
    )
    for index, period in enumerate(built):
        if not period.has_contract:
            period.search_from, period.search_to = (
                periods.missing_contract_window(period)
            )
        # Incidente real S122 (captura de Miguel Ángel, su propia
        # ficha): un periodo sin baja registrada salía "En curso"
        # aunque hubiera un alta posterior -- imposible, la relación
        # anterior terminó. Solo el último periodo puede estar en
        # curso; el resto sin baja es "Sin baja registrada".
        period.is_open = (
            period.end_baja is None and index == len(built) - 1
        )
    missing_count = sum(1 for period in built if not period.has_contract)
    return {
        "periods": list(reversed(built)),
        "undated_altas": undated_altas,
        "unmatched_contracts": sorted(
            periods.unmatched_contracts(
                built, by_code[periods.CONTRACT_CODE],
            ),
            key=lambda entry: (entry.issue_date is None, entry.issue_date,
                               entry.pk),
        ),
        "unplaced_extensions": periods.unplaced_extensions(
            built, [
                entry for code in periods.CONTRACT_SUBTYPE_CODES
                for entry in by_code[code]
            ],
        ),
        "missing_count": missing_count,
        "has_warnings": bool(missing_count or undated_altas),
    }


def _person_lifting_accessories(person, company):
    """
    Lifting accessories delivered now to a person, ready to paint.
    ---
    Accesorios de elevación entregados ahora a una persona, con sus
    datos derivados (centro de gasto, fecha de entrega, caducidad,
    certificado) ya resueltos.
    """
    from document_explorer.lifting_accessory_service import (
        accessories_for_person,
    )
    from panel.views_lifting_accessories import _annotate

    return _annotate(accessories_for_person(person, company))


def _resolve_document_selection(request, pk):
    """
    H31 (S103). Resuelve la selección de documentos de UNA persona,
    compartido por las tres vistas de "usabilidad documental"
    (preview, PDF único, ZIP) -- una sola fuente de verdad para
    evitar que una de las tres divergiera de las otras dos si algún
    día cambia de dónde se lee la selección. Lee siempre de
    PanelNavigationState (screen_key='personal_ficha', clave anidada
    'document_selection' por persona), nunca de parámetros de query.

    Devuelve (person, entries) -- entries ya en el orden de
    presentación estándar (familia, tipo).
    """
    person = get_object_or_404(PersonIdentity, pk=pk)
    cu = request.user.company_user
    nav_state = PanelNavigationState.objects.filter(
        company_user=cu, screen_key="personal_ficha",
    ).first()
    state = (
        nav_state.state
        if nav_state and isinstance(nav_state.state, dict) else {}
    )
    document_selection = (
        state.get("document_selection")
        if isinstance(state.get("document_selection"), dict) else {}
    )
    selected_ids = document_selection.get(str(pk)) or []
    if not isinstance(selected_ids, list):
        selected_ids = []

    ct = ContentType.objects.get_for_model(PersonIdentity)
    entries = DocumentIndexEntry.objects.filter(
        pk__in=selected_ids, bucket=BUCKET,
        domain_content_type=ct, domain_object_id=person.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).select_related("document_type").order_by(
        "document_type__family", "document_type__label",
    )
    return person, entries


class PersonalDocumentSelectionPreviewView(CompanyUserRequiredMixin, View):
    """
    H31 (S103). GET: fragmento de vista previa de la selección de
    documentos de una persona, primer paso de la usabilidad
    documental (checkboxes -> preview -> dossier/adjunto). Lee
    siempre de PanelNavigationState (screen_key='personal_ficha',
    clave anidada 'document_selection' por persona -- ver
    PersonalDetailView y panel/views_navigation_state.py), nunca de
    parámetros de query: es la misma fuente de verdad que pinta los
    checkboxes en la ficha, para que la vista previa nunca pueda
    divergir de lo marcado (p. ej. entre dos pestañas del navegador
    sobre la misma ficha).
    """

    def get(self, request, pk):
        person, entries = _resolve_document_selection(request, pk)
        return render(
            request,
            "panel/documentation_h30/"
            "_personal_document_selection_preview.html",
            {"person": person, "entries": entries},
        )


class DossierBuildError(Exception):
    """
    H31 (S104). Raised by the dossier byte-building cores
    (_build_dossier_pdf_bytes/_build_dossier_zip_bytes) when no
    document can be included -- never an HttpResponse, so both the
    direct-download views and the new email-sending flow decide for
    themselves how to surface the failure (a 400 response for direct
    download, one more entry in a batch error list when sending by
    email), same pattern as NotificationEmlError below.
    ---
    H31 (S104). Lanzada por los nucleos de construccion de bytes del
    dossier (_build_dossier_pdf_bytes/_build_dossier_zip_bytes) cuando
    no se puede incluir ningun documento -- nunca un HttpResponse, asi
    ambos flujos (descarga directa, envio por correo nuevo) deciden
    por si mismos como mostrar el fallo (una respuesta 400 para
    descarga directa, una entrada mas en la lista de errores del lote
    al enviar por correo), mismo patron que NotificationEmlError mas
    abajo.
    """


def _build_epi_section_page(epi_deliveries):
    """
    H31/H36 (S109). Construye la página de la sección de EPIs del
    dossier con el mismo mecanismo que la portada/índice
    (`build_index_page`) -- una fila por entrega real
    (`EpiDelivery`), nunca una fila por tipo de EPI marcado en la
    plantilla (un EPI puede tener varias entregas reales a la misma
    persona, p. ej. un chaleco sustituido).

    SIN FIRMA TODAVÍA -- nota de pie de página explícita, para que
    nadie confunda esta sección con una acreditación firmada de
    verdad hasta que el proveedor de firma electrónica esté
    integrado (decisión explícita de Miguel Ángel, S109: "tenemos
    que ir buscando la opción de integrar con un proveedor
    homologado" -- ver comparativa Docuten/Signaturit/Viafirma de
    esa misma sesión).
    """
    header_lines = [
        ("ENTREGAS DE EPI INCLUIDAS EN ESTE DOSSIER", 14, True),
    ]
    item_lines = [
        f"{d.epi.label} -- entregado {d.delivery_date}"
        for d in epi_deliveries
    ]
    footer_note = (
        "Esta sección NO lleva firma electrónica todavía -- "
        "integración con un proveedor de firma homologado (eIDAS) "
        "pendiente de elegir. No usar como acreditación de entrega "
        "ante terceros hasta que se complete esa integración."
    )
    return build_index_page(header_lines, item_lines, footer_note)


def _dossier_subject_texts(subject):
    """
    Cover lines and filename token of a dossier for a person or machine.
    ---
    H30 (S119), punto 6: líneas de portada y token de nombre de archivo
    del dossier -- PersonIdentity igual que siempre (nombre, DNI,
    empresa); MachineAsset con código, marca/modelo y matrícula.
    """
    if isinstance(subject, MachineAsset):
        title = "%s -- %s" % (subject.code, subject.brand_model or "")
        plate = "Matrícula: %s" % (subject.plate or "sin matrícula")
        lines = [(title, 13, False), (plate, 11, False)]
        return lines, naming_service._sanitize_token(subject.code)
    person_line = (
        f"{subject.first_surname} {subject.second_surname}, "
        f"{subject.given_name} ({subject.dni})"
    )
    lines = [
        (person_line, 13, False),
        (subject.employer_legal_name or "Sin empresa asignada", 11, False),
    ]
    token = naming_service.build_person_folder_name(
        subject.first_surname, subject.second_surname, subject.given_name,
    )
    return lines, token


def _build_dossier_pdf_bytes(person, entries, epi_deliveries=None):
    """
    H31 (S104). Extracted from _build_dossier_pdf_response (S103) so
    the raw PDF bytes can also be attached to an .eml, not only served
    as a direct HttpResponse download. Returns (pdf_bytes, filename).
    Raises DossierBuildError when no entry has a supported format.

    H31/H36 (S109, REDEFINIDO EN S113): `epi_deliveries` YA NO genera
    una página sintética propia. Miguel Ángel, verbatim: "ahora no
    generamos el documento de entrega, sino que entregamos el PDF
    correspondiente a las entregas últimas de cada EPI. El documento
    se generará en otra interfaz, la que se ocupe de las firmas con
    Docuten." Cada entrega resuelve su `source_entry` (el documento
    real de esa entrega) y se mezcla en el dosier exactamente igual
    que cualquier otro documento de `entries` -- misma descarga,
    misma conversión, mismo criterio de formato no soportado.
    `_build_epi_section_page` queda sin uso en esta función (se
    conserva por si otro llamador la necesita) -- generar un
    documento de acreditación de entrega es responsabilidad de la
    futura interfaz de firma con Docuten, no de este dosier.
    ---
    H31 (S104). Extraido de _build_dossier_pdf_response (S103) para
    que los bytes del PDF tambien puedan adjuntarse a un .eml, no solo
    servirse como descarga HttpResponse directa. Devuelve
    (pdf_bytes, filename). Lanza DossierBuildError cuando ningun
    documento tiene un formato soportado.
    """
    entries = list(entries)
    entry_ids = {entry.pk for entry in entries}
    epi_entries = [
        d.source_entry for d in (epi_deliveries or [])
        if d.source_entry_id and d.source_entry_id not in entry_ids
    ]
    all_entries = entries + epi_entries

    included_pdfs = []
    included_lines = []
    skipped_lines = []
    for entry in all_entries:
        extension = entry.name.rsplit(".", 1)[-1] if "." in entry.name else ""
        label = (
            entry.document_type.label if entry.document_type_id else entry.name
        )
        # S147: una nómina confidencial nunca va en el dossier.
        if entry.is_confidential:
            skipped_lines.append("%s -- confidencial" % label)
            continue
        family = (
            entry.document_type.get_person_family_display()
            if entry.document_type_id else "—"
        )
        data = download_bytes(entry.bucket, entry.blob_name)
        pdf_bytes = convert_to_pdf_bytes(data, extension)
        if pdf_bytes is None:
            skipped_lines.append(
                f"{label} ({family}) -- formato .{extension or '?'} "
                "no soportado",
            )
            continue
        included_pdfs.append(pdf_bytes)
        caducidad = (
            f"vigente {entry.expiry_date}"
            if entry.expiry_date
            else (
                f"emisión {entry.issue_date}"
                if entry.issue_date
                else "sin fecha"
            )
        )
        included_lines.append(f"{label} -- {family} -- {caducidad}")

    if not included_pdfs:
        raise DossierBuildError(
            "Ningún documento tiene un formato soportado para el PDF "
            "único (usa la descarga en ZIP para estos archivos).",
        )

    # S119, punto 6: `person` puede ser también una MachineAsset.
    subject_lines, person_token = _dossier_subject_texts(person)
    header_lines = [
        ("DOSSIER DE DOCUMENTACIÓN", 18, True),
        *subject_lines,
        (f"Generado: {timezone.localdate().isoformat()}", 10, False),
        (f"Documentos incluidos: {len(included_lines)}", 11, True),
    ]
    footer_note = (
        "No incluidos en este PDF (formato no soportado -- "
        "descárgalos en ZIP): " + "; ".join(skipped_lines)
        if skipped_lines else None
    )
    cover_bytes = build_index_page(header_lines, included_lines, footer_note)

    pages = [cover_bytes]
    pages.extend(included_pdfs)

    try:
        merged_bytes = merge_pdfs(pages)
    except EmptyDocumentListError as exc:
        raise DossierBuildError(str(exc)) from exc

    filename = f"Dossier_{person_token}_{timezone.localdate().isoformat()}.pdf"
    return merged_bytes, filename


def _build_dossier_pdf_response(person, entries, epi_deliveries=None):
    """
    H31 (S103, refactorizado S104). Genera la respuesta HTTP del
    dossier en PDF único a partir de un `person` y un queryset/lista
    de `entries` ya resueltos -- compartido por
    PersonalDocumentSelectionPdfView (a partir de la selección de
    casilleros) y PersonalDossierTemplateApplyView (a partir de una
    plantilla guardada, resolviendo el vigente de cada tipo en este
    mismo instante). Nunca se llama con `entries` ya vacío -- el
    llamador decide qué mensaje de error mostrar si no hay nada que
    ofrecer. Delega la construcción real de bytes en
    _build_dossier_pdf_bytes (S104), compartida también con el envío
    por correo.
    """
    try:
        pdf_bytes, filename = _build_dossier_pdf_bytes(
            person, entries, epi_deliveries=epi_deliveries,
        )
    except DossierBuildError as exc:
        return HttpResponse(str(exc), status=400)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _build_dossier_zip_bytes(person, entries, epi_deliveries=None):
    """
    H31 (S104). Extracted from _build_dossier_zip_response (S103) so
    the raw ZIP bytes can also be attached to an .eml, not only served
    as a direct HttpResponse download. Returns (zip_bytes, filename).

    H31/H36 (S109, REDEFINIDO EN S113): `epi_deliveries` ya NO añade un
    PDF sintético de resumen -- mismo criterio y misma cita de Miguel
    Ángel que `_build_dossier_pdf_bytes`. El documento real
    (`source_entry`) de cada entrega se mezcla con `entries` y viaja
    dentro del ZIP en la carpeta de su propia familia documental,
    exactamente igual que cualquier otro archivo -- nunca en una
    carpeta aparte "entregas-epi/" con un resumen inventado.
    ---
    H31 (S104). Extraido de _build_dossier_zip_response (S103) para
    que los bytes del ZIP tambien puedan adjuntarse a un .eml, no solo
    servirse como descarga HttpResponse directa. Devuelve
    (zip_bytes, filename).
    """
    import io
    import zipfile

    entries = list(entries)
    entry_ids = {entry.pk for entry in entries}
    epi_entries = [
        d.source_entry for d in (epi_deliveries or [])
        if d.source_entry_id and d.source_entry_id not in entry_ids
    ]
    all_entries = entries + epi_entries

    zip_buffer = io.BytesIO()
    used_names = set()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in all_entries:
            # S147: una nómina confidencial nunca va en el dossier.
            if entry.is_confidential:
                continue
            family_folder = (
                slugify(entry.document_type.get_person_family_display())
                if entry.document_type_id else "sin-familia"
            )
            # H31 (S103), corregido tras revisión de Miguel Ángel sobre
            # el ZIP real descargado: el nombre del archivo dentro del
            # ZIP es el nombre CANÓNICO real del documento
            # (entry.name -- ya construido por
            # naming_service.build_filename_personal en el momento de
            # la subida, ver subject_upload_service.py), NUNCA uno
            # inventado a partir de la etiqueta del tipo documental
            # (versión anterior: "dni.pdf" en vez del nombre canónico
            # real con apellidos/tipo/fecha).
            arcname = f"{family_folder}/{entry.name}"
            if "." in entry.name:
                base_name, extension = entry.name.rsplit(".", 1)
            else:
                base_name, extension = entry.name, ""
            suffix = 2
            while arcname in used_names:
                arcname = (
                    f"{family_folder}/{base_name}_{suffix}.{extension}"
                    if extension else f"{family_folder}/{base_name}_{suffix}"
                )
                suffix += 1
            used_names.add(arcname)
            data = download_bytes(entry.bucket, entry.blob_name)
            zf.writestr(arcname, data)

    _lines, person_token = _dossier_subject_texts(person)
    filename = f"Dossier_{person_token}_{timezone.localdate().isoformat()}.zip"
    return zip_buffer.getvalue(), filename


def _build_dossier_zip_response(person, entries, epi_deliveries=None):
    """
    H31 (S103, refactorizado S104). Genera la respuesta HTTP del
    dossier en ZIP a partir de un `person` y un queryset/lista de
    `entries` ya resueltos -- compartido por
    PersonalDocumentSelectionZipView y
    PersonalDossierTemplateApplyView, mismo criterio que
    `_build_dossier_pdf_response`. Delega la construcción real de
    bytes en _build_dossier_zip_bytes (S104), compartida también con
    el envío por correo.
    """
    zip_bytes, filename = _build_dossier_zip_bytes(
        person, entries, epi_deliveries=epi_deliveries,
    )
    response = HttpResponse(zip_bytes, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class PersonalDocumentSelectionPdfView(CompanyUserRequiredMixin, View):
    """
    H31 (S103). GET: genera el dossier de la selección como UN ÚNICO
    PDF (portada/índice + documentos), pensado para adjuntar a un
    correo -- palabras de Miguel Ángel al abrir H26: "la documentación
    normalmente se aglutina en un solo PDF para enviarla por correo".
    Cablea por fin `document_management.pdf_merge_service`
    (construido en H26 S022/S023, nunca llamado desde ninguna vista
    hasta ahora).

    Cada documento no-PDF se convierte a PDF si es una imagen
    rasterizada soportada (`convert_to_pdf_bytes`); un documento con
    un formato no soportado (Word, Excel...) se EXCLUYE del PDF
    fusionado y se anota expresamente en el índice bajo "No
    incluidos" -- nunca se descarta en silencio, nunca se aborta todo
    el dossier por un solo archivo no soportado.
    """

    def get(self, request, pk):
        person, entries = _resolve_document_selection(request, pk)
        if not entries:
            return HttpResponse(
                "No hay ningún documento seleccionado para esta persona.",
                status=400,
            )
        return _build_dossier_pdf_response(person, entries)


class PersonalDocumentSelectionZipView(CompanyUserRequiredMixin, View):
    """
    H31 (S103). GET: genera el dossier de la selección como un ZIP con
    los archivos ORIGINALES (sin convertir nada), organizados en una
    carpeta por familia documental -- mismo patrón que las principales
    plataformas CAE del sector (Nalanda: seleccionas uno o varios
    trabajadores y descargas un ZIP con una carpeta por trabajador;
    Klear/Kizeo: descarga de una carpeta completa en ZIP conservando
    la estructura de categorías, investigado online en la sesión
    anterior). Pensado para "enviar a plataformas" externas que
    esperan los archivos tal cual, nunca un PDF fusionado.
    """

    def get(self, request, pk):
        person, entries = _resolve_document_selection(request, pk)
        if not entries:
            return HttpResponse(
                "No hay ningún documento seleccionado para esta persona.",
                status=400,
            )
        return _build_dossier_zip_response(person, entries)


class PersonalDossierEmailSendView(DocsUploadAccessMixin, View):
    """
    H31 (S104), punto 1 de la hoja de ruta. POST: genera y sirve para
    descarga un `.eml` real con el dossier de documentación de una
    persona adjunto (PDF único, o ZIP si el PDF no es viable para la
    selección -- ver `_build_dossier_notification_eml`), un cuerpo de
    mensaje editado por el propio supervisor en el editor básico del
    panel (`body_html`, obligatorio) y la firma real de quien envía
    (`request.user.company_user.email_signature_html`).

    Fuente de los documentos a adjuntar, en este orden de prioridad:
    1. `template_pk` en el POST -- dossier de una plantilla guardada
       (`_resolve_template_entries`, resuelve el documento VIGENTE de
       cada tipo en este mismo instante, igual que
       `PersonalDossierTemplateApplyView`).
    2. Sin `template_pk` -- la selección actual de casilleros
       (`_resolve_document_selection`, misma fuente que las vistas de
       PDF/ZIP directo).

    Mismo criterio que `PersonalNotificationSendView`: no hay envío
    SMTP real desde el servidor (sin EMAIL_BACKEND configurado). El
    `.eml` se descarga y el supervisor lo abre/reenvía desde su propio
    Outlook -- pendiente de confirmación visual real con Outlook antes
    de dar este punto por cerrado (ver hoja de ruta H31-S104).
    """

    def post(self, request, pk):
        person = get_object_or_404(PersonIdentity, pk=pk)

        template_pk = request.POST.get("template_pk", "").strip()
        epi_deliveries = None
        if template_pk:
            template = get_object_or_404(
                PersonalDossierTemplate, pk=template_pk,
            )
            entries = _resolve_template_entries(person, template)
            epi_deliveries = _resolve_template_epi_deliveries(person, template)
        else:
            _person, entries = _resolve_document_selection(request, pk)

        if not entries and not epi_deliveries:
            return HttpResponse(
                "No hay ningún documento que incluir en el dossier "
                "(ni selección de casilleros ni plantilla con "
                "documentos vigentes).", status=400,
            )

        # S130: cuerpo opcional -- vacío usa el texto por defecto.
        body_html = request.POST.get("body_html", "").strip()

        try:
            eml_bytes, filename = _build_dossier_notification_eml(
                person, entries, body_html, request.user.company_user,
                epi_deliveries=epi_deliveries,
            )
        except NotificationEmlError as exc:
            return HttpResponse(str(exc), status=400)

        response = HttpResponse(eml_bytes, content_type="message/rfc822")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


def _resolve_template_entries(person, template):
    """
    H31 (S103). Resuelve, EN EL MOMENTO de aplicar una plantilla, el
    documento VIGENTE de cada tipo guardado en ella -- nunca una fila
    fija de DocumentIndexEntry congelada desde que se creó la
    plantilla. Reutiliza `_split_current_obsolete()`, la misma fuente
    de verdad que ya usa `PersonalDetailView` para pintar la ficha.
    Un tipo cuyo documento ya no existe (borrado) simplemente no
    aparece -- el llamador decide qué hacer si la lista sale vacía.
    """
    ct = ContentType.objects.get_for_model(PersonIdentity)
    type_ids = list(template.document_types.values_list("pk", flat=True))
    all_entries = DocumentIndexEntry.objects.filter(
        bucket=BUCKET, domain_content_type=ct, domain_object_id=person.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
        document_type_id__in=type_ids,
    ).select_related("document_type")
    current, _obsolete = _split_current_obsolete(
        list(all_entries), get_required_type_ids(person),
    )
    current.sort(key=lambda e: (e.document_type.family, e.document_type.label))
    return current


def _resolve_template_epi_deliveries(person, template):
    """
    H31/H36 (S109, redefinido S113). Resuelve, EN EL MOMENTO de aplicar
    una plantilla, la entrega MÁS RECIENTE de cada EPI marcado en
    `template.epi_items` para la persona concreta -- mismo criterio de
    "resolver en el momento de aplicar, nunca fila fija" que
    `_resolve_template_entries`.

    CORREGIDO EN S113 (decisión explícita de Miguel Ángel): antes
    devolvía TODAS las entregas reales; ahora solo la última de cada
    EPI, porque el documento real de esa última entrega es lo que se
    adjunta al dosier (ver `_build_dossier_pdf_bytes`/
    `_build_dossier_zip_bytes`) -- adjuntar el histórico completo
    duplicaría documentos en el dosier sin aportar nada nuevo. Un EPI
    marcado sin ninguna entrega real a esa persona simplemente no
    aporta filas -- el llamador decide qué hacer si la lista sale
    vacía (nunca bloquea el resto del dossier).

    Devuelve una lista de `EpiDelivery` (una por EPI, la más
    reciente), con `source_entry` ya resuelto (`select_related`) para
    no disparar una consulta por entrega al mezclar sus documentos
    reales en el dosier.
    """
    epi_ids = list(template.epi_items.values_list("pk", flat=True))
    if not epi_ids:
        return []
    deliveries = EpiDelivery.objects.filter(
        person=person, epi_id__in=epi_ids,
    ).select_related("epi", "source_entry").order_by("-delivery_date")
    latest_by_epi = {}
    for delivery in deliveries:
        if delivery.epi_id not in latest_by_epi:
            latest_by_epi[delivery.epi_id] = delivery
    return list(latest_by_epi.values())


class PersonalDossierTemplateListView(CompanyUserRequiredMixin, View):
    """
    H31 (S103). GET: fragmento del "gestor de plantillas" -- lista las
    plantillas de TODA LA EMPRESA (compartidas por cualquier
    supervisor/administrador, corregido tras el diseño inicial que las
    ataba a una sola persona). Se pide siempre desde la ficha de una
    persona concreta (`pk`) para que "Descargar" sepa sobre quién
    aplicar cada plantilla.

    H35 (S105): solo expone ya "Descargar" -- crear/editar/duplicar/
    borrar se trasladó a `DossierTemplateManageView`, su propia
    página, porque un dosier es una tarea multi-trabajador y no tenía
    sentido gestionarla desde la ficha de uno solo.
    """

    def get(self, request, pk):
        person = get_object_or_404(PersonIdentity, pk=pk)
        company = request.user.company_user.company
        templates = company.dossier_templates.filter(
            scope=PersonalDossierTemplate.SCOPE_PERSONAL,
        ).prefetch_related(
            "document_types",
        ).order_by("created_at")
        return render(
            request,
            "panel/documentation_h30/_personal_dossier_template_list.html",
            {"person": person, "templates": templates},
        )


# H35 (S105). Paleta fija, en el mismo orden que DocumentTypeCatalog.
# FAMILY_CHOICES -- estable entre sesiones y entre cargas de página
# (nunca recalculada por orden de aparición real, que variaria si se
# anaden/quitan tipos de una familia). Un color por familia, elegidos
# para que se distingan bien entre si sin depender de que el usuario
# tenga buena vision del color (tonos claramente distintos, no solo
# matices).
_DOSSIER_FAMILY_COLORS = {
    DocumentTypeCatalog.FAMILY_CIRCULACION: "#e3f2fd",
    DocumentTypeCatalog.FAMILY_TECNICA_SEGURIDAD: "#fff3e0",
    DocumentTypeCatalog.FAMILY_SEGUROS: "#e8f5e9",
    DocumentTypeCatalog.FAMILY_FINANCIERO: "#f3e5f5",
    DocumentTypeCatalog.FAMILY_BAJAS_MAQUINA: "#fbe9e7",
    DocumentTypeCatalog.FAMILY_ADMINISTRATIVO: "#e0f7fa",
    DocumentTypeCatalog.FAMILY_IDENTIDAD_PERSONAL: "#fff9c4",
    DocumentTypeCatalog.FAMILY_LABORAL: "#ede7f6",
    DocumentTypeCatalog.FAMILY_SALUD_BAJAS_PERSONA: "#ffebee",
    DocumentTypeCatalog.FAMILY_PRL_FORMACION: "#e8eaf6",
    DocumentTypeCatalog.FAMILY_OTROS_DOCUMENTOS: "#eeeeee",
    DocumentTypeCatalog.FAMILY_MEDIA: "#f1f8e9",
}


class DossierTemplateManageView(CompanyUserRequiredMixin, View):
    """
    H35 (S105). GET: página completa (nunca modal/acordeón) de
    gestión de plantillas de dosier -- Miguel Ángel, verbatim: "he
    cometido el error de incluirlo ahí [la ficha de una persona]...
    los dosieres son tareas que se realizan con varios trabajadores
    [...] quiero una lista con todos los documentos para que se forme
    la plantilla eligiendo de un casillero [...] todo el listado de
    documentos [...] agrupados por familia, eso sí, agrupados por
    familia, no en acordeón [...] todo visible agrupado por familia
    con colores diferentes".

    Sustituye por completo al gestor modal que vivía dentro de la
    ficha de personal para CREAR/EDITAR/DUPLICAR/BORRAR -- la ficha
    (`PersonalDossierTemplateListView`) sigue existiendo solo para
    "Descargar" una plantilla ya creada, aplicada a esa persona en
    concreto.

    Todos los tipos documentales de dominio PERSONAL/BOTH activos se
    muestran siempre, agrupados por familia y coloreados
    (`_DOSSIER_FAMILY_COLORS`) -- a diferencia del gestor antiguo, que
    solo ofrecía marcar los tipos que la persona cuya ficha estuviera
    abierta en ese momento ya tuviera subidos.
    """

    def get(self, request):
        company = request.user.company_user.company
        # H30 (S119), punto 6: ámbito del gestor -- Personal (por
        # defecto, como hasta ahora) o Maquinaria (?ambito=MAQUINARIA).
        ambito = request.GET.get("ambito", "").upper()
        is_machine_scope = ambito == "MAQUINARIA"
        scope = (
            PersonalDossierTemplate.SCOPE_MACHINE if is_machine_scope
            else PersonalDossierTemplate.SCOPE_PERSONAL
        )
        templates = company.dossier_templates.filter(
            scope=scope,
        ).prefetch_related(
            "document_types", "epi_items",
        ).order_by("name")

        doc_types = DocumentTypeCatalog.objects.filter(
            is_active=True,
            domain__in=(
                ["MACHINE", "BOTH"] if is_machine_scope
                else ["PERSONAL", "BOTH"]
            ),
        ).order_by("family", "label")
        # S125: con ámbito Personal, Circulación es Conducción.
        sections = _type_family_sections(
            doc_types,
            lambda code: DocumentTypeCatalog.family_label(
                code, for_person=not is_machine_scope,
            ),
        )
        # H31/H36 (S109): EPIs como sección propia (entregas reales,
        # familia de EpiItemCatalog, nunca mezclada con la de tipos).
        # S119: los EPIs son solo de Personal.
        item_kinds = "type"
        if not is_machine_scope:
            epi_items = EpiItemCatalog.objects.filter(
                is_active=True,
            ).order_by("family", "label")
            epi_groups = {}
            for epi in epi_items:
                epi_groups.setdefault(epi.family, []).append(epi)
            for family, items in epi_groups.items():
                sections.append({
                    "title": "EPIs -- %s" % family,
                    "color": "",
                    "kind": "epi",
                    "inline": False,
                    "note": (
                        "Entregas reales registradas en el panel, sin "
                        "bloque de firma todavía (pendiente de un "
                        "proveedor de firma eIDAS)."
                    ),
                    "items": [
                        {"pk": epi.pk, "label": "EPI: %s" % epi.label,
                         "text": epi.label, "title": ""}
                        for epi in items
                    ],
                })
            item_kinds = "type,epi"

        rows = [
            {
                "pk": template.pk,
                "name": template.name,
                "active": True,
                "type_ids": _joined_pks(template.document_types.all()),
                "epi_ids": _joined_pks(template.epi_items.all()),
                "category_ids": "",
            }
            for template in templates
        ]
        nav_key = "dossier_templates_%s" % scope
        picker = {
            "dom_id": "tp-dosieres",
            "create_url": reverse("panel:dossier_template_create"),
            "update_url": reverse(
                "panel:dossier_template_update", args=[0],
            ).replace("/0/", "/{pk}/"),
            "delete_url": reverse("panel:dossier_templates_bulk_delete"),
            "active_url": "",
            "scope": scope,
            "nav_key": nav_key,
            "initial_pk": _picker_initial_pk(request, nav_key),
            "item_kinds": item_kinds,
            "require_name": False,
            "require_items": True,
            "can_toggle_active": False,
            "noun_new": "Nueva plantilla",
            "name_placeholder": "Dossier N (automático si se deja en blanco)",
            "list_title": "Plantillas de dosier",
            "empty_text": "Sin plantillas guardadas todavía.",
            "help_text": (
                "Pulsa una plantilla para ver y editar sus documentos. "
                "Guarda con el mismo nombre para editarla; con otro "
                "nombre se crea una nueva y la original no se toca. Al "
                "aplicarla a un trabajador siempre se usa el documento "
                "vigente de cada tipo, y el formato (PDF o ZIP) se "
                "pregunta en ese momento."
            ),
            "delete_note": (
                "Solo se borra la plantilla, nunca los documentos."
            ),
            "saved_event": "",
            "deleted_event": "",
            "changed_event": "",
            "rows": rows,
            "sections": sections,
        }
        return render(request, "panel/dossier_templates_h35/manage.html", {
            "picker": picker,
            "is_machine_scope": is_machine_scope,
        })


def _joined_pks(objects):
    """
    Comma-separated pks, for the picker's data- attributes.
    ---
    Pks separados por comas, para los atributos data- del gestor común
    (panel/_doc_type_picker.html, S128).
    """
    return ",".join(str(obj.pk) for obj in objects)


def _type_family_sections(doc_types, label_for):
    """
    Group catalog types by family, in FAMILY_CHOICES order, as picker
    sections ("Sin familia" last).
    ---
    H30 (S128). Agrupa los tipos del catálogo por familia, en el orden
    de FAMILY_CHOICES ("Sin familia" al final), con el color de cada
    familia -- secciones del gestor común de Requisitos y Dosieres.
    `label_for(code)` da el rótulo de la familia (cada pantalla tiene
    el suyo, ver S125).
    """
    by_family = {}
    for dt in doc_types:
        by_family.setdefault(dt.family or "", []).append(dt)
    known = [code for code, _ in DocumentTypeCatalog.FAMILY_CHOICES]
    codes = [code for code in known if code in by_family]
    # Una familia fuera de FAMILY_CHOICES nunca esconde sus tipos.
    codes += sorted(
        code for code in by_family if code and code not in known
    )
    if "" in by_family:
        codes.append("")
    return [
        {
            "title": label_for(code) if code else "Sin familia",
            "color": _DOSSIER_FAMILY_COLORS.get(code, "#f5f5f5"),
            "kind": "type",
            "inline": False,
            "note": "",
            "items": [
                {"pk": dt.pk, "label": dt.label, "text": dt.label,
                 "title": ""}
                for dt in by_family[code]
            ],
        }
        for code in codes
    ]


def _picker_initial_pk(request, nav_key):
    """
    Last row the user loaded in this picker, from PanelNavigationState.
    ---
    H30 (S128). Última fila cargada por este usuario en el gestor
    (directriz 4.15): al volver a la pestaña sigue en la misma
    plantilla o requisito. La guarda el propio JS en `loaded_pk`.
    """
    nav_state = PanelNavigationState.objects.filter(
        company_user=request.user.company_user, screen_key=nav_key,
    ).first()
    if nav_state is None or not isinstance(nav_state.state, dict):
        return None
    return nav_state.state.get("loaded_pk")


class DossierTemplateSaveView(CompanyUserRequiredMixin, View):
    """
    H35 (S105). POST: crea una plantilla nueva (sin `template_pk`) o
    edita una existente (con `template_pk`) -- nombre y la lista
    completa de tipos documentales marcados en
    `DossierTemplateManageView`. El formato de salida (PDF/ZIP) ya no
    se guarda aquí -- se pregunta siempre al aplicar la plantilla, ver
    `PersonalDossierTemplateApplyView` (S106).
    """

    def post(self, request, template_pk=None):
        company = request.user.company_user.company
        if template_pk:
            template = get_object_or_404(
                PersonalDossierTemplate, pk=template_pk, company=company,
            )
        else:
            scope = request.POST.get("scope", "")
            template = PersonalDossierTemplate(
                company=company,
                created_by=getattr(request.user, "company_user", None),
                # S119, punto 6: ámbito elegido en el gestor.
                scope=(
                    scope
                    if scope in dict(PersonalDossierTemplate.SCOPE_CHOICES)
                    else PersonalDossierTemplate.SCOPE_PERSONAL
                ),
            )

        name = request.POST.get("name", "").strip()
        if not name:
            if template.pk:
                name = template.name
            else:
                n = company.dossier_templates.count() + 1
                name = "Dossier %d" % n

        type_ids = request.POST.getlist("document_type_ids")
        epi_item_ids = request.POST.getlist("epi_item_ids")
        if not type_ids and not epi_item_ids:
            return JsonResponse(
                {
                    "ok": False,
                    "error": (
                        "Selecciona al menos un tipo documental o un EPI."
                    ),
                },
                status=400,
            )

        template.name = name
        template.save()
        template.document_types.set(type_ids)
        template.epi_items.set(epi_item_ids)

        return JsonResponse(
            {"ok": True, "id": template.pk, "name": template.name}
        )


class PersonalDossierTemplateApplyView(CompanyUserRequiredMixin, View):
    """
    H31 (S103). GET: aplica una plantilla de empresa SOBRE UNA
    PERSONA concreta (`pk`) -- resuelve el documento vigente de cada
    tipo de la plantilla EN ESTE INSTANTE para esa persona
    (`_resolve_template_entries`) y lo COMBINA con lo que esa misma
    persona tenga ahora mismo en su selección de casilleros -- Miguel
    Ángel: "documentos como el DNI o la tarjeta de conducción estén en
    plantillas y luego se añadan los documentos que son específicos de
    cada trabajador, como por ejemplo formación determinada en un
    área". Sin selección activa, se aplica solo la plantilla; sin
    plantilla resuelta pero con selección, se aplica solo la
    selección -- nunca un dossier vacío si hay algo que ofrecer por
    cualquiera de las dos vías.

    **S106**: el formato (`?format=PDF` o `?format=ZIP`) se pregunta
    SIEMPRE en la propia ficha antes de llegar aquí -- la plantilla ya
    no guarda un formato propio (ver `PersonalDossierTemplate`,
    corregido S106). Sin `format` válido, 400 explícito -- nunca se
    asume PDF por defecto.
    """

    def get(self, request, pk, template_pk):
        person = get_object_or_404(PersonIdentity, pk=pk)
        template = get_object_or_404(PersonalDossierTemplate, pk=template_pk)

        output_format = request.GET.get("format", "").strip().upper()
        if output_format not in (
            PersonalDossierTemplate.FORMAT_PDF,
            PersonalDossierTemplate.FORMAT_ZIP,
        ):
            return HttpResponse(
                "Falta indicar el formato (PDF o ZIP) para descargar "
                "esta plantilla.",
                status=400,
            )

        template_entries = _resolve_template_entries(person, template)
        epi_deliveries = _resolve_template_epi_deliveries(person, template)
        _person, selection_entries = _resolve_document_selection(request, pk)

        combined = list(template_entries)
        combined_pks = {e.pk for e in combined}
        for entry in selection_entries:
            if entry.pk not in combined_pks:
                combined.append(entry)
                combined_pks.add(entry.pk)

        if not combined and not epi_deliveries:
            return HttpResponse(
                "Ninguno de los tipos documentales de esta plantilla "
                "tiene hoy un documento vigente para esta persona, y "
                "no hay ningún documento adicional seleccionado.",
                status=400,
            )
        if output_format == PersonalDossierTemplate.FORMAT_ZIP:
            return _build_dossier_zip_response(
                person, combined, epi_deliveries=epi_deliveries,
            )
        return _build_dossier_pdf_response(
            person, combined, epi_deliveries=epi_deliveries,
        )


class DossierTemplateBulkDeleteView(CompanyUserRequiredMixin, View):
    """
    H30 (S128). POST `ids`: borra varias plantillas de dosier de la
    empresa (sin papelera -- es configuración, nunca un documento), tras
    el modal con cuenta atrás del gestor común. Sustituye al borrado de
    una en una (`PersonalDossierTemplateDeleteView`, que además no
    comprobaba la empresa) y a "Marcar como activa"
    (`PersonalDossierTemplateSetActiveView`), retirada a petición de
    Miguel Ángel.
    """

    def post(self, request):
        company = request.user.company_user.company
        ids = [i for i in request.POST.getlist("ids") if i.isdigit()]
        deleted, _detail = company.dossier_templates.filter(
            pk__in=ids,
        ).delete()
        return JsonResponse({"ok": True, "count": len(ids) if deleted else 0})


# ---------------------------------------------------------------------------
# H30 (S119), punto 6 -- selección y plantillas de dossier en la ficha de
# MÁQUINA, mismo mecanismo que Personal (S103-S106): selección guardada en
# PanelNavigationState (screen_key "machine_ficha"), dossier de la
# selección en PDF único o ZIP, y plantillas de empresa de ámbito
# Maquinaria que resuelven el vigente de cada tipo al aplicarlas.
# ---------------------------------------------------------------------------
MACHINE_FICHA_SCREEN_KEY = "machine_ficha"


def _machine_selected_ids(request, pk):
    """
    Selected document ids of one machine, from PanelNavigationState.
    ---
    Ids seleccionados de una máquina, leídos de PanelNavigationState --
    la misma fuente que pinta las casillas, nunca parámetros de query.
    """
    nav_state = PanelNavigationState.objects.filter(
        company_user=request.user.company_user,
        screen_key=MACHINE_FICHA_SCREEN_KEY,
    ).first()
    state = (
        nav_state.state
        if nav_state and isinstance(nav_state.state, dict) else {}
    )
    selection = state.get("document_selection")
    if not isinstance(selection, dict):
        return []
    selected = selection.get(str(pk)) or []
    if not isinstance(selected, list):
        return []
    # S125: solo lo que sigue vivo y vinculado (mismo filtro que la
    # vista previa), para que contador y casillas no mientan.
    return _alive_selected_ids(selected, MachineAsset, pk)


def _alive_selected_ids(selected_ids, subject_model, subject_pk):
    """
    Selected ids that still exist and belong to the subject.

    ---

    Ids seleccionados que siguen vivos (ni papelera ni purgados) y
    vinculados al sujeto -- el mismo filtro que aplica la vista previa
    de la selección. Conserva el orden de selección.
    """
    wanted = [
        int(value) for value in selected_ids if str(value).isdigit()
    ]
    alive = set(DocumentIndexEntry.objects.filter(
        pk__in=wanted, bucket=BUCKET,
        domain_content_type=ContentType.objects.get_for_model(subject_model),
        domain_object_id=subject_pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).values_list("pk", flat=True))
    return [pk for pk in wanted if pk in alive]


def _resolve_machine_document_selection(request, pk):
    """
    Return (machine, selected entries) in family/type order.
    ---
    Devuelve (máquina, documentos seleccionados) en orden de familia y
    tipo; solo documentos vivos de ESA máquina.
    """
    machine = get_object_or_404(MachineAsset, pk=pk)
    ct = ContentType.objects.get_for_model(MachineAsset)
    entries = DocumentIndexEntry.objects.filter(
        pk__in=_machine_selected_ids(request, pk), bucket=BUCKET,
        domain_content_type=ct, domain_object_id=machine.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).select_related("document_type").order_by(
        "document_type__family", "document_type__label",
    )
    return machine, entries


def _resolve_machine_template_entries(machine, template):
    """
    Current document of each template type for this machine, now.
    ---
    El vigente de cada tipo de la plantilla para esta máquina, resuelto
    en este instante con el mismo cálculo que la ficha.
    """
    ct = ContentType.objects.get_for_model(MachineAsset)
    type_ids = list(template.document_types.values_list("pk", flat=True))
    all_entries = DocumentIndexEntry.objects.filter(
        bucket=BUCKET, domain_content_type=ct, domain_object_id=machine.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
        document_type_id__in=type_ids,
    ).select_related("document_type")
    current, _obsolete = _split_current_obsolete(
        list(all_entries), get_required_type_ids(machine),
    )
    current.sort(key=lambda e: (e.document_type.family, e.document_type.label))
    return current


class MachineDocumentSelectionPreviewView(CompanyUserRequiredMixin, View):
    """
    GET: preview of a machine's document selection.
    ---
    GET: vista previa de la selección de documentos de una máquina.
    """

    def get(self, request, pk):
        machine, entries = _resolve_machine_document_selection(request, pk)
        return render(
            request,
            "panel/documentation_h30/_machine_document_selection_preview.html",
            {"machine": machine, "entries": entries},
        )


class MachineDocumentSelectionPdfView(CompanyUserRequiredMixin, View):
    """
    GET: dossier of the selection as a single PDF.
    ---
    GET: dossier de la selección en un único PDF (portada + índice +
    documentos), mismo constructor que Personal.
    """

    def get(self, request, pk):
        machine, entries = _resolve_machine_document_selection(request, pk)
        if not entries:
            return HttpResponse(
                "No hay ningún documento seleccionado para esta máquina.",
                status=400,
            )
        return _build_dossier_pdf_response(machine, entries)


class MachineDocumentSelectionZipView(CompanyUserRequiredMixin, View):
    """
    GET: dossier of the selection as a ZIP of the originals.
    ---
    GET: dossier de la selección en ZIP con los archivos originales,
    una carpeta por familia, mismo constructor que Personal.
    """

    def get(self, request, pk):
        machine, entries = _resolve_machine_document_selection(request, pk)
        if not entries:
            return HttpResponse(
                "No hay ningún documento seleccionado para esta máquina.",
                status=400,
            )
        return _build_dossier_zip_response(machine, entries)


# H31 (S136, sesión invasora). Estados de un documento en la ventana
# "Descargar documentación", en el orden en que se listan.
DOWNLOAD_STATE_ORDER = {"vigente": 0, "caducado": 1, "obsoleto": 2}
DOWNLOAD_STATE_LABELS = {
    "vigente": "Vigente", "caducado": "Caducado", "obsoleto": "Obsoleto",
}


def _document_download_families(subject, for_person):
    """
    Documents of a person or machine grouped by family, with state.

    ---

    H31 (S136). Todos los documentos vivos de la persona o máquina,
    agrupados por familia (en el orden del catálogo) y marcados como
    vigente, caducado (vigente con la caducidad ya pasada) u obsoleto,
    con el mismo cálculo que la ficha (`_split_current_obsolete` con el
    requisito de documentación del sujeto). Los que no tienen tipo van
    en su propia familia, "Sin tipo", como vigentes. Devuelve una lista
    de {"code", "label", "rows": [{"entry", "state", "state_label"}]}.
    """
    ct = ContentType.objects.get_for_model(subject)
    entries = list(DocumentIndexEntry.objects.filter(
        bucket=BUCKET, domain_content_type=ct, domain_object_id=subject.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).select_related("document_type"))
    typed = [entry for entry in entries if entry.document_type_id]
    current, obsolete = _split_current_obsolete(
        typed, get_required_type_ids(subject),
    )
    states = {}
    for entry in current:
        states[entry.pk] = (
            "caducado" if getattr(entry, "needs_attention", False)
            else "vigente"
        )
    for entry in obsolete:
        states[entry.pk] = "obsoleto"
    family_order = {
        code: index
        for index, (code, _label) in enumerate(
            DocumentTypeCatalog.FAMILY_CHOICES,
        )
    }
    families = {}
    for entry in entries:
        if entry.document_type_id:
            code = entry.document_type.family or ""
            label = DocumentTypeCatalog.family_label(
                code, for_person=for_person,
            )
        else:
            code, label = "SIN_TIPO", "Sin tipo"
        state = states.get(entry.pk, "vigente")
        families.setdefault(code, {"code": code, "label": label, "rows": []})
        families[code]["rows"].append({
            "entry": entry,
            "state": state,
            "state_label": DOWNLOAD_STATE_LABELS[state],
        })
    for family in families.values():
        family["rows"].sort(key=lambda row: (
            row["entry"].document_type.label
            if row["entry"].document_type_id else row["entry"].name,
            DOWNLOAD_STATE_ORDER[row["state"]],
            -(row["entry"].expiry_date or row["entry"].issue_date
              or date.min).toordinal(),
        ))
    return sorted(
        families.values(),
        key=lambda family: family_order.get(family["code"], len(family_order)),
    )


class DocumentDownloadPickerView(CompanyUserRequiredMixin, View):
    """
    GET: the "Descargar documentación" window of a person or machine.

    ---

    H31 (S136, sesión invasora). Miguel Ángel: "un botón que ponga
    descargar documentación, abrimos un modal con la documentación
    separada por familia, con marcajes de obsoletos, para que filtro,
    etcétera, para gestionar la descarga de documentación de un
    determinado trabajador o de una determinada máquina".

    Fragmento de la ventana (lo carga `panel/js/document_download_
    picker.js`). Las casillas son la misma "Selección de documentos"
    de la ficha (PanelNavigationState, clave `document_selection`), así
    que la descarga reutiliza las vistas de siempre: ZIP con los
    originales por familia y PDF único con índice. Los filtros de la
    ventana se guardan por usuario en la misma clave de pantalla
    (`download_picker`, directriz 4.15).
    """

    def get(self, request, pk, kind):
        if kind == "personal":
            subject = get_object_or_404(PersonIdentity, pk=pk)
            screen_key = "personal_ficha"
            zip_url = reverse(
                "panel:documentation_personal_document_selection_zip",
                args=[pk],
            )
            pdf_url = reverse(
                "panel:documentation_personal_document_selection_pdf",
                args=[pk],
            )
            title = "%s %s %s" % (
                subject.given_name, subject.first_surname,
                subject.second_surname,
            )
        else:
            subject = get_object_or_404(MachineAsset, pk=pk)
            screen_key = MACHINE_FICHA_SCREEN_KEY
            zip_url = reverse(
                "panel:documentation_machine_document_selection_zip",
                args=[pk],
            )
            pdf_url = reverse(
                "panel:documentation_machine_document_selection_pdf",
                args=[pk],
            )
            title = "%s — %s" % (subject.code, subject.brand_model)
        nav_state = PanelNavigationState.objects.filter(
            company_user=request.user.company_user, screen_key=screen_key,
        ).first()
        state = (
            nav_state.state
            if nav_state and isinstance(nav_state.state, dict) else {}
        )
        saved = state.get("download_picker")
        saved = saved if isinstance(saved, dict) else {}
        saved_states = saved.get("states")
        if not isinstance(saved_states, list):
            saved_states = ["vigente", "caducado"]
        families = _document_download_families(
            subject, for_person=(kind == "personal"),
        )
        url_name = (
            "panel:documentation_personal_download_trash"
            if kind == "personal"
            else "panel:documentation_machine_download_trash"
        )
        return render(
            request,
            "panel/documentation_h30/_document_download_picker.html",
            {
                "title": title,
                "families": families,
                "total": sum(len(family["rows"]) for family in families),
                "screen_key": screen_key,
                "subject_pk": pk,
                "zip_url": zip_url,
                "pdf_url": pdf_url,
                "saved_states": saved_states,
                "saved_family": str(saved.get("family") or ""),
                "saved_sort": str(saved.get("sort") or ""),
                "state_choices": list(DOWNLOAD_STATE_LABELS.items()),
                # S136: "Enviar a la papelera", mismos roles que el
                # borrado de un documento en la ficha.
                "can_trash": request.user.company_user.role in (
                    CompanyUser.ROLE_DOCS_SUPERVISOR,
                    CompanyUser.ROLE_ADMIN,
                    CompanyUser.ROLE_ADMIN_SUPERVISOR,
                ),
                "trash_url": reverse(url_name, args=[pk]),
            },
        )


class DocumentDownloadTrashView(DocsUploadAccessMixin, View):
    """
    POST: send documents of one person or machine to the trash.

    ---

    H31 (S136, sesión invasora). POST (`entry_ids`): manda a la
    papelera documentos de la persona o máquina desde la ventana
    "Descargar documentación". Miguel Ángel: "deberíamos de tener un
    botón para eliminar, porque algunos archivos habría que
    eliminarlos [...] para que no aparezca en la documentación" (fotos
    repetidas, el mismo permiso obsoleto varias veces).

    Mismo borrado que `DocumentDeleteView` de la ficha: solo
    `deleted_at`/`deleted_by`, nunca toca GCS (directriz 4.12); el
    final real sigue siendo el vaciado de la papelera por el
    administrador. Solo documentos vivos de ESE sujeto.
    """

    def post(self, request, pk, kind):
        model = PersonIdentity if kind == "personal" else MachineAsset
        subject = get_object_or_404(model, pk=pk)
        entry_ids = [
            value for value in request.POST.getlist("entry_ids")
            if value.isdigit()
        ]
        if not entry_ids:
            return JsonResponse(
                {"ok": False, "error": "No hay documentos marcados."},
                status=400,
            )
        entries = DocumentIndexEntry.objects.filter(
            pk__in=entry_ids, bucket=BUCKET,
            domain_content_type=ContentType.objects.get_for_model(model),
            domain_object_id=subject.pk,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
        )
        trashed = list(entries.values_list("pk", flat=True))
        entries.update(
            deleted_at=timezone.now(),
            deleted_by=request.user.company_user,
        )
        return JsonResponse({"ok": True, "trashed_ids": trashed})


class MachineDossierTemplateListView(CompanyUserRequiredMixin, View):
    """
    GET: company machine-scope dossier templates, from a machine file.
    ---
    GET: plantillas de dossier de ámbito Maquinaria de la empresa,
    pedidas desde la ficha de una máquina.
    """

    def get(self, request, pk):
        machine = get_object_or_404(MachineAsset, pk=pk)
        templates = request.user.company_user.company.dossier_templates.filter(
            scope=PersonalDossierTemplate.SCOPE_MACHINE,
        ).prefetch_related("document_types").order_by("created_at")
        return render(
            request,
            "panel/documentation_h30/_machine_dossier_template_list.html",
            {"machine": machine, "templates": templates},
        )


class MachineDossierTemplateApplyView(CompanyUserRequiredMixin, View):
    """
    GET: apply a machine template to one machine (PDF or ZIP).
    ---
    GET: aplica una plantilla de Maquinaria a una máquina -- el vigente
    de cada tipo en este instante, combinado con su selección actual;
    formato (?format=PDF|ZIP) siempre elegido, nunca asumido.
    """

    def get(self, request, pk, template_pk):
        machine = get_object_or_404(MachineAsset, pk=pk)
        template = get_object_or_404(
            PersonalDossierTemplate, pk=template_pk,
            company=request.user.company_user.company,
            scope=PersonalDossierTemplate.SCOPE_MACHINE,
        )
        output_format = request.GET.get("format", "").strip().upper()
        if output_format not in (
            PersonalDossierTemplate.FORMAT_PDF,
            PersonalDossierTemplate.FORMAT_ZIP,
        ):
            return HttpResponse(
                "Falta indicar el formato (PDF o ZIP) para descargar "
                "esta plantilla.",
                status=400,
            )
        combined = list(_resolve_machine_template_entries(machine, template))
        combined_pks = {entry.pk for entry in combined}
        _machine, selection = _resolve_machine_document_selection(request, pk)
        for entry in selection:
            if entry.pk not in combined_pks:
                combined.append(entry)
                combined_pks.add(entry.pk)
        if not combined:
            return HttpResponse(
                "Ninguno de los tipos de esta plantilla tiene hoy un "
                "documento vigente para esta máquina, y no hay ningún "
                "documento adicional seleccionado.",
                status=400,
            )
        if output_format == PersonalDossierTemplate.FORMAT_ZIP:
            return _build_dossier_zip_response(machine, combined)
        return _build_dossier_pdf_response(machine, combined)


class JobPositionManageView(CompanyUserRequiredMixin, View):
    """
    H31 (S109). GET: página de gestión de "Requisitos de
    documentación" -- misma mecánica que `DossierTemplateManageView`
    (tipos documentales agrupados por familia, marcados con
    casillero), pero para `JobPosition.required_document_types` en
    vez de `PersonalDossierTemplate.document_types`. Sin FK a Company
    -- el catálogo es de toda la plataforma, mismo criterio que
    `PersonGroupTemplate`. Sin concepto de "plantilla activa" -- un
    requisito no se "aplica" sobre nadie, solo se asigna desde la
    propia ficha (`PersonIdentity.job_position` o `MachineAsset.
    document_requirement`) o en lote desde el listado.

    AMPLIADO EN S119 -- CATÁLOGO ÚNICO, GLOBAL: el selector de tipos ya
    NO filtra por dominio (antes solo PERSONAL/BOTH) -- Miguel Ángel,
    verbatim: "los requisitos documentales no son ni para personas ni
    para máquinas [...] es un absurdo ahora acotar a personal o acotar
    a máquina. Eso se acota al crearlo y al asignarlo." Ofrece TODO el
    catálogo activo; qué tipos tienen sentido para un requisito
    concreto lo decide quien lo crea, nunca el código.
    """

    def get(self, request):
        positions = JobPosition.objects.prefetch_related(
            "required_document_types", "required_driving_categories",
        ).order_by("name")

        # S119: catálogo completo, sin filtro de dominio (ver
        # docstring de la clase).
        doc_types = DocumentTypeCatalog.objects.filter(
            is_active=True,
        ).order_by("family", "label")
        family_labels = dict(DocumentTypeCatalog.FAMILY_CHOICES)
        # H30 (S120). Clases concretas del permiso de conducción --
        # Miguel Ángel: "esto en realidad es una matriz". Con alguna
        # clase marcada, "Carnet de conducir" (si también se marca)
        # solo avisa si falta el carné, nunca por caducidad.
        sections = [{
            "title": "Permiso de conducción -- clases exigidas",
            "color": "",
            "kind": "category",
            "inline": True,
            "note": "",
            "items": [
                {"pk": cat.pk, "label": "Permiso %s" % cat.code,
                 "text": cat.code, "title": cat.label}
                for cat in DrivingLicenceCategory.objects.all()
            ],
        }] + _type_family_sections(
            doc_types, lambda code: family_labels.get(code, "Sin familia"),
        )

        rows = [
            {
                "pk": position.pk,
                "name": position.name,
                "active": position.is_active,
                "type_ids": _joined_pks(
                    position.required_document_types.all(),
                ),
                "epi_ids": "",
                "category_ids": _joined_pks(
                    position.required_driving_categories.all(),
                ),
            }
            for position in positions
        ]
        nav_key = "job_positions_manager"
        picker = {
            "dom_id": "tp-requisitos",
            "create_url": reverse("panel:job_position_create"),
            "update_url": reverse(
                "panel:job_position_update", args=[0],
            ).replace("/0/", "/{pk}/"),
            "delete_url": reverse("panel:job_positions_bulk_delete"),
            "active_url": reverse("panel:job_positions_bulk_active"),
            "scope": "",
            "nav_key": nav_key,
            "initial_pk": _picker_initial_pk(request, nav_key),
            "item_kinds": "category,type",
            "require_name": True,
            "require_items": False,
            "can_toggle_active": True,
            "noun_new": "Nuevo requisito",
            "name_placeholder": "p. ej. Gruista, Administrativo...",
            "list_title": "Requisitos de documentación",
            "empty_text": "Sin requisitos guardados todavía.",
            "help_text": (
                "Pulsa un requisito para ver y editar sus documentos "
                "obligatorios (disparan los avisos de falta y de "
                "caducidad). Guarda con el mismo nombre para editarlo; "
                "con otro nombre se crea uno nuevo y el original no se "
                "toca. Un requisito desactivado no genera avisos."
            ),
            "delete_note": (
                "Quien lo tenga asignado (personas o máquinas) se queda "
                "sin requisito."
            ),
            "saved_event": "eb:requirement-saved",
            "deleted_event": "eb:requirement-deleted",
            "changed_event": "eb:requirements-changed",
            "rows": rows,
            "sections": sections,
        }
        return render(request, "panel/job_positions/manage.html", {
            "picker": picker,
        })


class JobPositionSaveView(CompanyUserRequiredMixin, View):
    """
    H31 (S109). POST: crea un puesto nuevo (sin `position_pk`) o edita
    uno existente (con `position_pk`) -- nombre y la lista completa de
    tipos documentales obligatorios marcados en
    `JobPositionManageView`. A diferencia de las plantillas de dosier,
    un puesto SÍ puede guardarse sin ningún tipo marcado (un puesto
    recién creado, todavía sin perfilar del todo -- "que eso se pueda
    seguir perfilando en el futuro") -- nunca bloqueante.
    """

    def post(self, request, position_pk=None):
        if position_pk:
            position = get_object_or_404(JobPosition, pk=position_pk)
        else:
            position = JobPosition(
                created_by=getattr(request.user, "company_user", None),
            )

        name = request.POST.get("name", "").strip()
        if not name:
            return JsonResponse(
                {"ok": False, "error": "Falta el nombre del requisito."},
                status=400,
            )

        position.name = name
        try:
            position.save()
        except IntegrityError:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Ya existe un requisito con ese nombre.",
                },
                status=400,
            )
        type_ids = request.POST.getlist("document_type_ids")
        position.required_document_types.set(type_ids)
        # H30 (S120). Clases de permiso de conducción exigidas.
        category_ids = request.POST.getlist("driving_category_ids")
        position.required_driving_categories.set(category_ids)

        return JsonResponse(
            {"ok": True, "id": position.pk, "name": position.name}
        )


class JobPositionBulkDeleteView(CompanyUserRequiredMixin, View):
    """
    H30 (S128), hoja de ruta punto 1. POST `ids`: borra varios
    requisitos a la vez, tras el modal con cuenta atrás de 5 s del
    gestor común. Las personas y máquinas que lo tuvieran asignado
    quedan sin requisito (on_delete=SET_NULL), nunca se borran ni se
    tocan ellas. Sustituye al borrado de uno en uno (S109).
    """

    def post(self, request):
        ids = [i for i in request.POST.getlist("ids") if i.isdigit()]
        positions = JobPosition.objects.filter(pk__in=ids)
        count = positions.count()
        positions.delete()
        return JsonResponse({"ok": True, "count": count})


class JobPositionBulkActiveView(CompanyUserRequiredMixin, View):
    """
    H30 (S128), hoja de ruta punto 1. POST `ids` + `active` (1/0):
    activa o desactiva varios requisitos. Un requisito desactivado no
    genera avisos (`required_documentation_service.get_requirement` y
    `document_notice_service`), pero sigue asignado a quien lo tenga.
    """

    def post(self, request):
        ids = [i for i in request.POST.getlist("ids") if i.isdigit()]
        active = request.POST.get("active") == "1"
        # `update()` no pasa por auto_now: la fecha de edición se pone
        # a mano para que el cambio de estado quede registrado.
        count = JobPosition.objects.filter(pk__in=ids).update(
            is_active=active, updated_at=timezone.now(),
        )
        return JsonResponse({"ok": True, "count": count})


def _document_type_history_response(request, subject_model, subject_pk,
                                    type_code):
    """
    Render the full history (current + obsolete) of one document type
    for one subject, shared by Personal and machine files.
    ---
    Historial COMPLETO (vigente + obsoletos) de UN tipo documental para
    UN sujeto -- persona o máquina. H30 (S118): extraído de
    PersonalDocumentTypeHistoryView para que la ficha de máquina use
    exactamente el mismo cálculo y el mismo fragmento, sin duplicarlo.

    S117 -- incidente real de Miguel Ángel (Carvajal González, pk=218):
    el Historial pintaba "Vigente/Obsoleto" leyendo solo el is_obsolete
    guardado, mientras la ficha lo CALCULA por fechas
    (_split_current_obsolete) -- mostraba como vigente una
    investigación de 2023 con otra de 2025 más reciente. El estado del
    Historial sale del mismo cálculo que la ficha. Orden por fecha
    efectiva (caducidad si la hay, si no emisión), más reciente arriba,
    sin fecha al final.
    """
    subject = get_object_or_404(subject_model, pk=subject_pk)
    document_type = get_object_or_404(DocumentTypeCatalog, code=type_code)
    ct = ContentType.objects.get_for_model(subject_model)
    entries = list(DocumentIndexEntry.objects.filter(
        bucket=BUCKET, domain_content_type=ct, domain_object_id=subject.pk,
        document_type=document_type, entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).select_related("document_type").order_by("-expiry_date", "-id"))
    current, _obsolete = _split_current_obsolete(
        entries, get_required_type_ids(subject),
    )
    # S123: mismo criterio que la ficha -- un contrato/alta/IDC de un
    # periodo anterior sale como obsoleto en su historial.
    if subject_model is PersonIdentity:
        current, _obsolete = _move_previous_period_documents(
            current, _obsolete,
            _person_employment_periods(subject)["periods"],
        )
        # S125: mismo criterio que la ficha -- en Laboral un solo
        # vigente por tipo.
        current, _obsolete = _keep_latest_laboral_per_type(
            current, _obsolete,
        )
    current_pks = {entry.pk for entry in current}
    for entry in entries:
        entry.is_current_computed = entry.pk in current_pks
    entries.sort(
        key=lambda entry: (
            (entry.expiry_date or entry.issue_date) is not None,
            entry.expiry_date or entry.issue_date or date.min,
            entry.pk,
        ),
        reverse=True,
    )
    return render(
        request, "panel/documentation_h30/_personal_document_history.html",
        {"document_type": document_type, "entries": entries},
    )


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
        return _document_type_history_response(
            request, PersonIdentity, pk, type_code,
        )


class MachineDocumentTypeHistoryView(CompanyUserRequiredMixin, View):
    """
    H30 (S118), punto 1 de la hoja de ruta. GET: historial completo de
    UN tipo documental para UNA máquina -- mismo fragmento y mismo
    cálculo de vigencia que el de Personal. Sustituye a la tabla plana
    "Obsoletos" de la ficha de máquina: los obsoletos se ven aquí, en
    el Historial de su tipo.
    """

    def get(self, request, pk, type_code):
        return _document_type_history_response(
            request, MachineAsset, pk, type_code,
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
                {
                    "ok": False,
                    "error": "Falta el archivo de la ficha técnica.",
                },
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
            epi.code,
            today.isoformat(),
            DocumentIndexEntry.objects.count(),
            extension,
        )
        target_folder = "%s/%s" % (EPI_TECHNICAL_SHEETS_ROOT, epi.code)
        ensure_folder_chain(BUCKET, target_folder)
        blob_name = "%s/%s" % (target_folder, filename)
        content_type = (
            "application/pdf"
            if extension == "pdf"
            else "application/octet-stream"
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
        return JsonResponse(
            {
                "ok": True,
                "technical_sheet": {
                    "id": entry.pk,
                    "url": reverse(
                        "panel:documentation_document_view", args=[entry.pk]
                    ),
                },
            }
        )


class EpiBatchDeliveryExecuteView(DocsUploadAccessMixin, View):
    """
    H31 (S113). POST: entrega real de EPIs -- sustituye a
    `EpiIndividualDeliveryView` (S74) y `EpiMassDeliveryView` (S75),
    unificadas en una sola vista porque el proceso real de la empresa
    es el mismo en los dos casos (una o varias personas, uno o varios
    EPIs a la vez, nunca uno solo): Miguel Ángel, verbatim -- "se
    confecciona un documento a través de una plantilla [...] vienen
    una serie de EPIs [...] el trabajador firma el documento [...] los
    documentos variarán unos de otros dependiendo de a qué personas
    van dirigidos y dependiendo de la lista de EPIs que se les hace
    entrega."

    `person_ids`: una o varias pks (la ficha individual manda una
    sola; la barra de acción masiva del listado, las del casillero).
    `epi_ids`: una o varias pks de `EpiItemCatalog` -- ya vienen
    resueltas por el frontend, sea cual sea el origen (lote con
    casillas desmarcadas, o EPIs sueltos sin lote). Esta vista no sabe
    ni le importa si hubo una `EpiDeliveryBatchTemplate` de por medio
    -- eso es solo una ayuda de UI para rellenar la lista de EPIs más
    rápido, nunca un dato que se persista en el `EpiDelivery`.

    Por cada persona: un `EpiDelivery(extraction_method=MANUAL)` real
    por EPI entregado (igual que las vistas que sustituye), MÁS un
    documento PDF real generado con la relación exacta de EPIs
    entregados a esa persona en este lote concreto (nunca el mismo
    documento para dos personas distintas, ni con X -- una línea de
    texto por EPI, ver `epi_delivery_document_service`), indexado vía
    `upload_subject_document` (mismo mecanismo que cualquier subida
    real -- carpeta real de la persona, nunca la ruta antigua "DOC.
    PERSONAL/ENTREGA EPIS/{año}" de antes de la reorganización de
    H29) como tipo documental EPIS, y enlazado como `source_entry` de
    TODAS las entregas creadas para esa persona en esta misma llamada
    -- así el botón "Ver" de la pestaña EPIs (ya arreglado esta
    sesión) funciona también con estas.

    Encabezado de empresa resuelto por `CompanyFiscalProfile` contra
    `person.employer_company` -- si no hay perfil que case (variante
    de empresa todavía sin confirmar por Miguel Ángel), el documento
    se genera igual, sin esas 3 líneas, nunca bloqueante.

    WhatsApp de confirmación igual de no bloqueante que las vistas que
    sustituye -- un fallo de WhatsApp o de generación del PDF de una
    persona nunca revierte sus entregas ya comprometidas en BD, ni
    afecta al resto del lote.
    """

    def post(self, request):
        person_ids = request.POST.getlist("person_ids")
        epi_ids = request.POST.getlist("epi_ids")
        delivery_date_str = request.POST.get("delivery_date", "")

        if not person_ids:
            return JsonResponse(
                {"ok": False, "error": "No hay ninguna persona seleccionada."},
                status=400,
            )
        if not epi_ids or not delivery_date_str:
            return JsonResponse(
                {
                    "ok": False,
                    "error": (
                        "Selecciona al menos un EPI y la fecha de entrega."
                    ),
                },
                status=400,
            )
        try:
            year, month, day = (int(x) for x in delivery_date_str.split("-"))
            delivery_date = date(year, month, day)
        except ValueError:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Fecha de entrega con formato inválido.",
                },
                status=400,
            )

        epis = list(
            EpiItemCatalog.objects.filter(pk__in=epi_ids, is_active=True)
            .order_by("family", "label"),
        )
        if not epis:
            return JsonResponse(
                {
                    "ok": False,
                    "error": (
                        "Ninguno de los EPIs seleccionados existe o está "
                        "activo."
                    ),
                },
                status=400,
            )
        epi_labels = [epi.label for epi in epis]
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        try:
            epis_document_type = DocumentTypeCatalog.objects.get(code="EPIS")
        except DocumentTypeCatalog.DoesNotExist:
            return JsonResponse(
                {
                    "ok": False,
                    "error": (
                        "El tipo documental EPIS no existe en el catálogo."
                    ),
                },
                status=400,
            )

        created = []
        errors = []
        whatsapp_sent_count = 0
        documents_generated = 0
        for person_id in person_ids:
            try:
                person = PersonIdentity.objects.get(pk=person_id)
            except (PersonIdentity.DoesNotExist, ValueError):
                errors.append(
                    {"person_id": person_id, "error": "Persona no encontrada."}
                )
                continue

            deliveries = [
                EpiDelivery.objects.create(
                    person=person, epi=epi, delivery_date=delivery_date,
                    extraction_method=EpiDelivery.METHOD_MANUAL,
                )
                for epi in epis
            ]

            company_profile = resolve_company_fiscal_profile(
                person.employer_company
            )
            try:
                pdf_bytes = build_epi_delivery_pdf_bytes(
                    person, epi_labels, delivery_date, company_profile,
                )
                subject_label = "%s %s, %s" % (
                    person.first_surname,
                    person.second_surname,
                    person.given_name,
                )
                upload_result = upload_subject_document(
                    subject=person,
                    domain_content_type=person_ct,
                    document_type=epis_document_type,
                    data=pdf_bytes,
                    original_filename="entrega_epis_%s.pdf"
                    % delivery_date.isoformat(),
                    typed_date=None,
                    subject_label=subject_label,
                    uploaded_by=getattr(request.user, "company_user", None),
                )
                entry = upload_result["entry"]
                EpiDelivery.objects.filter(
                    pk__in=[d.pk for d in deliveries],
                ).update(source_entry=entry)
                documents_generated += 1
            except SubjectUploadError as exc:
                errors.append(
                    {
                        "person_id": person.pk,
                        "error": "Entregas registradas, pero el documento "
                        "no se pudo generar: %s" % exc,
                    }
                )

            for delivery in deliveries:
                if send_epi_delivery_whatsapp_confirmation(delivery):
                    whatsapp_sent_count += 1
            created.append({
                "person_id": person.pk,
                "delivery_ids": [d.pk for d in deliveries],
            })

        return JsonResponse({
            "ok": True,
            "created_count": len(created),
            "documents_generated": documents_generated,
            "whatsapp_sent_count": whatsapp_sent_count,
            "created": created,
            "errors": errors,
        })


class EpiBatchTemplateSaveView(CompanyUserRequiredMixin, View):
    """
    H31 (S113). POST: crea un lote nuevo (sin `template_pk`) o edita
    uno existente -- nombre y la lista completa de EPIs marcados en
    la propia pestaña EPIs (EpiTabFragmentView). Igual que un puesto de
    trabajo, un lote sí puede guardarse sin ningún EPI marcado todavía
    (se puede seguir perfilando después).
    """

    def post(self, request, template_pk=None):
        if template_pk:
            template = get_object_or_404(
                EpiDeliveryBatchTemplate, pk=template_pk
            )
        else:
            template = EpiDeliveryBatchTemplate()

        name = request.POST.get("name", "").strip()
        if not name:
            return JsonResponse(
                {"ok": False, "error": "Falta el nombre del lote."},
                status=400,
            )

        template.name = name
        try:
            template.save()
        except IntegrityError:
            return JsonResponse(
                {"ok": False, "error": "Ya existe un lote con ese nombre."},
                status=400,
            )
        item_ids = request.POST.getlist("item_ids")
        template.items.set(item_ids)

        return JsonResponse({"ok": True, "id": template.pk})


class EpiBatchTemplateDeleteView(CompanyUserRequiredMixin, View):
    """
    H31 (S113). POST: borra un lote -- nunca toca ningún `EpiDelivery`
    ya registrado (el lote es solo una ayuda de UI, no se referencia
    desde la entrega real).
    """

    def post(self, request, template_pk):
        template = get_object_or_404(EpiDeliveryBatchTemplate, pk=template_pk)
        template.delete()
        return JsonResponse({"ok": True})


class PersonalIntakeExtractView(DocsUploadAccessMixin, View):
    """
    H31 (S100), Bloque 1 -- PASO 1 del alta guiada por documentación.
    Recibe 1-N documentos subidos (DNI/contrato/reconocimiento médico,
    campo `documents`, multipart), extrae sus datos con
    `personal_intake_service` y devuelve un borrador ya combinado --
    NUNCA crea nada todavía. El supervisor confirma o corrige ese
    borrador en el paso 2 (`PersonalCreateView`), que es quien de
    verdad escribe en BD y sube los archivos a GCS.

    Puramente síncrono, sin persistencia intermedia -- si el
    supervisor cierra el modal sin confirmar, no queda ningún rastro
    en BD (ver anexo H31, corrección de preguntas 3/4: nada de cola de
    pendientes).
    """

    def post(self, request):
        import concurrent.futures

        files = request.FILES.getlist("documents")
        if not files:
            return JsonResponse(
                {"ok": False, "error": "No se ha subido ningún documento."},
                status=400,
            )
        # H31 (S100), confirmado por Miguel Ángel: 20 documentos cubren
        # prácticamente todo un alta real -- el resto se sube después
        # desde la ficha ya creada, por la vía normal (sin este tope).
        if len(files) > 20:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Máximo 20 documentos en el alta -- el resto "
                             "súbelos después desde la ficha ya creada.",
                },
                status=400,
            )

        # H31 (S100), incidente real: procesar los documentos uno a
        # uno convertía el tiempo total en la SUMA de los tiempos de
        # cada uno -- con 15 documentos y algún 429/504 transitorio de
        # Vertex AI en el camino (reintento real, ver
        # personal_intake_service._RETRY_DELAY_SECONDS), la espera en
        # el modal llegó a acercarse a los 3 minutos. Las llamadas son
        # de red (Cloud Vision + Gemini), no de CPU, así que
        # paralelizarlas con hilos es seguro (el GIL no bloquea E/S) y
        # el limitador de tasa compartido (`acquire_gemini_slot`, con
        # su propio `threading.Lock`) ya está pensado para que varias
        # llamadas concurrentes lo respeten sin pisarse. El tiempo
        # total pasa a ser el del documento más lento, no la suma de
        # todos.
        file_bytes = [(f.name, f.content_type, f.read()) for f in files]
        results_by_index = [None] * len(file_bytes)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            futures = {
                pool.submit(
                    personal_intake_service.extract_one_document,
                    data, content_type or "application/octet-stream",
                    filename=name,
                ): idx
                for idx, (name, content_type, data) in enumerate(file_bytes)
            }
            for future in concurrent.futures.as_completed(futures):
                results_by_index[futures[future]] = future.result()

        extractions = []
        per_file = []
        filenames = []
        for (name, _content_type, _data), result in zip(
            file_bytes, results_by_index
        ):
            extractions.append(result)
            filenames.append(name)
            per_file.append(
                {
                    "filename": name,
                    "document_type_code": result.get(
                        "document_type_code", "DESCONOCIDO"
                    ),
                    "confidence": result.get("confidence", ""),
                    "expiry_hint": result.get("expiry_hint", ""),
                    "issue_hint": result.get("issue_hint", ""),
                    "error": result.get("error"),
                }
            )

        # H31 (S101), Miguel Ángel, verbatim: "estamos indicando números
        # de documentos y no nombres de documentos [...] eso no sirve
        # absolutamente para nada" -- con 10-15 documentos en el mismo
        # lote, "Documento 7" no le dice al supervisor cuál de sus
        # archivos hay que revisar; el nombre real sí.
        merged = personal_intake_service.merge_person_draft(
            extractions, filenames=filenames,
        )
        draft = merged["draft"]

        # H31 (S101), Miguel Ángel, verbatim: "el hecho de que los
        # documentos que dispongan de número de DNI, ese número sea
        # coincidente para todos y rechazar el documento en minoría."
        # `merge_person_draft` ya decidió cuáles son -- aquí se
        # materializa el rechazo forzando su `document_type_code` a
        # DESCONOCIDO, que es justo lo que `_store_documents` ya
        # descarta por la vía normal (ver comentario de esa función).
        # El aviso de por qué se descarta cada uno ya viene en
        # merged["warnings"], con el nombre del archivo.
        for rejected_idx in merged.get("rejected_indices", []):
            per_file[rejected_idx]["document_type_code"] = "DESCONOCIDO"

        # H31 (S100), incidente real: el procesamiento en paralelo de
        # arriba puede tardar bastantes segundos sin tocar la BD para
        # nada (todo el tiempo es red hacia Gemini/Cloud Vision). La
        # conexión de BD que Django abrió al entrar en la vista
        # (autenticación) se queda inactiva mientras tanto, y MySQL
        # (con su propio `wait_timeout` real de PythonAnywhere) puede
        # cerrarla por su cuenta antes de que se vuelva a usar aquí --
        # error real visto en producción: `MySQLdb.OperationalError:
        # (4031, 'The client was disconnected by the server because
        # of inactivity...')`. `close_old_connections()` descarta esa
        # conexión ya inválida y fuerza una reconexión limpia en la
        # siguiente consulta, sin que el supervisor vea nada raro.
        from django.db import close_old_connections
        close_old_connections()

        # H31 (S100), incidente real de la propia sesión: Miguel Ángel
        # probó el alta con su propio DNI (ya dado de alta antes) y el
        # sistema no avisó -- dejó seguir hasta el paso de confirmación
        # sin decir nada, pese a haber leído el DNI correctamente.
        # Corregido: la comprobación de duplicado se hace aquí, nada
        # más leer los documentos, ANTES de mostrar el formulario de
        # confirmación -- nunca al final. Se devuelven igualmente los
        # datos ya leídos (draft/per_file), para que el supervisor vea
        # qué ha leído el sistema antes de cerrar el aviso.
        normalized_dni = personal_intake_service.normalize_dni(draft["dni"])
        existing_person = (
            PersonIdentity.objects.filter(dni=normalized_dni).first()
            if normalized_dni else None
        )
        # H31 (S101), Miguel Ángel, verbatim: "si no hay ningún DNI, ni
        # se puede extraer ningún número de identificación, debemos
        # avisar del error y no contaminar la base de datos con datos
        # potencialmente erróneos." Sin ningún documento del lote que
        # traiga el DNI/NIE (de cualquier tipo, ver
        # `merge_person_draft` -- ya no hace falta que sea el propio
        # carnet), el supervisor tendría que escribirlo entero a mano
        # sin nada que lo verifique -- justo el escenario real que
        # detectó Miguel Ángel: toda su documentación real yendo a
        # parar a una identidad inventada. Se corta aquí, antes de
        # mostrar el formulario de confirmación, nunca después.
        if not normalized_dni:
            return JsonResponse({
                "ok": False,
                "error": "No se ha podido identificar el DNI/NIE de "
                         "ningún documento del lote -- no se crea la "
                         "ficha para no guardar datos de identidad sin "
                         "verificar. Si es un trabajador nuevo, incluye "
                         "al menos un documento que traiga su DNI (el "
                         "propio DNI/NIE, un contrato, un ALTA de la "
                         "Seguridad Social...). Si es para añadir o "
                         "actualizar documentación de alguien que ya "
                         "está dado de alta, hazlo desde su propia "
                         "ficha -- este botón es solo para altas "
                         "nuevas.",
            }, status=400)

        # H24 (S144), Miguel Ángel: si ya existe pero está de baja, el
        # alta lo reactiva, guarda su documentación y lleva su carpeta a
        # ACTIVOS (también en local). Solo un activo sigue bloqueado.
        if existing_person and not existing_person.is_active_employee:
            return JsonResponse({
                "ok": True,
                "duplicate": False,
                "draft": draft,
                "warnings": merged["warnings"],
                "per_file": per_file,
                "reactivate": {
                    "id": existing_person.pk,
                    "label": "%s %s, %s" % (
                        existing_person.first_surname,
                        existing_person.second_surname,
                        existing_person.given_name,
                    ),
                },
            })

        if existing_person:
            return JsonResponse({
                "ok": True,
                "duplicate": True,
                "draft": draft,
                "warnings": merged["warnings"],
                "per_file": per_file,
                "existing_person_id": existing_person.pk,
                "existing_person_label": "%s %s, %s" % (
                    existing_person.first_surname,
                    existing_person.second_surname,
                    existing_person.given_name,
                ),
            })

        return JsonResponse({
            "ok": True,
            "duplicate": False,
            "draft": draft,
            "warnings": merged["warnings"],
            "per_file": per_file,
        })


class PersonalCreateView(DocsUploadAccessMixin, View):
    """
    H31 (S100), Bloque 1 -- PASO 2 (confirmación/creación) del alta
    guiada por documentación. Crea el `PersonIdentity` real que hasta
    ahora no existía -- confirmado contra el código real
    (`import_worker_machine_excel.py`, línea
    `person = PersonIdentity.objects.get(dni=dni)`) que la importación
    del Excel NUNCA crea filas nuevas, solo actualiza las que ya
    existen por DNI: el hueco de "cómo nace un PersonIdentity que
    todavía no está en el Excel" es exactamente el que cubre esta
    vista.

    CORREGIDO EN LA MISMA SESIÓN (S100): la primera versión de esta
    vista era un formulario manual puro -- Miguel Ángel corrigió que
    el alta real es guiada por documentación (ver anexo H31, sección
    "CORRECCIÓN CRÍTICA..."): el supervisor sube DNI/contrato,
    `PersonalIntakeExtractView` (paso 1) extrae los datos y precarga
    este formulario, y el supervisor solo confirma o corrige un campo
    puntual -- nunca teclea desde cero. Esta vista sigue aceptando los
    mismos campos de texto (siguen siendo necesarios como respaldo
    manual cuando la extracción falla del todo o el supervisor
    corrige), pero además recibe los MISMOS archivos ya extraídos en
    el paso 1 (campo `documents`, reenviados por el propio navegador)
    junto con el tipo documental ya detectado por archivo
    (`document_type_codes`, alineado por índice) para indexarlos de
    verdad en la carpeta de la persona recién creada -- sin repetir la
    llamada a Gemini, que ya se hizo en el paso 1.

    `is_active_employee=True` siempre -- esta vía de alta es,
    por definición, para personal activo (ver anexo H31, alcance
    "SOLO personal ACTIVO"). `folder_path` se calcula con la misma
    regla real ACTIVOS/{EMPRESA|GERENCIA|SIN_EMPRESA} que usa
    `restructure_personal_folders` (S99), compartida ahora vía
    `naming_service.build_person_category_root()` para no duplicarla
    (S100).
    """

    REQUIRED_FIELDS = ("dni", "first_surname", "given_name")
    OPTIONAL_TEXT_FIELDS = (
        "second_surname", "employer_company", "phone", "phone_secondary",
        "email", "address_street", "postal_code", "city", "province",
        "ss_affiliation_number", "professional_category",
    )
    OPTIONAL_DATE_FIELDS = ("birth_date", "hire_date")

    @staticmethod
    def _normalize_dni(raw_dni):
        return personal_intake_service.normalize_dni(raw_dni)

    # H31 (S100), ampliado tras petición de Miguel Ángel: "mejoramos
    # para incluir el resto de documentos. Supuestamente ya
    # disponemos de lo necesario para clasificar todo lo referente a
    # personal." Ya no hay una lista fija de 3 tipos -- se sube
    # cualquier documento cuyo `document_type_code` resuelva contra un
    # `DocumentTypeCatalog` real, activo, del dominio PERSONAL (ver
    # `_store_documents`, misma consulta que ya hace
    # `personal_intake_service` para construir el vocabulario de
    # extracción -- un tipo nuevo que se dé de alta en el catálogo se
    # permite solo, sin tocar este archivo). Solo `DESCONOCIDO` (o
    # cualquier código que no exista de verdad en el catálogo) se
    # sigue descartando sin subir -- el supervisor lo sube después por
    # la vía normal de la ficha ya creada.

    def _store_documents(self, request, person, folder_path):
        """
        H31 (S100). Sube de verdad a GCS e indexa (`DocumentIndexEntry`)
        cada archivo ya confirmado por el supervisor -- mismo mecanismo
        de subida (`spare_parts.gcs_service.upload_bytes`) y de
        nombrado (`naming_service.build_filename_personal`) que el
        resto de la plataforma, nunca inventado aquí. Un fallo al
        indexar un archivo concreto no revierte el alta ya confirmada
        del trabajador -- se informa como aviso, el supervisor puede
        subir ese documento después por la vía normal de la ficha.

        CORREGIDO EN LA MISMA SESIÓN (S100), incidente real con los 2
        DNI reales de Miguel Ángel: al principio solo se subían
        DNI/CONTRATO/RECONOCIMIENTO_MEDICO; ampliado después (mismo
        día, petición explícita) a TODO el catálogo real de PERSONAL
        -- cualquier `DESCONOCIDO` (código que no resuelve contra
        `DocumentTypeCatalog`, domain="PERSONAL", is_active=True) se
        sigue descartando sin subir, nunca entra a la ficha por esta
        vía. Además, cuando llegan varios documentos del mismo tipo
        con `tracks_expiry=True` (2 DNI, uno caducado y otro vigente),
        se aplica la sustitución real
        (`document_management.vigencia_service.evaluate_substitution`,
        mismo mecanismo ya usado por `subject_upload_service` para la
        subida desde ficha) -- el de fecha de caducidad más reciente
        queda vigente, el otro se marca `is_obsolete=True` y queda
        registrado en `DocumentSubstitutionLog`, en vez de dejar los
        dos "vigentes" a la vez sin ningún criterio, que es lo que
        pasó antes de esta corrección.
        """
        from document_explorer.models import DocumentIndexEntry
        from spare_parts.gcs_service import upload_bytes

        files = request.FILES.getlist("documents")
        type_codes = request.POST.getlist("document_type_codes")
        expiry_hints = request.POST.getlist("document_expiry_hints")
        issue_hints = request.POST.getlist("document_issue_hints")
        ct = ContentType.objects.get_for_model(PersonIdentity)
        today = timezone.now().date()
        warnings = []
        stored = 0
        skipped = []
        already = []
        # H31 (S100), incidente real reportado por Miguel Ángel: al
        # subir 2 DNI + 2 reconocimientos médicos en la misma alta,
        # `build_filename_personal` sin ordinal generaba el MISMO
        # nombre de archivo para los dos documentos del mismo tipo del
        # mismo día -- el segundo sobrescribía en GCS el blob del
        # primero en silencio, mientras se seguían creando filas
        # `DocumentIndexEntry` distintas apuntando a ese mismo blob ya
        # sobrescrito ("galimatías": 15 archivos subidos, varias
        # entradas duplicadas señalando al mismo objeto real).
        # Corregido: se cuenta cuántos nombres con el mismo prefijo
        # (persona+tipo+fecha) ya existen -- tanto ya indexados en BD
        # para esta persona (por si este mismo mecanismo se reutiliza
        # en el futuro para añadir documentos a alguien ya existente)
        # como los ya procesados en ESTE mismo lote -- y solo a partir
        # del segundo se añade el sufijo `_2`, `_3`... (`ordinal=None`
        # en el primero, igual que antes, para no cambiar el nombre en
        # el caso normal sin colisión).
        prefix_counts = {}
        # H31 (S100): snapshots "vigentes hasta ahora" de esta misma
        # sesión de alta, por código de tipo -- se van acumulando a
        # medida que se crean entries, para poder comparar cada
        # documento nuevo contra los ya creados en este mismo lote
        # (nunca hay preexistentes reales en un alta, pero el mismo
        # bucle sirve igual si en el futuro se reutiliza para añadir
        # documentos a una persona ya existente).
        current_by_type = {}
        company = Company.objects.first()

        for idx, f in enumerate(files):
            code = type_codes[idx] if idx < len(type_codes) else "DESCONOCIDO"
            document_type = DocumentTypeCatalog.objects.filter(
                code=code, domain="PERSONAL", is_active=True,
            ).first()
            if document_type is None:
                skipped.append(f.name)
                continue
            # H24 (S144), prueba con Cruces Gómez: el alta subía otra vez
            # documentos que ya estaban en el cubo. Mismo criterio que el
            # agente (S128): si el contenido ya está en el cubo, no se
            # sube ni se clasifica.
            content_md5 = base64.b64encode(
                hashlib.md5(f.read()).digest()).decode("ascii")
            f.seek(0)
            if DocumentIndexEntry.objects.filter(
                bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
                md5_hash=content_md5, purged_at__isnull=True,
            ).exists():
                already.append(f.name)
                continue
            type_code_for_name = document_type.code
            extension = (
                f.name.rsplit(".", 1)[-1] if "." in f.name else "pdf"
            )
            base_prefix = naming_service.build_filename_personal(
                person.first_surname, person.second_surname,
                person.given_name, type_code_for_name,
                today, extension=extension,
            ).rsplit(".", 1)[0]
            if base_prefix not in prefix_counts:
                prefix_counts[base_prefix] = DocumentIndexEntry.objects.filter(
                    bucket=BUCKET, domain_content_type=ct,
                    domain_object_id=person.pk,
                    entry_kind=DocumentIndexEntry.KIND_FILE,
                    deleted_at__isnull=True, purged_at__isnull=True,
                    name__startswith=base_prefix,
                ).count()
            prefix_counts[base_prefix] += 1
            ordinal = (
                prefix_counts[base_prefix]
                if prefix_counts[base_prefix] > 1 else None
            )
            filename = naming_service.build_filename_personal(
                person.first_surname, person.second_surname,
                person.given_name, type_code_for_name,
                today, ordinal=ordinal, extension=extension,
            )
            blob_name = "%s/%s" % (folder_path, filename)
            data = f.read()

            # H31 (S100), incidente real: los hints de fecha (expiry_
            # hint/issue_hint) viajan desde la extracción hasta aquí
            # por tres capas (JSON -> JS -> formulario) -- el motor
            # real (`classify_dates_in_text`) demostró leer bien los
            # dos ALTA reales de Miguel Ángel en pruebas directas
            # contra el archivo, pero la ficha creada seguía guardando
            # `issue_date=None`; nunca se localizó en qué capa exacta
            # se perdía. En vez de seguir persiguiéndolo, se recalcula
            # aquí mismo, contra los bytes reales que se están
            # indexando -- para PDF, sobre su texto ya incrustado
            # (gratis, sin red) -- así el resultado nunca depende de
            # que el hint haya sobrevivido el viaje completo. Para
            # imágenes se sigue confiando en el hint ya extraído (aquí
            # no se repite Cloud Vision, sería una llamada de red
            # más).
            engine_expiry_date, engine_issue_date = None, None
            logger.warning(
                "# [DIAG-FECHAS] archivo=%s extension=%r len(data)=%d",
                f.name, extension, len(data),
            )
            if extension.lower() == "pdf":
                embedded_text = personal_intake_service._pdf_embedded_text(
                    data
                )
                logger.warning(
                    "# [DIAG-FECHAS] archivo=%s len(embedded_text)=%d "
                    "primeros_200=%r",
                    f.name, len(embedded_text), embedded_text[:200],
                )
                if embedded_text:
                    from document_explorer.date_verification_service import (
                        classify_dates_in_text,
                    )
                    engine_expiry_date, engine_issue_date, _others = (
                        classify_dates_in_text(embedded_text)
                    )
                    logger.warning(
                        "# [DIAG-FECHAS] archivo=%s expiry=%r issue=%r",
                        f.name, engine_expiry_date, engine_issue_date,
                    )

            expiry_date = (
                engine_expiry_date
                if document_type and document_type.tracks_expiry else None
            )
            if expiry_date is None:
                raw_expiry = (
                    expiry_hints[idx] if idx < len(expiry_hints) else ""
                )
                if (
                    document_type
                    and document_type.tracks_expiry
                    and raw_expiry
                ):
                    try:
                        year, month, day = (
                            int(x) for x in raw_expiry.split("-")
                        )
                        expiry_date = date(year, month, day)
                    except ValueError:
                        expiry_date = None

            # H31 (S100), verbatim Miguel Ángel: "tengo dos altas, una
            # con grúas Adolfo y otra con asistencia y grúa, y no es
            # capaz de decir cuál es la vigente" -- ALTA (y muchos
            # otros tipos del catálogo) no tienen fecha de caducidad
            # propia; `document_management.vigencia_service` ya sabe
            # resolver ese caso comparando por `issue_date` (el más
            # reciente gana). Sin exigir `tracks_expiry` aquí a
            # propósito -- el caso real es justo el de los tipos que
            # NO tienen caducidad.
            issue_date = engine_issue_date
            if issue_date is None:
                raw_issue = issue_hints[idx] if idx < len(issue_hints) else ""
                if raw_issue:
                    try:
                        year, month, day = (
                            int(x) for x in raw_issue.split("-")
                        )
                        issue_date = date(year, month, day)
                    except ValueError:
                        issue_date = None

            try:
                upload_bytes(
                    BUCKET, blob_name, data,
                    content_type=f.content_type or "application/octet-stream",
                )
                entry = DocumentIndexEntry.objects.create(
                    bucket=BUCKET,
                    entry_kind=DocumentIndexEntry.KIND_FILE,
                    blob_name=blob_name,
                    blob_name_hash=path_digest(blob_name),
                    parent_path=folder_path,
                    parent_path_hash=path_digest(folder_path),
                    name=filename,
                    size_bytes=len(data),
                    md5_hash=content_md5,
                    content_type=f.content_type or "application/octet-stream",
                    document_type=document_type,
                    domain_content_type=ct,
                    domain_object_id=person.pk,
                    expiry_date=expiry_date,
                    issue_date=issue_date,
                )
                stored += 1

                # H31 (S100): la sustitución ya NO se limita a
                # `tracks_expiry=True` -- `evaluate_substitution()`
                # sabe decidir igual de bien por `issue_date` cuando
                # no hay `expiry_date` (ver docstring de
                # `vigencia_service`), que es precisamente el caso de
                # ALTA y de la mayoría de tipos sin caducidad propia.
                # Limitarlo a `tracks_expiry` era justo lo que dejaba
                # dos ALTA "vigentes" a la vez sin ningún criterio.
                # H30 (S122): un tipo acumulable (varios vigentes a la
                # vez -- contratos, altas, cursos, entregas...) nunca
                # entra en la sustitución (vigencia_service deja este
                # filtro al llamador y aquí faltaba).
                if document_type is not None and document_type.is_cumulative:
                    continue
                existing_snapshots = current_by_type.get(code, [])
                incoming_snapshot = DocumentSnapshot(
                    identifier=entry.pk, expiry_date=entry.expiry_date,
                    issue_date=entry.issue_date, indexed_at=entry.indexed_at,
                )
                result = evaluate_substitution(
                    incoming_snapshot, existing_snapshots,
                )
                if result.incoming_should_prevail:
                    for old_id, _old_expiry in [
                        (s.identifier, s.expiry_date)
                        for s in existing_snapshots
                        if s.identifier in result.existing_to_archive
                    ]:
                        old_entry = DocumentIndexEntry.objects.get(pk=old_id)
                        old_entry.is_obsolete = True
                        old_entry.save(update_fields=["is_obsolete"])
                        if company:
                            DocumentSubstitutionLog.objects.create(
                                company=company,
                                superseding_content_type=(
                                    ContentType.objects.get_for_model(
                                        DocumentIndexEntry,
                                    )
                                ),
                                superseding_object_id=entry.pk,
                                superseding_label=entry.name,
                                superseded_content_type=(
                                    ContentType.objects.get_for_model(
                                        DocumentIndexEntry,
                                    )
                                ),
                                superseded_object_id=old_entry.pk,
                                superseded_label=old_entry.name,
                                subject_label=str(person),
                                document_type=code,
                                reasoning=result.reasoning,
                            )
                    current_by_type[code] = [
                        s for s in existing_snapshots
                        if s.identifier not in result.existing_to_archive
                    ] + [incoming_snapshot]
                else:
                    entry.is_obsolete = True
                    entry.save(update_fields=["is_obsolete"])
                    current_by_type[code] = existing_snapshots
            except Exception as exc:
                logger.warning(
                    "# [PersonalCreateView] Fallo indexando %s para "
                    "PersonIdentity %s: %s", f.name, person.pk, exc,
                    exc_info=True,
                )
                warnings.append(
                    "No se pudo indexar %s -- súbelo de nuevo desde la "
                    "ficha ya creada." % f.name,
                )

        if already:
            warnings.append(
                "Ya estaban en el cubo (no se suben otra vez): %s."
                % ", ".join(already),
            )
        if skipped:
            warnings.append(
                "%d documento(s) no reconocido(s) (%s) no se han subido -- "
                "súbelos desde la ficha ya creada una vez confirmada."
                % (len(skipped), ", ".join(skipped)),
            )
        return stored, warnings

    def _reactivate(self, request, person, data, date_values, section):
        """
        H24 (S144). Onboarding of a worker who already exists but is
        terminated: reactivate, store the new documents, local sync.

        ---

        Alta de un trabajador que ya existe pero está de baja (Miguel
        Ángel: "debería de reactivar ese trabajador y clasificar su
        documentación y descargarla a su local"). Toma la empresa del
        alta si viene, lo reactiva con la fecha de alta como
        recontratación (su documentación pasa a ACTIVOS/<EMPRESA>),
        guarda los documentos nuevos en su carpeta y crea la descarga
        a local, que además mueve su carpeta de INACTIVOS y la borra.
        """
        company_user = request.user.company_user
        previous_local = local_download_service.snapshot_paths(person)
        if data["employer_company"]:
            person.employer_company = data["employer_company"]
            person.save(update_fields=["employer_company", "updated_at"])
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        _reactivate_person(
            person, date_values["hire_date"], person_ct, company_user,
            local_sync=False,
        )
        person.refresh_from_db()
        # S146: su sección desde la fecha de alta, antes de mover su
        # carpeta local (la categoría local sale de la sección).
        from hr_calendar.balance import assign_section

        assign_section([person], section, date_values["hire_date"],
                       company_user)
        ensure_folder_chain(BUCKET, person.folder_path)
        stored_count, doc_warnings = self._store_documents(
            request, person, person.folder_path,
        )
        download_job = local_download_service.create_for_person(
            person, company_user, previous_local,
        )
        return JsonResponse({
            "ok": True,
            "reactivated": True,
            "person_id": person.pk,
            "documents_stored": stored_count,
            "warnings": doc_warnings,
            "download": {
                "total": len(download_job.files),
                "status_url": reverse(
                    "panel:documentation_personal_local_download",
                    kwargs={"pk": download_job.pk},
                ),
            } if download_job else None,
            "redirect_url": reverse(
                "panel:documentation_personal_detail",
                kwargs={"pk": person.pk},
            ),
        })

    def post(self, request):
        data = {
            field: request.POST.get(field, "").strip()
            for field in self.REQUIRED_FIELDS + self.OPTIONAL_TEXT_FIELDS
        }
        data["dni"] = self._normalize_dni(data["dni"])

        missing = [f for f in self.REQUIRED_FIELDS if not data[f]]
        if missing:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Faltan campos obligatorios: %s."
                    % ", ".join(missing),
                },
                status=400,
            )

        if data["employer_company"] not in dict(ALTA_COMPANY_CHOICES):
            return JsonResponse(
                {"ok": False, "error": "Elige la empresa."}, status=400,
            )
        raw_section = request.POST.get("section_id", "")
        section = Section.objects.filter(
            pk=raw_section if raw_section.isdigit() else 0,
            company=request.user.company_user.company,
        ).first()
        if section is None:
            return JsonResponse(
                {"ok": False, "error": "Elige la sección."}, status=400,
            )

        existing = PersonIdentity.objects.filter(dni=data["dni"]).first()
        reactivate = (
            existing is not None and not existing.is_active_employee
            and request.POST.get("reactivate_person_id") == str(existing.pk)
        )
        if existing is not None and not reactivate:
            # S148 (alta por formulario): si está de baja, se ofrece
            # reactivarla, igual que en el alta por documentos.
            offer = None if existing.is_active_employee else {
                "id": existing.pk,
                "label": "%s %s, %s" % (
                    existing.first_surname, existing.second_surname,
                    existing.given_name,
                ),
            }
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Ya existe una persona con el DNI/NIE %s."
                    % data["dni"],
                    "reactivate": offer,
                },
                status=400,
            )

        date_values = {}
        for field in self.OPTIONAL_DATE_FIELDS:
            raw_value = request.POST.get(field, "").strip()
            if not raw_value:
                date_values[field] = None
                continue
            try:
                year, month, day = (int(x) for x in raw_value.split("-"))
                date_values[field] = date(year, month, day)
            except ValueError:
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "Fecha con formato inválido en %s." % field,
                    },
                    status=400,
                )
        # H31 (S100): fecha de alta por defecto = hoy si el supervisor
        # no la escribe -- un alta de trabajador siempre tiene una
        # fecha real de entrada, nunca queda en blanco por omisión.
        if date_values["hire_date"] is None:
            date_values["hire_date"] = timezone.now().date()

        if reactivate:
            return self._reactivate(
                request, existing, data, date_values, section)

        # H31 (S100), Miguel Ángel: "lo que sí sabemos es la población
        # donde vive [...] debe de haber una tabla [...] donde
        # podamos descargarnos los códigos postales de las
        # poblaciones." Si el supervisor (o la extracción) no trae
        # C.P. pero sí población, se rellena solo contra el dataset
        # real del INE -- nunca inventado, nunca sobrescribe un C.P.
        # ya indicado a mano.
        postal_code = data["postal_code"]
        if not postal_code and data["city"]:
            postal_code = postal_code_service.lookup_postal_code(data["city"])

        folder_root = naming_service.build_person_category_root(
            data["first_surname"], data["second_surname"],
            data["employer_company"], True,
        )
        folder_name = naming_service.build_person_folder_name(
            data["first_surname"], data["second_surname"], data["given_name"],
        )
        folder_path = "%s/%s" % (folder_root, folder_name)

        person = PersonIdentity(
            # S125: sin este vínculo la ficha queda fuera de WhatsApp
            # (adjuntos, "Leer aquí", envíos), que resuelven por Company.
            company=request.user.company_user.company,
            dni=data["dni"],
            first_surname=data["first_surname"],
            second_surname=data["second_surname"],
            given_name=data["given_name"],
            is_active_employee=True,
            employer_company=data["employer_company"],
            phone=data["phone"],
            phone_secondary=data["phone_secondary"],
            email=data["email"],
            address_street=data["address_street"],
            postal_code=postal_code,
            city=data["city"],
            province=data["province"],
            ss_affiliation_number=data["ss_affiliation_number"],
            professional_category=data["professional_category"],
            birth_date=date_values["birth_date"],
            hire_date=date_values["hire_date"],
            folder_path=folder_path,
        )
        try:
            person.full_clean()
        except ValidationError as exc:
            return JsonResponse(
                {"ok": False, "error": "; ".join(exc.messages)}, status=400,
            )
        person.save()
        ensure_folder_chain(BUCKET, folder_path)
        # S146: su sección desde la fecha de alta; decide también su
        # carpeta local (TALLER, ADMINISTRACION... o OPERARIOS).
        from hr_calendar.balance import assign_section

        assign_section([person], section, date_values["hire_date"],
                       request.user.company_user)

        stored_count, doc_warnings = self._store_documents(
            request, person, folder_path,
        )
        # H24 (S144): el alta termina cuando sus documentos están en la
        # carpeta local de OneDrive (los descarga el agente H28).
        # S148 (alta por formulario): sin documentos, el agente crea
        # igualmente su carpeta local vacía.
        from document_explorer.local_download_service import (
            create_for_person,
        )
        download_job = create_for_person(
            person, getattr(request.user, "company_user", None),
            always=True,
        )

        return JsonResponse(
            {
                "ok": True,
                "person_id": person.pk,
                "documents_stored": stored_count,
                "warnings": doc_warnings,
                "download": {
                    "total": len(download_job.files),
                    "status_url": reverse(
                        "panel:documentation_personal_local_download",
                        kwargs={"pk": download_job.pk},
                    ),
                } if download_job else None,
                "redirect_url": reverse(
                    "panel:documentation_personal_detail",
                    kwargs={"pk": person.pk},
                ),
            }
        )


class PersonalUpdateView(DocsUploadAccessMixin, View):
    """

    H31 (S74, ampliado S76, corregido S113). POST: edita los campos
    reales de PersonIdentity que tiene sentido de negocio corregir a
    mano desde el panel -- datos personales/contacto/dirección +
    fecha de alta/baja en la empresa (S76, Miguel Ángel: "echo en
    falta la dirección [...] fecha de alta, fecha de baja"). El resto
    de campos del modelo (dni, is_active_employee, employer_company,
    fechas de caducidad) son datos de `import_worker_machine_excel` --
    editarlos a mano aquí quedaría sobrescrito por la siguiente
    importación real del Excel, así que se muestran de solo lectura en
    la ficha, nunca en este formulario. `ss_affiliation_number` es la
    EXCEPCIÓN explícita (S113): aunque también lo trae el Excel, el
    único dato realmente inmutable de la ficha es el DNI -- Miguel
    Ángel decidió que este campo sí sea editable a mano sin importar
    de dónde vino el valor la última vez ("da igual cuál coger"),
    asumiendo que una importación posterior del Excel puede
    sobrescribirlo. Mismo control de acceso que subir/eliminar
    documentos (DocsUploadAccessMixin) -- editar la ficha es una
    acción de escritura, no de simple consulta.
    """

    TEXT_EDITABLE_FIELDS = (
        "given_name", "first_surname", "second_surname", "phone",
        "phone_secondary", "email", "address_street", "postal_code",
        "city", "province", "ss_affiliation_number",
        "professional_category", "nickname",
        # S148: observaciones libres (campo Memo).
        "notes",
    )
    DATE_EDITABLE_FIELDS = ("hire_date", "termination_date")
    # H31 (S109): `job_position` -- FK a JobPosition, editable igual
    # que el resto de esta ficha (nunca un formulario aparte). Sin
    # valor en el POST -> desasigna (None), mismo criterio que un
    # campo de fecha vacío.
    FK_EDITABLE_FIELDS = ("job_position",)
    EDITABLE_FIELDS = (
        TEXT_EDITABLE_FIELDS + DATE_EDITABLE_FIELDS + FK_EDITABLE_FIELDS
    )

    NAME_FIELDS = ("given_name", "first_surname", "second_surname")

    def post(self, request, pk):
        from datetime import date

        person = get_object_or_404(PersonIdentity, pk=pk)
        old_names = tuple(getattr(person, f) for f in self.NAME_FIELDS)
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
                        year, month, day = (
                            int(x) for x in raw_value.split("-")
                        )
                        setattr(person, field, date(year, month, day))
                    except ValueError:
                        return JsonResponse(
                            {
                                "ok": False,
                                "error": "Fecha con formato inválido en %s."
                                % field,
                            },
                            status=400,
                        )
                else:
                    setattr(person, field, None)
                updated_fields.append(field)
        for field in self.FK_EDITABLE_FIELDS:
            if field in request.POST:
                raw_value = request.POST.get(field, "").strip()
                if raw_value:
                    job_position = get_object_or_404(JobPosition, pk=raw_value)
                    setattr(person, field, job_position)
                else:
                    setattr(person, field, None)
                updated_fields.append(field)
        if not updated_fields:
            return JsonResponse(
                {"ok": False, "error": "Sin campos que actualizar."},
                status=400,
            )
        try:
            person.full_clean(validate_unique=False)
        except ValidationError as exc:
            return JsonResponse(
                {"ok": False, "error": "; ".join(exc.messages)}, status=400,
            )
        person.save(update_fields=updated_fields)
        renamed = 0
        if tuple(getattr(person, f) for f in self.NAME_FIELDS) != old_names:
            renamed = _realign_person_document_names(person)
        person_data = {
            f: getattr(person, f)
            for f in self.TEXT_EDITABLE_FIELDS + self.DATE_EDITABLE_FIELDS
        }
        person_data["job_position"] = (
            {"id": person.job_position_id, "name": str(person.job_position)}
            if person.job_position_id else None
        )
        return JsonResponse({
            "ok": True, "person": person_data,
            "renamed_documents": renamed,
        })


def _realign_person_document_names(person):
    """
    Realign the canonical names of a person's documents after a name or
    surname change. Returns how many names changed.
    ---
    Realinea los nombres canónicos de los documentos de una persona tras
    cambiar su nombre o apellidos (el nombre canónico los lleva dentro).
    Devuelve cuántos nombres cambiaron. S121: hueco real encontrado al
    corregir "CORREO" -> "CORREA" MUNHOZ (DNI a la vista) -- la ficha
    permitía editar los apellidos, pero sus 64 documentos seguían con el
    apellido viejo en el nombre. Misma función y convención que los
    realineados masivos (apply_personal_canonical_rename, fecha ficticia
    2021-01-01 de S98 solo dentro del nombre de los que no tienen
    fecha): solo cambia `name` en BD, nunca el archivo en GCS.
    """
    from document_explorer.classification_service import (
        apply_personal_canonical_rename,
    )
    from document_explorer.machine_folder_service import FICTITIOUS_DATE

    entries = DocumentIndexEntry.objects.filter(
        domain_content_type=ContentType.objects.get_for_model(PersonIdentity),
        domain_object_id=person.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True,
        purged_at__isnull=True,
        document_type__isnull=False,
    ).select_related("document_type").order_by("pk")
    reserved = set()
    renamed = 0
    for entry in entries:
        old_name = entry.name
        result = apply_personal_canonical_rename(
            entry, fictitious_date=FICTITIOUS_DATE, apply_changes=True,
            reserved_names=reserved,
        )
        if result.get("new_name") and result["new_name"] != old_name:
            renamed += 1
    logger.info(
        "Ficha %s: nombre/apellidos cambiados, %d nombres de documento "
        "realineados", person.pk, renamed,
    )
    return renamed


class PersonalSetAvatarView(DocsUploadAccessMixin, View):
    """
    H35 (S105). POST: fija `PersonIdentity.avatar_document` a un
    `DocumentIndexEntry`-imagen ya indexado de esa misma persona --
    Miguel Ángel, verbatim: "en los documentos que son imágenes hay
    que añadir la posibilidad de usar como foto de perfil".

    Deliberadamente NUNCA toca `document_type` del documento elegido
    -- a diferencia del mecanismo antiguo (código de catálogo IMAGEN,
    S73/S74), que reasignaba el tipo y por tanto le habría hecho
    perder su clasificación real (un DNI o un carnet de gruista usado
    como foto dejaría de ser DNI/CARNET_GRUISTA). Mismo control de
    acceso que subir/eliminar/editar documentos de la ficha
    (DocsUploadAccessMixin) -- fijar el avatar es una acción de
    escritura sobre la ficha, no una simple consulta.

    Solo admite un documento que:
    - Pertenezca de verdad a esa persona (mismo domain_content_type/
      domain_object_id que cualquier otro documento vinculado --
      nunca se acepta a ciegas un id de otra ficha aunque llegue en
      el POST).
    - Tenga extensión de imagen real -- un PDF no puede ser el avatar
      aunque su contenido sea una foto escaneada, mismo criterio que
      el resto del proyecto usa para "es imagen" (extensión, nunca
      inferencia de contenido).
    """

    IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")

    def post(self, request, pk):
        person = get_object_or_404(PersonIdentity, pk=pk)
        entry_id = request.POST.get("entry_id", "").strip()
        if not entry_id:
            return JsonResponse(
                {"ok": False, "error": "Falta entry_id."}, status=400,
            )
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        entry = get_object_or_404(
            DocumentIndexEntry,
            pk=entry_id,
            domain_content_type=person_ct,
            domain_object_id=person.id,
            deleted_at__isnull=True,
            purged_at__isnull=True,
        )
        if not entry.name.lower().endswith(self.IMAGE_EXTENSIONS):
            return JsonResponse(
                {"ok": False, "error": "Ese documento no es una imagen."},
                status=400,
            )
        person.avatar_document = entry
        person.save(update_fields=["avatar_document"])
        # H31 (S134): la foto elegida a mano se recorta igual que la del
        # DNI. Si no se ve ninguna cara, se usa la imagen entera, como
        # antes, y se quita el recorte anterior para que no la tape.
        from document_explorer.id_photo_service import (
            IdPhotoError, extract_from_entry,
        )

        try:
            extract_from_entry(person, entry, manual=True)
            avatar_url = reverse(
                "panel:documentation_personal_photo", args=[person.pk],
            )
        except IdPhotoError:
            PersonIdPhoto.objects.filter(person=person).delete()
            avatar_url = reverse(
                "panel:documentation_document_view", args=[entry.pk],
            )
        return JsonResponse({"ok": True, "avatar_url": avatar_url})


def _platform_photo_name(person):
    """
    File name of the platform photo: SURNAMES_NAME.png, no accents.

    ---

    Nombre del archivo de la foto para plataforma: APELLIDOS_NOMBRE.png,
    sin tildes ni espacios (mismo estilo que los nombres canónicos).
    """
    parts = (person.first_surname, person.second_surname, person.given_name)
    text = "_".join(p for p in parts if p) or "FOTO_%s" % person.pk
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = "".join(c if c.isalnum() else "_" for c in text.upper())
    return "%s.png" % "_".join(t for t in text.split("_") if t)


def _person_photo_bytes(person):
    """
    The person photo as image bytes: the ID crop, or the chosen image.

    ---

    La foto de la persona en bytes: el recorte de carné si lo hay; si
    no, la imagen elegida como foto (`avatar_document`); None si no
    tiene ninguna.
    """
    id_photo = PersonIdPhoto.objects.filter(person=person).first()
    if id_photo is not None:
        return bytes(id_photo.image)
    entry = person.avatar_document
    if entry is not None and entry.name.lower().endswith(
        PersonalSetAvatarView.IMAGE_EXTENSIONS,
    ):
        from spare_parts.gcs_service import download_bytes

        return download_bytes(entry.bucket, entry.blob_name)
    return None


class PersonalPhotoView(CompanyUserRequiredMixin, View):
    """
    GET: the ID photo crop of a person (JPEG).

    ---

    H31 (S134). GET: la foto de carné recortada de la persona, en JPEG,
    para la ficha y su ventana "Ver foto". Mismo acceso que "Ver" un
    documento.
    """

    def get(self, request, pk):
        id_photo = get_object_or_404(PersonIdPhoto, person_id=pk)
        response = HttpResponse(bytes(id_photo.image),
                                content_type="image/jpeg")
        response["Cache-Control"] = "private, max-age=86400"
        return response


class PersonalPlatformPhotoView(CompanyUserRequiredMixin, View):
    """
    GET: download the person photo as a PNG under 128 KB.

    ---

    H31 (S134). GET: descarga la foto "para plataforma": PNG de menos
    de 128 KB con el nombre de la persona -- Miguel Ángel: "que ponga
    únicamente descarga foto para plataforma y se descarga con el
    nombre de la persona en formato PNG y con menos de 128K". Con
    `x`, `y`, `w`, `h` (fracciones de 0 a 1) descarga solo el recuadro
    marcado en la ventana "Ver foto": *"una herramienta para que
    seleccione un rectángulo de la foto"*, porque las plataformas
    piden que la cara ocupe la mayor parte posible.
    """

    def get(self, request, pk):
        from document_explorer.id_photo_service import (
            IdPhotoError, platform_png,
        )

        person = get_object_or_404(PersonIdentity, pk=pk)
        data = _person_photo_bytes(person)
        if data is None:
            return HttpResponse("Esta persona no tiene foto.", status=404,
                                content_type="text/plain; charset=utf-8")
        box = None
        raw_box = [request.GET.get(key, "") for key in ("x", "y", "w", "h")]
        if all(raw_box):
            try:
                box = tuple(float(value) for value in raw_box)
            except ValueError:
                return HttpResponse(
                    "Recuadro con formato inválido.", status=400,
                    content_type="text/plain; charset=utf-8",
                )
        try:
            png = platform_png(data, box=box)
        except IdPhotoError as exc:
            return HttpResponse(str(exc), status=422,
                                content_type="text/plain; charset=utf-8")
        response = HttpResponse(png, content_type="image/png")
        response["Content-Disposition"] = 'attachment; filename="%s"' % (
            _platform_photo_name(person)
        )
        return response


class PersonalPhotoUploadView(DocsUploadAccessMixin, View):
    """
    POST: upload a profile photo straight to the person record.

    ---

    H31 (S134). POST: sube la foto de perfil directamente a la ficha,
    sin pasar por la subida de documentos (que la leía con Gemini, ~20
    s, y la archivaba como documento IMAGEN). Miguel Ángel: *"La foto no
    tiene por qué leerla, es una foto que vamos a subir, foto de
    perfil, y lo que queremos es que sea lo más rápido posible."*
    """

    MAX_BYTES = 20 * 1024 * 1024

    def post(self, request, pk):
        from document_explorer.id_photo_service import (
            IdPhotoError, save_uploaded,
        )

        person = get_object_or_404(PersonIdentity, pk=pk)
        upload = request.FILES.get("file")
        if upload is None:
            return JsonResponse(
                {"ok": False, "error": "Falta la foto."}, status=400,
            )
        if upload.size > self.MAX_BYTES:
            return JsonResponse({"ok": False, "error": (
                "La foto pesa más de 20 MB."
            )}, status=400)
        try:
            save_uploaded(person, upload.read())
        except IdPhotoError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        return JsonResponse({"ok": True})


def _source_label(entry):
    """
    What the supervisor sees of a photo source: its type, not its file.

    ---

    Lo que ve el supervisor del documento de origen de la foto: su tipo
    ("su DNI"), nunca el nombre del archivo (S136, criterio de Miguel
    Ángel para todo el panel).
    """
    label = entry.document_type.label if entry.document_type_id else ""
    return "su %s" % label if label else "un documento"


class PersonalPhotoExtractView(DocsUploadAccessMixin, View):
    """
    POST: crop the ID photo now, automatically or from one document.

    ---

    H31 (S134). POST: saca ya la foto de carné, sin esperar a la tarea
    periódica.

    S136, ventana de gestión de la foto (Miguel Ángel: "modificar la
    existente, ponerla en el modo automático"):
    - con `entry`: la saca de ese documento concreto de la persona y la
      deja puesta a mano (la tarea ya no la cambia);
    - sin `entry`: modo automático (`set_automatic`): quita la marca de
      puesta a mano y la saca del primer documento con cara.
    """

    def post(self, request, pk):
        from document_explorer.id_photo_service import (
            IdPhotoError, candidates, extract_from_entry, set_automatic,
        )

        person = get_object_or_404(PersonIdentity, pk=pk)
        entry_pk = request.POST.get("entry", "").strip()
        if entry_pk:
            entry = candidates(person).filter(pk=entry_pk).first()
            if entry is None:
                return JsonResponse({"ok": False, "error": (
                    "Ese documento no es un DNI, NIE, pasaporte, permiso "
                    "ni imagen de esta persona."
                )}, status=400)
            try:
                extract_from_entry(person, entry, manual=True)
            except IdPhotoError as exc:
                return JsonResponse(
                    {"ok": False, "error": str(exc)}, status=422,
                )
            return JsonResponse({"ok": True, "source": _source_label(entry)})
        entry = set_automatic(person)
        if entry is None:
            return JsonResponse({"ok": False, "error": (
                "Foto en modo automático, pero no se ha encontrado "
                "ninguna cara en el DNI, NIE, pasaporte, permiso de "
                "conducir ni imágenes de esta persona."
            )}, status=422)
        return JsonResponse({"ok": True, "source": _source_label(entry)})


class PersonalPhotoRotateView(DocsUploadAccessMixin, View):
    """
    POST: turn the person photo a quarter (direction=left|right).

    ---

    H31 (S136). POST: gira la foto de la persona un cuarto de vuelta a
    la izquierda o a la derecha (`direction`), para corregir a mano una
    foto que ha salido torcida. Queda puesta a mano.
    """

    def post(self, request, pk):
        from document_explorer.id_photo_service import (
            IdPhotoError, save_rotated,
        )

        person = get_object_or_404(PersonIdentity, pk=pk)
        direction = request.POST.get("direction", "")
        if direction not in ("left", "right"):
            return JsonResponse(
                {"ok": False, "error": "Sentido de giro no válido."},
                status=400,
            )
        data = _person_photo_bytes(person)
        if data is None:
            return JsonResponse(
                {"ok": False, "error": "Esta persona no tiene foto."},
                status=404,
            )
        id_photo = PersonIdPhoto.objects.filter(person=person).first()
        source = id_photo.source if id_photo else person.avatar_document
        try:
            save_rotated(person, data, direction == "right", source=source)
        except IdPhotoError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=422)
        return JsonResponse({"ok": True})


class PersonalPhotoQueueView(DocsUploadAccessMixin, View):
    """
    POST: send the selected persons back to automatic photo search.

    ---

    H31 (S136). POST (`person_ids`): acción masiva de la pestaña
    Personal, "Volver a sacar la foto". Las personas marcadas vuelven
    al modo automático (también las puestas a mano) y a la cola de la
    tarea de cada 15 minutos.
    """

    def post(self, request):
        from document_explorer.id_photo_service import queue_recheck

        person_ids = [
            pk for pk in request.POST.getlist("person_ids") if pk.isdigit()
        ]
        if not person_ids:
            return JsonResponse(
                {"ok": False, "error": "No hay personas seleccionadas."},
                status=400,
            )
        count = queue_recheck(person_ids)
        return JsonResponse({"ok": True, "count": count})


class MachineSetAvatarView(DocsUploadAccessMixin, View):
    """
    Set an already indexed image document of a machine as its photo.
    ---
    H30 (S118). POST: fija `MachineAsset.avatar_document` a un
    documento-imagen ya indexado de esa misma máquina -- Miguel Ángel:
    "tenemos muchas máquinas con fotos, pues una de las fotos es
    elegirla como foto de perfil de la maquinaria". Mismas garantías
    que PersonalSetAvatarView: el documento tiene que pertenecer a esa
    máquina y tener extensión de imagen real, y nunca se toca su
    `document_type`.
    """

    def post(self, request, pk):
        machine = get_object_or_404(MachineAsset, pk=pk)
        entry_id = request.POST.get("entry_id", "").strip()
        if not entry_id:
            return JsonResponse(
                {"ok": False, "error": "Falta entry_id."}, status=400,
            )
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        entry = get_object_or_404(
            DocumentIndexEntry,
            pk=entry_id,
            domain_content_type=machine_ct,
            domain_object_id=machine.pk,
            deleted_at__isnull=True,
            purged_at__isnull=True,
        )
        if not entry.name.lower().endswith(
            PersonalSetAvatarView.IMAGE_EXTENSIONS,
        ):
            return JsonResponse(
                {"ok": False, "error": "Ese documento no es una imagen."},
                status=400,
            )
        machine.avatar_document = entry
        machine.save(update_fields=["avatar_document"])
        return JsonResponse({"ok": True})


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


def _default_dossier_body_html(person, document_count):
    """
    S130. Cuerpo por defecto del correo de un dossier, para no tener
    que escribirlo cada vez (solo se rellena el destinatario).
    ---
    S130. Default body for a dossier e-mail, so it never has to be
    typed (only the recipient is filled in).
    """
    plural = "s" if document_count != 1 else ""
    return (
        "<p>Buenos días:</p>"
        f"<p>Les adjuntamos el dossier de documentación de "
        f"<strong>{html_escape(str(person))}</strong> "
        f"({document_count} documento{plural}).</p>"
        "<p>Quedamos a su disposición para cualquier aclaración.</p>"
        "<p>Un saludo.</p>"
    )


def _build_dossier_notification_eml(
    person, entries, body_html, sender_company_user, epi_deliveries=None,
):
    """
    H31 (S104), punto 1 de la hoja de ruta. Construye el `.eml` real
    de envío de un dossier de documentación para UNA persona --
    extiende el mecanismo `.eml` de `_build_notification_eml`
    (H31 S74/S75) pero adjuntando el PDF/ZIP del dossier en vez de
    incrustar el HTML de una circular en el cuerpo, con un cuerpo de
    mensaje editable (`body_html`, ver PersonalDossierEmailSendView) y
    la firma real del supervisor que envía
    (`sender_company_user.email_signature_html`, H31 S104 -- ver nota
    en el modelo `CompanyUser` sobre por qué no se depende de la firma
    por defecto de Outlook).

    Intenta primero el PDF único (`_build_dossier_pdf_bytes`); si
    `DossierBuildError` (ningún documento con formato soportado para
    PDF), cae automáticamente al ZIP (`_build_dossier_zip_bytes`, que
    admite cualquier formato original) -- nunca se aborta el envío
    solo porque el PDF fusionado no sea viable para esta selección
    concreta.

    Lanza `NotificationEmlError` -- nunca HttpResponse, mismo patrón
    que `_build_notification_eml` -- cuando ni el PDF ni el ZIP pueden
    construirse (lista de `entries` vacía o sin ningún documento
    descargable). Desde S130 el destinatario va vacío (borrador
    `X-Unsent`) y `body_html` vacío usa `_default_dossier_body_html`.
    ---
    H31 (S104), roadmap point 1. Builds the real dossier-sending
    `.eml` for ONE person -- extends the `.eml` mechanism from
    `_build_notification_eml` (H31 S74/S75) but attaching the
    dossier's PDF/ZIP instead of embedding a circular's HTML in the
    body, with an editable message body (`body_html`, see
    PersonalDossierEmailSendView) and the real signature of the
    sending supervisor (`sender_company_user.email_signature_html`,
    H31 S104 -- see the note on the `CompanyUser` model on why
    Outlook's default signature isn't relied upon).

    Tries the single PDF first (`_build_dossier_pdf_bytes`); on
    `DossierBuildError` (no document with a PDF-supported format) it
    automatically falls back to the ZIP (`_build_dossier_zip_bytes`,
    which accepts any original format) -- the send is never aborted
    just because the merged PDF isn't viable for this particular
    selection.

    Raises `NotificationEmlError` -- never HttpResponse, same pattern
    as `_build_notification_eml` -- when neither the PDF nor the ZIP
    can be built (empty `entries`, or no downloadable document at
    all). Since S130 the recipient is left empty (`X-Unsent` draft)
    and an empty `body_html` uses `_default_dossier_body_html`.
    """
    # S130, Miguel Ángel: "Debería [...] generar el HTML correspondiente
    # para no tener que escribir ni los cuerpos de mensaje [...]
    # solamente rellenar ya lo que es el destinatario." El destinatario
    # se deja vacío (el dossier suele ir a un cliente o a una obra, no
    # al propio trabajador, y la mayoría no tiene correo registrado: antes
    # eso tumbaba el .eml entero) y `X-Unsent: 1` hace que Outlook lo
    # abra como un BORRADOR editable con el cuerpo y el adjunto ya
    # puestos, no como un mensaje recibido de solo lectura. Sin `From`:
    # en un borrador lo pone la cuenta de quien lo envía.
    try:
        attachment_bytes, attachment_filename = _build_dossier_pdf_bytes(
            person, entries, epi_deliveries=epi_deliveries,
        )
        attachment_mime = ("application", "pdf")
    except DossierBuildError:
        try:
            attachment_bytes, attachment_filename = _build_dossier_zip_bytes(
                person, entries, epi_deliveries=epi_deliveries,
            )
            attachment_mime = ("application", "zip")
        except DossierBuildError as exc:
            raise NotificationEmlError(str(exc)) from exc

    if not (body_html or "").strip():
        body_html = _default_dossier_body_html(
            person, len(entries or []) + len(epi_deliveries or []),
        )

    msg = StdEmailMessage()
    msg["Subject"] = f"Dossier de documentación -- {person}"
    msg["X-Unsent"] = "1"

    msg.set_content(
        f"Dossier de documentación de {person} (adjunto).\n"
        "Este cliente de correo no muestra HTML -- abra este mensaje "
        "con un cliente compatible."
    )

    signature_html = (
        (sender_company_user.email_signature_html or "").strip()
        if sender_company_user else ""
    )
    logo_cid = make_msgid()
    html_body = f"""
        <html><body style="font-family: Arial, sans-serif;">
          <p style="margin-bottom:16px;">
            <img src="cid:{logo_cid[1:-1]}" alt="Grupo Álvarez" height="40">
          </p>
          {body_html}
          {signature_html}
        </body></html>
    """
    msg.add_alternative(html_body, subtype="html")

    logo_path = find_static("panel/img/grupo_alvarez_logo.png")
    if logo_path:
        with open(logo_path, "rb") as logo_file:
            msg.get_payload()[1].add_related(
                logo_file.read(), "image", "png", cid=logo_cid,
            )

    maintype, subtype = attachment_mime
    msg.add_attachment(
        attachment_bytes,
        maintype=maintype,
        subtype=subtype,
        filename=attachment_filename,
    )

    filename = f"dossier_notificacion_{person.pk}.eml"
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
            eml_bytes, filename = _build_notification_eml(
                person, document_type
            )
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


class PersonMassSetJobPositionView(DocsUploadAccessMixin, View):
    """
    H31 (S109). POST: asigna (o desasigna, con `job_position_id`
    vacío) un puesto de trabajo a varias personas a la vez -- sobre
    el mismo Set `selection` de siempre, mismo mecanismo que el resto
    de acciones masivas de esta barra. Miguel Ángel, verbatim: "vamos
    a crear el puesto ya de chófer [...] elegir los choferes [...]
    asígnales el puesto de chófer [...] cambiaríamos en esos el
    puesto de General por el puesto de chófer" -- una asignación
    masiva nueva SIEMPRE sustituye el puesto anterior de cada
    persona, nunca lo acumula (un `ForeignKey`, no M2M -- una persona
    tiene un único puesto a la vez).
    """

    def post(self, request):
        person_ids = request.POST.getlist("person_ids")
        job_position_id = request.POST.get("job_position_id", "").strip()

        if not person_ids:
            return JsonResponse(
                {"ok": False, "error": "No hay ninguna persona seleccionada."},
                status=400,
            )

        if job_position_id:
            job_position = get_object_or_404(JobPosition, pk=job_position_id)
        else:
            job_position = None

        updated = PersonIdentity.objects.filter(
            pk__in=person_ids,
        ).update(job_position=job_position)

        return JsonResponse({
            "ok": True,
            "updated_count": updated,
            "job_position_name": str(job_position) if job_position else None,
        })


class PersonalTerminateView(DocsUploadAccessMixin, View):
    """
    H31 (S117). POST: baja por RESCISIÓN DE CONTRATO (el trabajador
    deja la empresa) de uno o varios trabajadores a la vez -- nunca
    confundir con una baja médica/ITL (hr_calendar.MedicalLeavePeriod).
    Mismo proceso que "Dar de baja" en Centros de gasto, decisión
    explícita de Miguel Ángel: "señalo en el listado, en el casillero
    50 personas y en el panel de acciones me aparece ya accionable el
    botón de dar de baja [...] con fecha del día [...] la selección de
    personal la haces desde el CRUD, no desde el modal" -- el modal del
    frontend solo confirma.

    Aplica lo ya decidido en S100 para la baja: pasa a inactivo, se
    guarda la fecha de baja (HOY) y su documentación va a la carpeta de
    inactivos, desde donde se consulta en el explorador de archivos.
    Reutiliza sin duplicar la regla de carpetas de S99
    (naming_service.build_person_category_root -> PERSONAL/INACTIVOS) y
    el movimiento VIRTUAL de move_service.move_entries() por
    domain_object real (4.12: nunca se toca GCS), igual que
    restructure_personal_folders. Una transacción por persona: si una
    falla, las demás no se deshacen.

    POST person_ids (uno o varios).
    """

    def post(self, request):
        person_ids = request.POST.getlist("person_ids")
        if not person_ids:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "No hay ningún trabajador seleccionado.",
                },
                status=400,
            )
        today = timezone.localdate()
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        terminated_ids = []
        skipped_names = []
        moved_total = 0
        for person in PersonIdentity.objects.filter(pk__in=person_ids):
            if not person.is_active_employee:
                skipped_names.append(_person_display_name(person))
                continue
            moved_total += _terminate_person(
                person, today, person_ct, request.user.company_user,
            )
            terminated_ids.append(person.pk)
        return JsonResponse({
            "ok": True,
            "terminated_count": len(terminated_ids),
            "terminated_ids": terminated_ids,
            "skipped_names": skipped_names,
            "moved_count": moved_total,
        })


def _person_display_name(person):
    """
    "APELLIDO1 APELLIDO2, NOMBRE", same format as the list.
    ---
    "APELLIDO1 APELLIDO2, NOMBRE", mismo formato que el listado.
    """
    return "%s %s, %s" % (
        person.first_surname, person.second_surname, person.given_name,
    )


def _terminate_person(person, termination_date, person_ct, company_user):
    """
    H31 (S117). Marks one worker as terminated (rescisión de contrato)
    and moves his/her documentation virtually to PERSONAL/INACTIVOS.
    Returns the number of documents moved.
    ---
    Marca un trabajador como dado de baja (rescisión de contrato) y
    mueve virtualmente su documentación a PERSONAL/INACTIVOS. Devuelve
    el número de documentos movidos.
    """
    from django.db import transaction

    from document_explorer.person_folder_service import (
        expected_base_folder, free_folder_for, move_person_documents,
    )

    # Mismo criterio que restructure_personal_folders ante homónimos:
    # nunca mezclar la documentación de dos personas en una carpeta --
    # sufijo _2, _3... si ya tiene documentos de OTRA persona (S125:
    # compartido en person_folder_service).
    new_folder_path = free_folder_for(
        person, expected_base_folder(person, is_active=False),
    )
    previous_local = local_download_service.snapshot_paths(person)

    with transaction.atomic():
        moved = move_person_documents(person, new_folder_path)
        person.is_active_employee = False
        person.termination_date = termination_date
        person.save(update_fields=[
            "is_active_employee", "termination_date", "updated_at",
        ])
        # S117 -- Miguel Ángel: "hay que desactivar su cuenta de acceso
        # si la tiene". Se desactiva en los dos sitios que la gobiernan:
        # CompanyUser.is_active (acceso al panel) y User.is_active de
        # Django (bloquea el inicio de sesión).
        account_disabled = _set_person_account_active(person, False)
    # H24 (S144): "poner inactivo a una persona en el panel y que [...]
    # en el local también la ponga en inactivos" (agente H28).
    local_download_service.create_for_person(
        person, company_user, previous_local,
    )
    logger.info(
        "# [H31-BAJA] PersonIdentity pk=%s dado de baja (rescisión) con "
        "fecha %s por CU pk=%s -- %d documento(s) movidos a %s; cuenta "
        "de acceso desactivada: %s.",
        person.pk, termination_date, company_user.pk, moved,
        new_folder_path, account_disabled,
    )
    return moved


def _set_person_account_active(person, active):
    """
    S117. Enables/disables the panel account linked to a worker
    (PersonIdentity.company_user), if any: CompanyUser.is_active and the
    Django User.is_active. Never touches a pending pre-registration
    (pending_onboarding), which is not a usable account yet. Returns
    True if an account was changed.
    ---
    Activa/desactiva la cuenta del panel enlazada a un trabajador
    (PersonIdentity.company_user), si la tiene: CompanyUser.is_active y
    User.is_active de Django. Nunca toca un pre-registro pendiente
    (pending_onboarding), que aún no es una cuenta utilizable. Devuelve
    True si se ha cambiado alguna cuenta.
    """
    account = person.company_user
    if account is None or account.pending_onboarding:
        return False
    account.is_active = active
    account.save(update_fields=["is_active"])
    if account.user_id:
        account.user.is_active = active
        account.user.save(update_fields=["is_active"])
    return True


def _reactivate_person(person, rehire_date, person_ct, company_user,
                       local_sync=True):
    """
    S117. Undoes a termination or re-hires a worker: back to active,
    termination date cleared, documentation moved back (virtually) to
    his/her ACTIVOS folder (same S99 rule), panel account re-enabled.
    With rehire_date, the hire date becomes that date (re-hiring);
    without it, the original hire date is kept (undo). Returns the
    number of documents moved.
    ---
    Deshace una baja o recontrata a un trabajador: vuelve a activo, se
    borra la fecha de baja, su documentación vuelve (virtualmente) a su
    carpeta de ACTIVOS (misma regla de S99) y se reactiva su cuenta del
    panel. Con rehire_date, la fecha de alta pasa a ser esa
    (recontratación); sin ella, se conserva la fecha de alta original
    (deshacer). Devuelve el número de documentos movidos.
    """
    from django.db import transaction

    from document_explorer.person_folder_service import (
        expected_base_folder, free_folder_for, move_person_documents,
    )

    new_folder_path = free_folder_for(
        person, expected_base_folder(person, is_active=True),
    )
    previous_local = local_download_service.snapshot_paths(person)

    with transaction.atomic():
        moved = move_person_documents(person, new_folder_path)
        person.is_active_employee = True
        person.termination_date = None
        update_fields = [
            "is_active_employee", "termination_date", "updated_at",
        ]
        if rehire_date:
            person.hire_date = rehire_date
            update_fields.append("hire_date")
        person.save(update_fields=update_fields)
        account_enabled = _set_person_account_active(person, True)
    # H24 (S144): su carpeta local vuelve también a ACTIVOS (agente H28).
    # El alta de un trabajador de baja lo pide ella misma, después de
    # guardar los documentos nuevos (`local_sync=False`).
    if local_sync:
        local_download_service.create_for_person(
            person, company_user, previous_local,
        )
    logger.info(
        "# [H31-REACTIVAR] PersonIdentity pk=%s reactivado (%s) por CU "
        "pk=%s -- %d documento(s) movidos a %s; cuenta reactivada: %s.",
        person.pk,
        "recontratación %s" % rehire_date if rehire_date else "deshacer baja",
        company_user.pk, moved, new_folder_path, account_enabled,
    )
    return moved


class PersonalReactivateView(DocsUploadAccessMixin, View):
    """
    H31 (S117). POST: deshace la baja por rescisión de contrato o
    recontrata a uno o varios trabajadores inactivos -- Miguel Ángel:
    "evidentemente es preciso poder recontratar o deshacer". Mismo
    patrón que PersonalTerminateView: la selección se hace en el
    listado y el modal solo confirma. Con rehire=1, la fecha de alta
    pasa a ser HOY (recontratación); sin él, se conserva la original
    (deshacer una baja dada por error).

    POST person_ids (uno o varios), rehire ("1" o vacío).
    """

    def post(self, request):
        person_ids = request.POST.getlist("person_ids")
        if not person_ids:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "No hay ningún trabajador seleccionado.",
                },
                status=400,
            )
        rehire_date = (
            timezone.localdate() if request.POST.get("rehire") == "1" else None
        )
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        reactivated_ids = []
        skipped_names = []
        moved_total = 0
        for person in PersonIdentity.objects.filter(pk__in=person_ids):
            if person.is_active_employee:
                skipped_names.append(_person_display_name(person))
                continue
            moved_total += _reactivate_person(
                person, rehire_date, person_ct, request.user.company_user,
            )
            reactivated_ids.append(person.pk)
        return JsonResponse({
            "ok": True,
            "reactivated_count": len(reactivated_ids),
            "reactivated_ids": reactivated_ids,
            "skipped_names": skipped_names,
            "moved_count": moved_total,
            "rehire": bool(rehire_date),
        })


class PersonGroupTemplateSaveView(DocsUploadAccessMixin, View):
    """
    H31 (S113). POST: crea un grupo nuevo (sin `group_pk`) o edita uno
    existente (renombrar y/o cambiar la composición) -- guarda con
    nombre el Set `selection` que ya acumula el frontend de
    `_personal_pane.html` (marcado entre filtros/páginas dentro de la
    misma sesión de navegador). Deliberadamente sin filtro de Company:
    el propio caso de uso (chalecos a choferes de varias empresas)
    exige poder mezclarlas en un mismo grupo.

    S147: grupos en árbol -- `parent_id` dice dentro de qué grupo va;
    las reglas (un grupo con subgrupos no tiene personas sueltas...)
    están en panel/person_groups.save_group. Devuelve el árbol pintado
    de nuevo (`tree_html`) además de los miembros del grupo guardado.
    """

    def post(self, request, group_pk=None):
        from django.template.loader import render_to_string

        from panel.person_groups import (
            GroupError, group_tree, parent_choices, save_group,
        )

        if group_pk:
            group = get_object_or_404(PersonGroupTemplate, pk=group_pk)
        else:
            group = PersonGroupTemplate(created_by=request.user.company_user)
        try:
            group, people = save_group(
                group, request.POST.get("name", ""),
                request.POST.get("parent_id", ""),
                request.POST.getlist("person_ids"),
                editor=request.user.company_user,
            )
        except GroupError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        return JsonResponse({
            "ok": True,
            "id": group.pk,
            "name": group.name,
            "members": [p.pk for p in people] if not
            group.children.exists() else [],
            "member_names": [
                "%s %s, %s" % (p.first_surname, p.second_surname, p.given_name)
                for p in people
            ] if not group.children.exists() else [],
            "tree_html": render_to_string(
                "panel/documentation_h30/_person_groups_tree.html",
                {"person_group_nodes": group_tree(
                    request.user.company_user)}, request=request,
            ),
            "parents": parent_choices(editor=request.user.company_user),
        })


class PersonGroupTemplateDeleteView(DocsUploadAccessMixin, View):
    """
    H31 (S113). POST: borra un grupo de selección -- nunca toca a las
    personas en sí, solo el conjunto guardado con nombre. S147: uno con
    subgrupos no se borra (primero sus subgrupos).
    """

    def post(self, request, group_pk):
        from django.template.loader import render_to_string

        from panel.person_groups import (
            GroupError, delete_group, group_tree, parent_choices,
        )

        group = get_object_or_404(PersonGroupTemplate, pk=group_pk)
        try:
            delete_group(group, editor=request.user.company_user)
        except GroupError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        return JsonResponse({
            "ok": True,
            "tree_html": render_to_string(
                "panel/documentation_h30/_person_groups_tree.html",
                {"person_group_nodes": group_tree(
                    request.user.company_user)}, request=request,
            ),
            "parents": parent_choices(editor=request.user.company_user),
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
                {
                    "ok": False,
                    "error": "Falta el tipo de circular/notificación.",
                },
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
                    errors.append(
                        {
                            "person_id": person_id,
                            "error": "Persona no encontrada.",
                        }
                    )
                    continue
                try:
                    eml_bytes, filename = _build_notification_eml(
                        person, document_type
                    )
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
                {
                    "ok": False,
                    "error": "Ninguna persona válida para el envío.",
                    "errors": errors,
                },
                status=400,
            )

        response = HttpResponse(
            zip_buffer.getvalue(), content_type="application/zip"
        )
        safe_type = type_code.lower()
        today = timezone.localdate().isoformat()
        response["Content-Disposition"] = (
            f'attachment; filename="notificaciones_masivas_{safe_type}_'
            f'{today}.zip"'
        )
        response["X-Mass-Created-Count"] = str(created_count)
        response["X-Mass-Errors"] = json.dumps(errors)
        return response


class PersonalNotificationWhatsAppMassView(DocsUploadAccessMixin, View):
    """
    H24 (S141). POST: send ONE circular by WhatsApp to the selected
    people (template circular_notification, button "Leer aquí").
    ---
    H24 (S141). POST: envía UNA circular por WhatsApp a los marcados
    (plantilla circular_notification: "Leer aquí" le contesta con el
    texto de la circular y la da por leída; también la ve en Mi buzón).
    Solo al teléfono de empresa (número 1). Cada envío correcto deja su
    DocumentAcknowledgment (canal WhatsApp); si Twilio falla no queda
    registrado y se dice por qué persona.
    """

    def post(self, request):
        from whatsapp.services import send_circular_notification_whatsapp
        from document_explorer.person_phone_service import mobile_of

        person_ids = request.POST.getlist("person_ids")
        type_code = request.POST.get("tipo", "").strip()
        if not person_ids or not type_code:
            return JsonResponse(
                {"ok": False,
                 "error": "Marca a alguien y elige la circular."},
                status=400,
            )
        document_type = get_object_or_404(
            DocumentTypeCatalog, code=type_code, is_active=True,
        )
        sent, errors = 0, []
        for person in PersonIdentity.objects.filter(pk__in=[
                pk for pk in person_ids if str(pk).isdigit()]):
            label = "%s %s" % (person.given_name, person.first_surname)
            if not mobile_of(person):
                errors.append("%s: sin teléfono de empresa" % label)
                continue
            ack = DocumentAcknowledgment.objects.create(
                person=person,
                document_type=document_type,
                delivery_date=timezone.localdate(),
                extraction_method=DocumentAcknowledgment.METHOD_MANUAL,
                channel=DocumentAcknowledgment.CHANNEL_WHATSAPP,
            )
            if send_circular_notification_whatsapp(ack):
                sent += 1
            else:
                ack.delete()
                errors.append("%s: no se ha podido enviar" % label)
        return JsonResponse({"ok": sent > 0, "sent": sent,
                             "errors": errors})


class DossierTemplateMissingCheckView(CompanyUserRequiredMixin, View):
    """
    H35 (S105). POST: para una plantilla y un conjunto de personas (la
    página visible del listado de Personal), devuelve qué personas NO
    tienen un documento vigente de TODOS los tipos incluidos en la
    plantilla -- Miguel Ángel, verbatim: "en la gestión de dossier,
    cuando estamos seleccionando para todos los trabajadores, hay que
    hacer un marcado en el listado de trabajadores que les falte algún
    documento de los que entran en la plantilla."

    Reutiliza `_resolve_template_entries` sin cambios -- el mismo
    criterio de "vigente ahora mismo" que ya usa la generación real
    del dosier, nunca una comprobación aparte que pudiera divergir.
    """

    def post(self, request):
        template_pk = request.POST.get("template_id", "").strip()
        person_ids = request.POST.getlist("person_ids")
        if not template_pk or not person_ids:
            return JsonResponse({"missing": []})

        template = get_object_or_404(PersonalDossierTemplate, pk=template_pk)
        required_type_ids = set(
            template.document_types.values_list("pk", flat=True),
        )
        if not required_type_ids:
            return JsonResponse({"missing": []})

        missing = []
        for person in PersonIdentity.objects.filter(pk__in=person_ids):
            entries = _resolve_template_entries(person, template)
            found_type_ids = {e.document_type_id for e in entries}
            if required_type_ids - found_type_ids:
                missing.append(person.pk)

        return JsonResponse({"missing": missing})


class CalendarTabFragmentView(CompanyUserRequiredMixin, View):
    """
    H31 (S94). Pestaña Calendario del hub de Documentación -- a
    petición de Miguel Ángel: quien lleva documentación/vacaciones
    necesita comprobar visualmente el efecto de un alta/edición/baja
    de VacationPeriod sin salir del hub. Reutiliza
    hr_calendar.views.build_calendar_context (misma lógica real que
    la página completa de Calendario, extraída a función compartida
    en esta misma sesión) -- nunca una copia paralela.

    CORREGIDO en la misma sesión (incidente real reportado por Miguel
    Ángel con captura de pantalla): el operario/periodo seleccionado
    no se recordaba entre visitas -- siempre volvía a alvarez_admin
    pese a haber seleccionado otro operario antes de salir del hub.
    Igual que las demás pestañas (mismo mecanismo, `_seed_request_get`
    + `filters.calendario` en PanelNavigationState), rellena
    `operator_pk`/`group_pk` desde el último valor guardado cuando la
    querystring real no los trae (carga inicial "load once").
    """

    def get(self, request):
        from hr_calendar.views import build_calendar_context

        nav_state = PanelNavigationState.objects.filter(
            company_user=request.user.company_user,
            screen_key="documentation_hub",
        ).first()
        _state = (
            nav_state.state
            if nav_state and isinstance(nav_state.state, dict) else {}
        )
        _persisted = (
            _state.get("filters", {}).get("calendario")
            if isinstance(_state.get("filters"), dict) else None
        )
        _seed_request_get(request, _persisted)

        ctx = build_calendar_context(request)
        return render(
            request, "panel/documentation_h30/_calendar_pane.html", ctx,
        )


class CalendarResultsFragmentView(CompanyUserRequiredMixin, View):
    """
    H31 (S94). Cambio de operario o navegación de periodo dentro de la
    pestaña Calendario -- solo repinta el bloque de resultados
    (selector de navegación de periodo + meses + leyenda), el
    selector de operario nunca se vuelve a pintar (mismo patrón que el
    resto de pestañas del hub).
    """

    def get(self, request):
        from hr_calendar.views import build_calendar_context

        ctx = build_calendar_context(request)
        return render(
            request, "panel/documentation_h30/_calendar_results.html", ctx,
        )


class DocumentViewView(CompanyUserRequiredMixin, View):
    """GET: redirige a la URL firmada (GCS) real del documento -- 'Ver'."""

    def get(self, request, pk):
        entry = get_object_or_404(
            DocumentIndexEntry, pk=pk, deleted_at__isnull=True,
        )
        # S147: confidencial (nómina): solo el trabajador y quien la
        # envió, descifrada aquí (nunca una URL firmada del cubo).
        if entry.is_confidential:
            from document_explorer.confidential import file_response

            return file_response(entry, request.user.company_user)
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


class DocumentChangeTypeView(DocsUploadAccessMixin, View):
    """
    H31 (S109). POST: corrige el `document_type` de UN documento ya
    indexado, sin tocar el archivo real ni su nombre (que se queda
    con el tipo con el que se subió originalmente -- el renombrado es
    solo virtual, mismo criterio que las campañas de retipado
    masivo). Nunca toca `blob_name`/`bucket` -- solo el campo
    `document_type`.

    Origen real: Miguel Ángel encontró un documento mal clasificado
    (una carta de baja voluntaria tipada como CONTRATO, por un falso
    positivo de la señal de contenido "CONTRATO DE TRABAJO" que la
    propia carta menciona de pasada en su cláusula de preaviso) y no
    encontró en ningún sitio del panel un mecanismo para corregir UN
    documento suelto sin montar una campaña completa de retipado por
    OCR en VMs -- verbatim: "no encuentro ni en la suya ni en la de
    ningún otro el mecanismo para poder cambiar el tipo de un
    documento".

    Deliberadamente genérico (`domain` -- personal o machine, ambos
    dominios comparten `DocumentIndexEntry`) para no duplicar esta
    vista cuando aparezca la misma necesidad en Centros de Gasto.
    """

    def post(self, request, pk):
        entry = get_object_or_404(
            DocumentIndexEntry, pk=pk, deleted_at__isnull=True,
        )
        new_type_code = request.POST.get("document_type_code", "").strip()
        if not new_type_code:
            return JsonResponse(
                {"ok": False, "error": "Falta el tipo documental nuevo."},
                status=400,
            )
        new_type = get_object_or_404(
            DocumentTypeCatalog, code=new_type_code, is_active=True,
        )
        # S130: cambio completo -- nombre canónico del tipo nuevo,
        # sustitución deshecha (tipo viejo) y aplicada (tipo nuevo) y,
        # en máquinas, los datos que acredita el tipo nuevo.
        from document_explorer.subject_upload_service import (
            change_document_type,
        )

        outcome = change_document_type(entry, new_type)
        check = outcome.get("check") or {}
        return JsonResponse({
            "ok": True, "new_type_label": new_type.label,
            "new_name": outcome["new_name"],
            "superseded_count": outcome["superseded_count"],
            "restored_count": outcome["restored_count"],
            "filled": check.get("filled") or {},
        })


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
        issue_date_str = request.POST.get("issue_date", "")
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

        # S123: fecha del documento (tipos sin caducidad, p. ej. la
        # fecha de inicio de un contrato), escrita en la ficha.
        typed_issue_date = None
        if issue_date_str and not document_type.tracks_expiry:
            try:
                typed_issue_date = datetime.strptime(
                    issue_date_str, "%Y-%m-%d",
                ).date()
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
                    typed_issue_date=typed_issue_date, check_content=True,
                )
            except SubjectUploadError as exc:
                errors.append({"file": uploaded_file.name, "error": str(exc)})
                continue
            # S123: la fecha con la que ha quedado el documento, para
            # decírselo al supervisor en el propio modal (Miguel Ángel:
            # "le das al botón y no sabemos lo que está ocurriendo").
            stored_entry = result["entry"]
            stored_date = stored_entry.expiry_date or stored_entry.issue_date
            entry_result = {
                "entry_id": stored_entry.pk,
                "entry_name": stored_entry.name,
                "superseded_count": result["superseded_count"],
                "date_label": (
                    stored_date.strftime("%d/%m/%Y") if stored_date else ""
                ),
                "date_kind": (
                    "caducidad" if stored_entry.expiry_date else "documento"
                ),
                # Solo se avisa de "sin fecha" donde la fecha importa:
                # tipos con caducidad y acumulables (contratos, altas,
                # bajas...), que se colocan por su fecha.
                "needs_date": bool(
                    document_type.tracks_expiry
                    or document_type.is_cumulative
                ),
            }
            # S130: comprobación del contenido (tipo y datos tomados).
            check = result.get("check") or {}
            if check.get("type_mismatch"):
                entry_result["type_mismatch"] = check["type_mismatch"]
            if check.get("filled"):
                entry_result["filled"] = check["filled"]
            if check.get("different"):
                entry_result["different"] = {
                    label: {"current": pair[0], "read": pair[1]}
                    for label, pair in check["different"].items()
                }
            if result["warning"]:
                entry_result["warning"] = {
                    "system_date": result["warning"][
                        "system_date"
                    ].isoformat(),
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
        tracks_expiry = request.POST.get("tracks_expiry") in (
            "true",
            "on",
            "1",
        )

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
