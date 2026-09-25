# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/vigencia_selector.py
"""
H30 (S119). Picks the currency rule for a document by type and domain.
---
Elige el criterio de vigencia de un documento según su tipo y su
dominio -- un único punto de decisión para la ficha
(`_split_current_obsolete`), la subida desde la ficha
(`subject_upload_service`) y el recálculo
(`recalculate_machine_vigencia`), para que nunca se contradigan.

REVERTIDO el mismo día: se generalizó `is_current_expiring` a
CUALQUIER tipo con `tracks_expiry=True`, sin comprobar tipo a tipo si
la caducidad de Personal era fiable (mismo error que la sesión ya
había corregido para máquinas: decidir sin mirar la muestra real).
Medido con consulta real tras el incidente de Manuel Alonso: 10 tipos
de Personal tienen el 100% de sus caducidades ya pasadas, y varios
(ALTA: 26 de 55; BAJA_PERSONAL: 1 de 11) la tienen ANTERIOR a la
propia emisión -- ese campo no es una caducidad real renovable para
esos tipos, es dato de extracción no fiable o un campo mal usado.
Generalizar sin decisión por tipo llenó fichas de Personal de avisos
falsos ("vigente caducada") en producción.

Decisión de Miguel Ángel (S119, opción 1): los tipos que caducan en
MÁQUINAS usan `is_current_expiring`; Personal sigue con `is_current`
hasta decidir, tipo por tipo con muestra real, cuáles necesitan de
verdad la "vigente caducada" (candidatos claros: CARNET_GRUISTA, CAP
-- sí caducan de verdad; ALTA, BAJA_PERSONAL -- no, su caducidad no es
fiable).
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
