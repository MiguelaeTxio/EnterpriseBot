# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/vigencia_selector.py
"""
H30 (S119). Picks the currency rule for a document by type and domain.
---
Elige el criterio de vigencia de un documento según su tipo y su
dominio -- un único punto de decisión para la ficha
(`_split_current_obsolete`), la subida desde la ficha
(`subject_upload_service`) y el recálculo
(`recalculate_machine_vigencia`), para que nunca se contradigan.

Decisión de Miguel Ángel (S119, opción 1): los tipos que caducan en
MÁQUINAS usan `is_current_expiring`; todo lo demás (incluido Personal)
sigue con `is_current`, sin ningún cambio.
"""
from django.contrib.contenttypes.models import ContentType

from document_management.vigencia_service import (
    is_current,
    is_current_expiring,
)


def current_fn_for(document_type, domain_content_type_id):
    """
    Return the currency function for this type and domain.
    ---
    Devuelve la función de vigencia para este tipo y dominio.
    """
    from fleet.models import MachineAsset

    if document_type is None or not document_type.tracks_expiry:
        return is_current
    machine_ct_id = ContentType.objects.get_for_model(MachineAsset).id
    if domain_content_type_id == machine_ct_id:
        return is_current_expiring
    return is_current
