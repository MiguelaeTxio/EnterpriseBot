# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/required_documentation_service.py
"""
H31 (S119). Required-document status of a subject (person or
machine), driven entirely by their assigned JobPosition.
required_document_types -- never a hardcoded list of positions,
domains or type codes.
---
H31 (S119). Estado de los documentos obligatorios de un sujeto
(persona o máquina), según los tipos reales que exija el requisito de
documentación que tenga asignado EN ESTE MOMENTO -- nunca una lista de
puestos, dominios o códigos de tipo escrita en el código. Decisión de
Miguel Ángel, verbatim: "no se puede hardcodear nada, ni los grupos
que hay, ni los documentos [...] no sabemos qué grupos va a haber."

Origen -- incidente real S119: el aviso de "vigente caducada" se había
generalizado a CUALQUIER documento con `tracks_expiry=True` que la
persona tuviera, sin mirar si ese tipo era siquiera obligatorio para
su puesto. Resultado: una persona administrativa salía avisada de que
se le había caducado un CAP o un carnet de gruista que sacó en su día
y que su puesto actual no exige. Miguel Ángel, verbatim: "avisamos a
una persona que es administrativa [...] de que tiene caducado el CAP
[...] tenemos grupos hechos de requisitos documentales para avisar de
unos requisitos de documentación. Tenemos que ceñirnos a eso."

AMPLIADO S119: "los requisitos documentales no son ni para personas ni
para máquinas [...] la gestión de requisitos documentales es global
[...] ese requisito se asigna a una máquina, a una dependencia o a una
persona [...] no tenemos que tener un arreglo para máquinas y un
arreglo para personas." Un único catálogo (`JobPosition`), asignado
por `PersonIdentity.document_requirements` o por `MachineAsset.
document_requirements` -- esta función sirve a los dos sujetos con el
mismo cálculo, sin ninguna rama por dominio.

S153: VARIOS requisitos por sujeto (antes uno solo). Lo obligatorio es
la UNIÓN de los tipos y clases de permiso de sus requisitos activos;
un tipo que piden dos requisitos cuenta una sola vez.

Regla, para cada tipo del requisito asignado (nunca otro documento que
el sujeto tenga, exija o no su requisito):
- Si no existe ningún documento vivo de ese tipo -> falta.
- Si existe, se mira el MÁS MODERNO (por caducidad si la tiene, si no
  por emisión) -- deliberadamente sin pasar por `is_current()`, que
  excluye un documento caducado de la competición aunque sea el único
  que hay (incidente real: un tipo obligatorio con un solo documento
  ya caducado salía como "falta", nunca como "caducado", porque
  `is_current()` nunca lo consideraba vigente). Si ese tipo caduca
  (`tracks_expiry`) y el más moderno ya pasó su fecha -> caducado.
- DNI/NIE son excluyentes (mismo criterio ya usado en la ficha): tener
  cualquiera de los dos cubre el requisito de identidad del otro;
  cada uno de los que sí tiene se sigue comprobando por su cuenta.

AMPLIADO S120 -- permiso de conducción como matriz de clases
(`JobPosition.required_driving_categories`): cada clase exigida se
comprueba contra `DrivingLicenceGrant` del carné más reciente del
sujeto (falta si no está, caducada si su fecha pasó). Con clases
exigidas, `CARNET_CONDUCIR` solo cuenta para "falta", nunca para
"caducado" (decisión 1 de Miguel Ángel, S120). Los avisos de clases
van a la familia del propio tipo `CARNET_CONDUCIR` en el catálogo.
"""
from dataclasses import dataclass
from datetime import date

from django.contrib.contenttypes.models import ContentType

BUCKET = "cgs_grupo_alvarez"
IDENTITY_CODES = ("DNI", "NIE")
DRIVING_CARD_CODE = "CARNET_CONDUCIR"


@dataclass(frozen=True)
class RequiredDrivingCategory:
    """
    A missing driving licence class, shaped like a DocumentTypeCatalog
    for the templates (`.label`, `str()`).
    ---
    H30 (S120). Clase de permiso exigida que falta -- con la misma
    forma que un `DocumentTypeCatalog` para las plantillas y los
    títulos que ya pintan `dt.label` o `join` sobre la lista de
    faltantes, sin tocar ese contrato.
    """

    label: str

    def __str__(self):
        return self.label


