# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/docs_core.py
"""
Document rules of the person and machine record, for the new interface.

---

Reglas de documentos de la ficha de persona y máquina para la nueva
interfaz (S163): COPIA de las funciones de panel/views_documentation_h30.py
que usa (vigencia de la ficha, periodos de contratación, accesorios
entregados, renombrado de documentos al cambiar el nombre, empresas del
filtro). La nueva interfaz no llama a la antigua: se puede borrar
cualquiera de las dos sin romper la otra. Un cambio de regla en una no
llega sola a la otra (Miguel Ángel, S163).
"""

import logging
from datetime import date

from django.contrib.contenttypes.models import ContentType

from document_explorer import lifting_accessory_service as service
from document_explorer.models import (
    LIFTING_ACCESSORY_REVIEW_MONTHS, DocumentIndexEntry, DocumentTypeCatalog,
    PersonIdentity, add_months,
)
from document_explorer.vigencia_selector import current_fn_for
from document_management.vigencia_service import DocumentSnapshot

logger = logging.getLogger(__name__)

BUCKET = "cgs_grupo_alvarez"



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
    # S153 (Miguel Ángel): Geogrúas, CIF B93654010, carpeta local GEO.
    ("geogruas", "Geogrúas S.L.", ["GEOGRUAS SL"]),
    ("sin_empresa", "Sin empresa asignada", [""]),
]


# S146 (Miguel Ángel): "hay que preguntar a qué empresa va y sacar el
# desplegable de empresas posibles" -- nada de escribirla a mano
# (Transgrual, TRANSGRUAL, Grualdi, GRUALDI S.L....). En el alta se
# guarda siempre el texto canónico de cada empresa (el primero de su
# lista en COMPANY_FILTER_CHOICES), que es el que reconoce también el
# código de su carpeta local (TR, GR, GL, AGG, GEO).


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


def _person_employment_periods(person, entries=None):
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

    by_code = {code: [] for code in periods.PERIOD_CODES}
    if entries is None:
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        entries = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, domain_content_type=person_ct,
            domain_object_id=person.pk,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            # S125: un obsoleto (duplicado exacto, carpeta "obsoleto")
            # no es un periodo -- salía como "Alta sin fecha".
            is_obsolete=False,
            document_type__code__in=periods.PERIOD_CODES,
        ).select_related("document_type")
    else:
        # S163: los documentos ya cargados del trabajador (listados de la
        # nueva interfaz), filtrados con el mismo criterio.
        entries = [
            entry for entry in entries
            if not entry.is_obsolete and entry.deleted_at is None
            and entry.purged_at is None and entry.document_type_id
            and entry.document_type.code in periods.PERIOD_CODES
        ]
    for entry in entries:
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
    return _annotate(accessories_for_person(person, company))


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


# Copia de panel/views_lifting_accessories.py (_person_label, _annotate).
def _person_label(person):
    """
    "Surnames, Name" of a worker (never the ID number).
    ---
    "Apellidos, Nombre" de un trabajador (nunca el DNI).
    """
    if person is None:
        return ""
    surnames = " ".join(
        p for p in (person.first_surname, person.second_surname) if p
    )
    return "%s, %s" % (surnames, person.given_name)


def _annotate(accessories):
    """
    Attach the derived data every screen shows: current machine and
    responsible, last review, effective expiry and the expired flag.
    ---
    Añade los datos derivados que pinta cada pantalla: máquina y
    responsable actuales, última revisión, caducidad efectiva y aviso
    de caducado. Una consulta por relación (prefetch), nunca por fila.
    """
    today = date.today()
    accessories = list(accessories.select_related(
        "accessory_type", "model",
    ).prefetch_related(
        "assignments__machine", "assignments__responsible_person",
        "reviews",
    ))
    certificates = service.certificates_of(accessories)
    for accessory in accessories:
        accessory.certificates = certificates.get(accessory.pk, [])
        accessory.has_certificate = bool(accessory.certificates)
        open_assignments = [
            a for a in accessory.assignments.all() if a.end_date is None
        ]
        current = max(
            open_assignments, key=lambda a: (a.start_date, a.pk),
            default=None,
        )
        reviews = list(accessory.reviews.all())
        last_review = max(
            reviews, key=lambda r: (r.review_date, r.pk), default=None,
        )
        accessory.current_assignment_row = current
        accessory.current_machine = current.machine if current else None
        accessory.responsible_label = _person_label(
            current.responsible_person if current else None,
        )
        accessory.last_review_date = (
            last_review.review_date if last_review else None
        )
        if last_review is not None:
            accessory.expiry = last_review.expiry_date
        elif accessory.supply_date:
            accessory.expiry = add_months(
                accessory.supply_date, LIFTING_ACCESSORY_REVIEW_MONTHS,
            )
        else:
            accessory.expiry = None
        accessory.is_expired = bool(
            accessory.is_active and accessory.expiry
            and accessory.expiry < today
        )
    return accessories


# Copia de fleet/views.py (_short_company_name).
def short_company_name(company_name):
    """
    "GRUAS ADOLFO ALVAREZ, S.L. CIF B29405040" -> "GRUAS ADOLFO ALVAREZ".

    ---

    Forma corta del nombre de empresa (como la columna EMPRESA del Excel).
    """
    name = (company_name or "").strip()
    for separator in (",", " CIF"):
        if separator in name:
            name = name.split(separator, 1)[0]
    return name.strip()
