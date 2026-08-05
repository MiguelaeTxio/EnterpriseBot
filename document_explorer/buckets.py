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

# Carpeta real (no un cajón técnico) en la raíz de "Directorio
# Principal", hermana de DOC. MAQUINAS/DOC. PERSONAL -- decisión 3.14
# del anexo H29, corregida en S041 y construida en S042. Destino de un
# archivo de cuarentena que Gemini no pudo clasificar/reubicar con
# certeza en su ÚNICA pasada (N=1, Miguel Ángel: "con que entre una
# vez y no se pueda clasificar ya es suficiente") -- sale del prefijo
# de cuarentena, así que `consume_quarantine_task` deja de
# reprocesarlo para siempre hasta que un humano lo reencole a mano.
NO_CONFORMES_PREFIX = "NO CONFORMES/"

# Carpeta real de nivel superior, hermana de DOC. MAQUINAS/DOC.
# PERSONAL -- destino fijo para el tipo documental MANUAL_USO
# (catálogo cerrado, sembrado ya en 0004_seed_closed_vocabulary),
# decisión de Miguel Ángel en S042: un manual de uso es genérico al
# modelo, no específico de un activo concreto, así que no tiene
# sentido enrutarlo por máquina como el resto de DOC. MAQUINAS -- va
# directo a su propia carpeta, con el nombre que ya traía y un
# ordinal solo si hay colisión (ver classification_service.
# apply_quarantine_classification, caso especial MANUAL_USO).
MANUAL_USO_FOLDER = "MANUALES DE USO"

INDEXED_BUCKETS = (
    TASK_PHOTOS_BUCKET,
    DELIVERY_NOTES_BUCKET,
    HISTORICAL_BUCKET,
)

# Cubo raíz de la unificación visual (S039, decisión de Miguel Ángel):
# el explorador deja de mostrar pestañas de cubo -- todo se presenta
# como un único árbol que empieza en "Directorio Principal". Ese cubo
# es HISTORICAL_BUCKET; su carpeta raíz real ES la raíz visual, y las
# raíces de los demás cubos indexados se inyectan como si fueran
# subcarpetas suyas (ver `document_explorer.views` -- entradas
# sintéticas). "Nadie tiene por qué saber que son cubos diferentes":
# verbatim de Miguel Ángel.
PRIMARY_BUCKET = HISTORICAL_BUCKET

# Nombres visibles en castellano de las pestañas del explorador
# (decisión de Miguel Ángel, S038, anexo H29 sección 3.12). Los cubos
# de documentación de máquina y de personal se eliminaron de GCS en la
# misma sesión (contenido ya integrado en HISTORICAL_BUCKET desde
# H28) y por eso ya no aparecen ni aquí ni en INDEXED_BUCKETS.
#
# Spanish display names for the explorer tabs (Miguel Ángel's
# decision, S038, H29 annex section 3.12). The machine-documents and
# personnel-documents buckets were deleted from GCS in the same
# session (their content was already folded into HISTORICAL_BUCKET
# via H28) so they no longer appear here or in INDEXED_BUCKETS.
BUCKET_DISPLAY_NAMES = {
    TASK_PHOTOS_BUCKET: "Fotos Partes",
    DELIVERY_NOTES_BUCKET: "Fotos Albaranes",
    HISTORICAL_BUCKET: "Directorio Principal",
}

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
}