def get_requirements(subject):
    """
    Return the active JobPositions assigned to this subject.
    ---
    S153. Requisitos ACTIVOS asignados al sujeto
    (`PersonIdentity.document_requirements` o `MachineAsset.
    document_requirements`), ordenados por nombre; lista vacía si no
    tiene ninguno. S128: un requisito desactivado no genera avisos --
    para todo lo que pasa por este servicio es como no tenerlo. Lee
    `.all()` para aprovechar un `prefetch_related` del llamador.
    """
    manager = getattr(subject, "document_requirements", None)
    if manager is None or subject.pk is None:
        return []
    return sorted(
        (req for req in manager.all() if req.is_active),
        key=lambda req: req.name,
    )


def required_driving_categories(subject):
    """
    Union of the licence classes required by the subject's
    requirements, in catalog order.
    ---
    S153. Unión de las clases de permiso que exigen los requisitos
    activos del sujeto, sin repetir, en el orden del catálogo.
    """
    by_pk = {}
    for requirement in get_requirements(subject):
        for category in requirement.required_driving_categories.all():
            by_pk[category.pk] = category
    return sorted(
        by_pk.values(),
        key=lambda category: (category.display_order, category.pk),
    )


def latest_driving_card(cards, card_ids_with_grants=frozenset()):
    """
    Return the most recent driving licence card entry, or None.
    ---
    H30 (S120). Carné más reciente de una lista de entradas
    `CARNET_CONDUCIR` -- mismo criterio que el resto del servicio
    (caducidad si la tiene, si no emisión), desempate por pk. Las
    clases vigentes se leen SIEMPRE de un único carné, nunca mezclando
    carnés distintos (decisión S120).

    Se elige entre los carnés CON matriz registrada
    (`card_ids_with_grants`): anverso y reverso vienen a menudo en
    archivos separados y solo el reverso lleva las clases -- un anverso
    más reciente nunca debe tapar la matriz de su propio reverso. Solo
    si ningún carné tiene matriz se devuelve el más reciente de todos
    (para el aviso "clases del carné sin registrar").
    """
    if not cards:
        return None
    with_grants = [
        entry for entry in cards if entry.pk in card_ids_with_grants
    ]
    return max(
        with_grants or cards,
        key=lambda entry: (
            entry.expiry_date or entry.issue_date or date.min, entry.pk,
        ),
    )


def evaluate_driving_categories(required_categories, card, grants, today):
    """
    Return (missing, expired) labels for the required licence classes.
    ---
    H30 (S120). Comprueba cada clase exigida contra la matriz del
    carné vigente (`card`, puede ser None) y sus clases (`grants`,
    `DrivingLicenceGrant` de ESE carné). Devuelve (faltantes,
    caducadas): faltantes como `RequiredDrivingCategory`, caducadas
    como texto "Permiso de conducción C — caducó el dd/mm/aaaa".
    Sin concesiones automáticas (art. 5.2 RGC): la DGT imprime en el
    carné todas las clases que el titular tiene, así que la matriz
    recoge ya la verdad legal (decisión S120).
    """
    missing, expired = [], []
    grants_by_code = {grant.category.code: grant for grant in grants}
    for category in required_categories:
        label = "Permiso de conducción %s" % category.code
        grant = grants_by_code.get(category.code)
        if grant is None:
            if card is not None and not grants_by_code:
                label += " (clases del carné sin registrar)"
            missing.append(RequiredDrivingCategory(label))
            continue
        if grant.expiry_date and grant.expiry_date < today:
            expired.append(
                "%s — caducó el %s" % (
                    label, grant.expiry_date.strftime("%d/%m/%Y"),
                ),
            )
    return missing, expired


def driving_card_family():
    """
    Return the family code of CARNET_CONDUCIR (where class alerts go).
    ---
    H30 (S120). Familia del tipo `CARNET_CONDUCIR` en el catálogo --
    los avisos de clases se pintan en la misma familia que el carné,
    leída del catálogo, nunca fijada en el código.
    """
    from document_explorer.models import DocumentTypeCatalog

    return DocumentTypeCatalog.objects.filter(
        code=DRIVING_CARD_CODE,
    ).values_list("family", flat=True).first() or ""


def get_required_type_ids(subject):
    """
    Return the frozenset of DocumentTypeCatalog pks required for this
    subject right now, or an empty frozenset if none assigned.
    ---
    H30 (S119). Devuelve el conjunto de pk de `DocumentTypeCatalog`
    exigidos ahora mismo por los requisitos de documentación de
    `subject` (S153: la unión de todos los activos), vacío si no tiene
    ninguno asignado. Único punto de esta lectura -- lo usan tanto
    `resolve_required_document_status` como `vigencia_selector.
    current_fn_for` (vía sus llamadores), para que los dos calculen
    "obligatorio para este sujeto" exactamente igual.
    """
    return frozenset(
        dt.pk for requirement in get_requirements(subject)
        for dt in requirement.required_document_types.all()
    )


