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
por `PersonIdentity.job_position` o por `MachineAsset.
document_requirement` -- esta función sirve a los dos sujetos con el
mismo cálculo, sin ninguna rama por dominio.

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


def get_requirement(subject):
    """
    Return the JobPosition assigned to this subject, or None.
    ---
    H30 (S120). Requisito asignado al sujeto
    (`PersonIdentity.job_position` o `MachineAsset.
    document_requirement`), o None.
    """
    return (
        getattr(subject, "job_position", None)
        or getattr(subject, "document_requirement", None)
    )


def latest_driving_card(cards):
    """
    Return the most recent driving licence card entry, or None.
    ---
    H30 (S120). Carné más reciente de una lista de entradas
    `CARNET_CONDUCIR` -- mismo criterio que el resto del servicio
    (caducidad si la tiene, si no emisión), desempate por pk. Las
    clases vigentes se leen SIEMPRE de este carné, nunca mezclando
    carnés distintos (decisión S120).
    """
    if not cards:
        return None
    return max(
        cards,
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
    exigidos ahora mismo por el requisito de documentación de `subject`
    (`PersonIdentity.job_position` o `MachineAsset.document_requirement`
    -- mismo catálogo único `JobPosition`), vacío si no tiene ninguno
    asignado. Único punto de esta lectura -- lo usan tanto
    `resolve_required_document_status` como `vigencia_selector.
    current_fn_for` (vía sus llamadores), para que los dos calculen
    "obligatorio para este sujeto" exactamente igual.
    """
    requirement = get_requirement(subject)
    if requirement is None:
        return frozenset()
    return frozenset(
        requirement.required_document_types.values_list("pk", flat=True),
    )


def resolve_required_document_status(subject):
    """
    Return (missing_by_family, expired_by_family) for this subject.
    ---
    Devuelve (faltantes_por_familia, caducados_por_familia) -- dicts
    `family_code -> [DocumentTypeCatalog, ...]` (faltantes) y
    `family_code -> [str label, ...]` (caducados), listos para el
    mismo contrato de plantilla que ya usan las fichas. `subject` es
    una `PersonIdentity` (usa `job_position`) o un `MachineAsset` (usa
    `document_requirement`) -- ambos FK al mismo catálogo
    `JobPosition`. Sin ningún requisito asignado, los dos salen
    vacíos -- ningún tipo es obligatorio.
    """
    from document_explorer.models import (
        DocumentIndexEntry, DocumentTypeCatalog,
    )

    from document_explorer.models import DrivingLicenceGrant

    missing_by_family = {}
    expired_by_family = {}
    requirement = get_requirement(subject)
    required_categories = (
        list(requirement.required_driving_categories.all())
        if requirement is not None else []
    )
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
        card = latest_driving_card(cards)
        grants = (
            list(DrivingLicenceGrant.objects.filter(
                entry=card,
            ).select_related("category"))
            if card is not None else []
        )
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
    requirement = get_requirement(subject)
    required_codes = (
        set(requirement.required_driving_categories.values_list(
            "code", flat=True,
        ))
        if requirement is not None else set()
    )
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
