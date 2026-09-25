# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/vigencia_selector.py
"""
H30 (S119). Picks the currency rule for a document by type.
---
Elige el criterio de vigencia de un documento según su tipo -- un
único punto de decisión para la ficha (`_split_current_obsolete`), la
subida desde la ficha (`subject_upload_service`) y el recálculo
(`recalculate_machine_vigencia`), para que nunca se contradigan.

Decisión de Miguel Ángel (S119, opción 1, generalizada tras el
incidente real de Manuel Alonso -- id=34037,
AUTORIZACION_TEMPORAL_CONDUCIR, caducado y único de su tipo, sin
ningún sustituto): con `is_current` a secas, un documento caducado sin
sustituto simplemente desaparece de la ficha (nunca es "vigente", así
que nunca dispara `needs_attention`) -- el listado, que sí mira el
campo `is_obsolete` en crudo, lo marcaba, y la ficha no, sin que nadie
pudiera saber por qué. Miguel Ángel, verbatim: "necesitamos saber los
documentos caducados, no que se oculten y no saber que lo están."

Por eso `is_current_expiring` (la "vigente caducada": si nadie lo
sustituye, el caducado se sigue mostrando como vigente, en rojo) se
aplica ahora a CUALQUIER tipo que caduque, sea de máquina o de
Personal -- ya no depende del dominio. `is_current` sigue para los
tipos que no caducan (`tracks_expiry=False`), donde la caducidad no
pinta nada.
"""
from document_management.vigencia_service import (
    is_current,
    is_current_expiring,
)


def current_fn_for(document_type, domain_content_type_id):
    """
    Return the currency function for this document type.
    ---
    Devuelve la función de vigencia para este tipo de documento.
    `domain_content_type_id` ya no distingue nada -- se conserva en la
    firma porque `_split_current_obsolete`, `subject_upload_service` y
    `recalculate_machine_vigencia` ya lo pasan.
    """
    if document_type is None or not document_type.tracks_expiry:
        return is_current
    return is_current_expiring