def resolve_required_document_status(subject):
    """
    Return (missing_by_family, expired_by_family) for this subject.
    ---
    Devuelve (faltantes_por_familia, caducados_por_familia) -- dicts
    `family_code -> [DocumentTypeCatalog, ...]` (faltantes) y
    `family_code -> [str label, ...]` (caducados), listos para el
    mismo contrato de plantilla que ya usan las fichas. `subject` es
    una `PersonIdentity` o un `MachineAsset` (los dos con
    `document_requirements`, mismo catálogo `JobPosition`). Sin ningún
    requisito asignado, los dos salen vacíos -- ningún tipo es
    obligatorio.
    """
    from document_explorer.models import (
        DocumentIndexEntry, DocumentTypeCatalog,
    )

    from document_explorer.models import DrivingLicenceGrant

    missing_by_family = {}
    expired_by_family = {}
    required_categories = required_driving_categories(subject)
    required_type_ids = get_required_type_ids(subject)
    if not required_type_ids and not required_categories:
        return missing_by_family, expired_by_family
    required_types = list(
        DocumentTypeCatalog.objects.filter(pk__in=required_type_ids),
    )

    ct = ContentType.objects.get_for_model(type(subject))
    today = date.today()
    if required_categories:
        cards = list(DocumentIndexEntry.objects.filter(
            bucket=BUCKET, domain_content_type=ct,
            domain_object_id=subject.pk,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            document_type__code=DRIVING_CARD_CODE,
        ))
        all_grants = list(DrivingLicenceGrant.objects.filter(
            entry__in=cards,
        ).select_related("category"))
        card = latest_driving_card(
            cards, frozenset(grant.entry_id for grant in all_grants),
        )
        grants = [
            grant for grant in all_grants
            if card is not None and grant.entry_id == card.pk
        ]
        category_missing, category_expired = evaluate_driving_categories(
            required_categories, card, grants, today,
        )
        family = driving_card_family()
        if category_missing:
            missing_by_family.setdefault(family, []).extend(
                category_missing,
            )
        if category_expired:
            expired_by_family.setdefault(family, []).extend(
                category_expired,
            )
    entries = DocumentIndexEntry.objects.filter(
        bucket=BUCKET, domain_content_type=ct, domain_object_id=subject.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
        document_type_id__in=[dt.pk for dt in required_types],
    ).select_related("document_type")

    docs_by_type_id = {}
    for entry in entries:
        docs_by_type_id.setdefault(entry.document_type_id, []).append(entry)
    present_codes = {
        entry.document_type.code
        for group in docs_by_type_id.values() for entry in group
    }
    has_identity_doc = bool(set(IDENTITY_CODES) & present_codes)

    for document_type in required_types:
        docs = docs_by_type_id.get(document_type.pk, [])
        if not docs:
            if document_type.code in IDENTITY_CODES and has_identity_doc:
                continue
            missing_by_family.setdefault(
                document_type.family, [],
            ).append(document_type)
            continue
        most_recent = max(
            docs,
            key=lambda entry: entry.expiry_date or entry.issue_date
            or date.min,
        )
        # S120 (decisión 1 de Miguel Ángel): si el requisito exige
        # clases concretas, CARNET_CONDUCIR solo cuenta para "falta"
        # -- la caducidad la deciden las clases, nunca la fecha única
        # del documento.
        if (
            document_type.code == DRIVING_CARD_CODE
            and required_categories
        ):
            continue
        if (
            document_type.tracks_expiry
            and most_recent.expiry_date
            and most_recent.expiry_date < today
        ):
            expired_by_family.setdefault(
                document_type.family, [],
            ).append(
                "%s — caducó el %s" % (
                    document_type.label,
                    most_recent.expiry_date.strftime("%d/%m/%Y"),
                ),
            )
    return missing_by_family, expired_by_family


def attach_driving_grants(entries, subject):
    """
    Attach the class matrix to every driving licence card in entries.
    ---
    H30 (S120). Cuelga de cada entrada `CARNET_CONDUCIR` de `entries`
    su matriz de clases (`entry.driving_grants`, ordenada como el
    catálogo), con dos atributos Python por clase, nunca de BD:
    `is_expired` (su fecha ya pasó) e `is_required_expired` (además
    la exige el requisito del sujeto -- lo que la ficha pinta en
    rojo). Plantillas tontas: la decisión se toma aquí, la plantilla
    solo pinta. Una sola consulta para todos los carnés.
    """
    from document_explorer.models import DrivingLicenceGrant

    cards = [
        entry for entry in entries
        if entry.document_type_id
        and entry.document_type.code == DRIVING_CARD_CODE
    ]
    if not cards:
        return entries
    required_codes = {
        category.code for category in required_driving_categories(subject)
    }
    today = date.today()
    grants_by_card = {}
    for grant in DrivingLicenceGrant.objects.filter(
        entry__in=cards,
    ).select_related("category").order_by("category__display_order"):
        grant.is_expired = bool(
            grant.expiry_date and grant.expiry_date < today,
        )
        grant.is_required_expired = (
            grant.is_expired and grant.category.code in required_codes
        )
        grants_by_card.setdefault(grant.entry_id, []).append(grant)
    for card in cards:
        card.is_driving_card = True
        card.driving_grants = grants_by_card.get(card.pk, [])
    return entries


