# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/buckets.py
"""
Which buckets the explorer indexes, and how each maps to a domain
model.

`spare_parts.gcs_service.ALL_BUCKETS` is deliberately NOT extended
with the historical bucket: that tuple is consumed by the
`create_gcs_buckets` management command, which calls `ensure_bucket()`
on every entry. Adding `cgs_grupo_alvarez` there would put an H28
bucket, with its own lifecycle and its Hierarchical Namespace setting
that cannot be changed after creation, under a command that was never
meant to touch it. The indexed set is therefore declared here.

---

Qué cubos indexa el explorador y cómo se corresponde cada uno con un
modelo de dominio.

`spare_parts.gcs_service.ALL_BUCKETS` NO se amplía a propósito con el
cubo histórico: esa tupla la consume el comando de gestión
`create_gcs_buckets`, que llama a `ensure_bucket()` sobre cada
entrada. Meter ahí `cgs_grupo_alvarez` pondría un cubo de H28, con su
propio ciclo de vida y su ajuste de Namespace Jerárquico que no se
puede cambiar después de crear el cubo, bajo un comando que nunca
estuvo pensado para tocarlo. Por eso el conjunto indexado se declara
aquí.
"""
from spare_parts.gcs_service import (
    DELIVERY_NOTES_BUCKET,
    MACHINE_DOCUMENTS_BUCKET,
    PERSONNEL_DOCUMENTS_BUCKET,
    TASK_PHOTOS_BUCKET,
)

# Cubo sucio de H28: documentación histórica migrada desde
# Microsoft 365, más el prefijo de cuarentena.
HISTORICAL_BUCKET = "cgs_grupo_alvarez"

# Prefijo de cuarentena, en la raíz del cubo histórico como hermano de
# las carpetas migradas (decisión de S036). El prefijo de marcas
# cuelga de él y NO contiene documentos: son los manifiestos de
# existencia local que escribe el agente de Windows, así que ni se
# indexan ni deben generar ninguna llamada a Gemini.
QUARANTINE_PREFIX = "_CUARENTENA/"
MARKS_PREFIX = "_CUARENTENA/_MARCAS/"

INDEXED_BUCKETS = (
    TASK_PHOTOS_BUCKET,
    DELIVERY_NOTES_BUCKET,
    MACHINE_DOCUMENTS_BUCKET,
    PERSONNEL_DOCUMENTS_BUCKET,
    HISTORICAL_BUCKET,
)

# Cubo -> (app_label, model_name, campo que guarda el nombre de blob).
# El cubo histórico no aparece: sus 37.606 objetos no tienen modelo de
# dominio, y precisamente por eso existe el índice.
DOMAIN_MODEL_BY_BUCKET = {
    TASK_PHOTOS_BUCKET: (
        "work_order_processor", "TaskPhoto", "gcs_blob_name",
    ),
    DELIVERY_NOTES_BUCKET: (
        "spare_parts", "DeliveryNote", "gcs_blob_name",
    ),
    MACHINE_DOCUMENTS_BUCKET: (
        "machine_documents", "MachineDocument", "gcs_blob_name",
    ),
    PERSONNEL_DOCUMENTS_BUCKET: (
        "personal_documents", "PersonalDocument", "gcs_blob_name",
    ),
}
