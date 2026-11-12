# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/vigencia_selector.py
"""
H30 (S119). Picks the currency rule for a document by type, scoped to
whether that type is REQUIRED for the specific subject being viewed.
---
Elige el criterio de vigencia de un documento según su tipo -- un
único punto de decisión para la ficha (`_split_current_obsolete`), la
subida desde la ficha (`subject_upload_service`) y el recálculo
(`recalculate_machine_vigencia`), para que nunca se contradigan.

HISTORIA REAL de esta decisión, en dos pasos equivocados y el
correcto:

1. Por dominio (S119, opción 1 original): `is_current_expiring` para
   MachineAsset, `is_current` para el resto. Corregido el mismo día:
   sin mirar el requisito, cualquier documento único y caducado de
   máquina se mostraba como "vigente caducado" -- incluso en tipos
   nunca exigidos a esa máquina en concreto.
2. Por tracks_expiry a secas, para TODOS los dominios (mismo día,
   revertido en menos de una hora): generalizar sin comprobar tipo a
   tipo llenó fichas de Personal de avisos falsos -- 10 tipos de
   Personal (ALTA, BAJA_PERSONAL...) tienen el 100% de sus caducidades
   ya pasadas y varias ANTERIORES a la propia emisión, dato de
   extracción no fiable, no una caducidad real.
3. CORRECTO (incidente real de Alberto Javier Álvarez Díaz, reportado
   por Miguel Ángel): ninguno de los dos pasos anteriores miraba lo
   único que importa. Miguel Ángel, verbatim: "los badges deben de
   aparecer cuando un requisito de documentación no se cumple [...] si
   no hay requisito de documentación, no debe mostrar absolutamente
   ningún aviso [...] si tiene un requisito con dos documentos
   obligatorios, si tiene el DNI y está caducado, tendrá que decir que
   está caducado. Y si no lo tiene, tendrá que decir que falta." Esto
   aplica exactamente igual a una persona que a una máquina -- nunca
   depende del dominio, depende únicamente de si ESE tipo, para ESE
   sujeto en concreto, está en su requisito de documentación asignado
   ahora mismo (`PersonIdentity.document_requirements` o `MachineAsset.
   document_requirements`, mismo catálogo único `JobPosition`; S153:
   la unión de todos sus requisitos activos).

Consecuencia real del error, antes de esta corrección: un tipo
obligatorio caducado y sin sustituto perdía la competición de
`is_current()` (que excluye de raíz cualquier candidato ya caducado,
tenga o no sustituto) y desaparecía por completo de la tabla de
documentos de su familia -- el aviso de "Caducado: X" salía en la
cabecera (ya corregido antes, `required_documentation_service`, que
nunca pasa por `is_current()`), pero la fila que debía mostrarlo en
rojo, con su fecha, sencillamente no existía en ningún sitio visible.
En máquinas no pasaba porque `is_current_expiring` (por dominio, sin
mirar si era obligatorio) ya lo colaba como vigente por otra vía --
por eso parecía "funcionar bien" en Centros de Gasto, cuando en
realidad tampoco miraba el requisito, solo tapaba el síntoma con un
criterio igual de equivocado en la dirección contraria.
"""
from document_management.vigencia_service import (
    is_current,
    is_current_expiring,
)


def current_fn_for(document_type, required_type_ids):
    """
    Return the currency function for this document type.
    ---
    Devuelve la función de vigencia para este tipo de documento.
    `required_type_ids` es el conjunto de pk de `DocumentTypeCatalog`
    exigidos AHORA MISMO por el requisito de documentación del sujeto
    concreto que se está mirando (vacío si no tiene ninguno asignado)
    -- nunca un criterio fijo por dominio ni por tipo. Si el tipo no
    caduca (`tracks_expiry=False`), la caducidad no pinta nada y da
    igual si es obligatorio o no.
    """
    if document_type is None or not document_type.tracks_expiry:
        return is_current
    if required_type_ids and document_type.pk in required_type_ids:
        return is_current_expiring
    return is_current