def attach_subtype_documents(entries, current, obsolete):
    """
    Move subtype documents under their parent's current document.
    ---
    H30 (S120). Documentos de un SUBTIPO (`DocumentTypeCatalog.
    parent_type`, p. ej. la autorización temporal de la DGT, subtipo
    del permiso de conducción): se sacan de las listas `current` y
    `obsolete` y se cuelgan de la entrada vigente MÁS RECIENTE del tipo
    padre (`parent.subtype_documents`, del más nuevo al más viejo),
    para pintarlos dentro de su fila. Si la persona no tiene ningún
    documento vigente del padre, el documento del subtipo se queda
    donde estaba -- nunca desaparece de la ficha. Devuelve
    (current, obsolete) ya filtradas.
    """
    # H30 (S122): con un padre ACUMULABLE (varios vigentes a la vez --
    # contratos) el subtipo se cuelga del documento del padre más
    # reciente ANTERIOR (o igual) a su propia fecha -- la prórroga del
    # contrato que alarga, nunca siempre del último contrato. Sin fecha
    # en el subtipo, o sin ningún padre anterior, el más reciente de
    # todos (criterio de S120, que es el único posible con un padre no
    # acumulable: solo hay un vigente).
    def _date_key(item):
        return (item.expiry_date or item.issue_date or date.min, item.pk)

    parents_by_type = {}
    for entry in current:
        if not entry.document_type_id:
            continue
        parents_by_type.setdefault(entry.document_type_id, []).append(entry)
    for group in parents_by_type.values():
        group.sort(key=lambda item: (item.issue_date or date.min, item.pk))

    def _parent_for(entry, candidates):
        latest = max(candidates, key=_date_key)
        if not entry.issue_date:
            return latest
        earlier = [
            candidate for candidate in candidates
            if candidate.issue_date
            and candidate.issue_date <= entry.issue_date
        ]
        return earlier[-1] if earlier else latest

    moved = set()
    for entry in sorted(entries, key=lambda item: item.pk, reverse=True):
        document_type = entry.document_type
        if document_type is None or not document_type.parent_type_id:
            continue
        candidates = parents_by_type.get(document_type.parent_type_id)
        if not candidates:
            continue
        parent = _parent_for(entry, candidates)
        if not hasattr(parent, "subtype_documents"):
            parent.subtype_documents = []
        parent.subtype_documents.append(entry)
        moved.add(entry.pk)
    if not moved:
        return current, obsolete
    return (
        [entry for entry in current if entry.pk not in moved],
        [entry for entry in obsolete if entry.pk not in moved],
    )


MASS_ADD = "add"
MASS_REMOVE = "remove"


def bulk_change_requirements(subject_model, subject_ids, mode, requirement):
    """
    Add or remove one requirement (or all, removing) on many subjects.
    ---
    S153. Asignación masiva de requisitos con varios por sujeto
    (personas o centros de gasto, mismo catálogo): `MASS_ADD` añade
    `requirement` a cada sujeto sin tocar los que ya tenga;
    `MASS_REMOVE` se lo quita, o quita TODOS si `requirement` es None.
    Antes (un solo requisito) asignar sustituía al anterior. Devuelve
    cuántos sujetos se han tocado de verdad.
    """
    from django.db import transaction

    through = subject_model.document_requirements.through
    source = "%s_id" % subject_model._meta.model_name
    ids = set(
        subject_model.objects.filter(pk__in=subject_ids).values_list(
            "pk", flat=True,
        ),
    )
    links = through.objects.filter(**{"%s__in" % source: ids})
    with transaction.atomic():
        if mode == MASS_ADD:
            have = set(links.filter(jobposition=requirement).values_list(
                source, flat=True,
            ))
            missing = sorted(ids - have)
            through.objects.bulk_create([
                through(**{source: pk, "jobposition_id": requirement.pk})
                for pk in missing
            ])
            return len(missing)
        if requirement is not None:
            links = links.filter(jobposition=requirement)
        touched = len(set(links.values_list(source, flat=True)))
        links.delete()
        return touched
