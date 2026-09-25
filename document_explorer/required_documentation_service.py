# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/required_documentation_service.py
"""
H31 (S119). Required-document status of a person, driven entirely by
their JobPosition.required_document_types -- never a hardcoded list
of positions or type codes.
---
H31 (S119). Estado de los documentos obligatorios de una persona,
según los tipos reales que exija su `JobPosition.required_document_types`
EN ESTE MOMENTO -- nunca una lista de puestos o de códigos de tipo
escrita en el código. Decisión de Miguel Ángel, verbatim: "no se puede
hardcodear nada, ni los grupos que hay, ni los documentos [...] no
sabemos qué grupos va a haber."

Origen -- incidente real S119: el aviso de "vigente caducada" se había
generalizado a CUALQUIER documento con `tracks_expiry=True` que la
persona tuviera, sin mirar si ese tipo era siquiera obligatorio para
su puesto. Resultado: una persona administrativa salía avisada de que
se le había caducado un CAP o un carnet de gruista que sacó en su día
y que su puesto actual no exige. Miguel Ángel, verbatim: "avisamos a
una persona que es administrativa [...] de que tiene caducado el CAP
[...] tenemos grupos hechos de requisitos documentales para avisar de
unos requisitos de documentación. Tenemos que ceñirnos a eso."

Regla, para cada tipo del requisito del puesto (nunca otro documento
que la persona tenga, exija o no su puesto):
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


def resolve_required_document_status(person):
    """
    Return (missing_by_family, expired_by_family) for this person.
    ---
    Devuelve (faltantes_por_familia, caducados_por_familia) -- dicts
    `family_code -> [DocumentTypeCatalog, ...]` (faltantes) y
    `family_code -> [str label, ...]` (caducados), listos para el
    mismo contrato de plantilla que ya usan las fichas. Sin puesto
    asignado, los dos salen vacíos -- ningún tipo es obligatorio.
    """
    from document_explorer.models import DocumentIndexEntry, PersonIdentity

    missing_by_family = {}
    expired_by_family = {}
    if not person.job_position_id:
        return missing_by_family, expired_by_family

    required_types = list(
        person.job_position.required_document_types.all(),
    )
    if not required_types:
        return missing_by_family, expired_by_family

    ct = ContentType.objects.get_for_model(PersonIdentity)
    entries = DocumentIndexEntry.objects.filter(
        bucket=BUCKET, domain_content_type=ct, domain_object_id=person.pk,
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
