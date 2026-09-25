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
"""
from datetime import date

from django.contrib.contenttypes.models import ContentType

BUCKET = "cgs_grupo_alvarez"
IDENTITY_CODES = ("DNI", "NIE")


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
    requirement = (
        getattr(subject, "job_position", None)
        or getattr(subject, "document_requirement", None)
    )
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

    missing_by_family = {}
    expired_by_family = {}
    required_type_ids = get_required_type_ids(subject)
    if not required_type_ids:
        return missing_by_family, expired_by_family
    required_types = list(
        DocumentTypeCatalog.objects.filter(pk__in=required_type_ids),
    )

    ct = ContentType.objects.get_for_model(type(subject))
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

    today = date.today()
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
        if (
            document_type.tracks_expiry
            and most_recent.expiry_date
            and most_recent.expiry_date < today
        ):
            expired_by_family.setdefault(
                document_type.family, [],
            ).append(document_type.label)
    return missing_by_family, expired_by_family
