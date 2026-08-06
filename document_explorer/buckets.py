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
from django.db.models import Q

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


def quarantine_scope_q(field="parent_path"):
    """
    Q filter matching a file's `field` (default `parent_path`) against
    quarantine -- BOTH nested (`"_CUARENTENA/DOC. MAQUINAS/..."`, the
    normal case, mirrors an original local folder) AND flat at the
    bare quarantine root (`"_CUARENTENA"`, no trailing segment at
    all).

    Real incident, S042: `parent_path__startswith=QUARANTINE_PREFIX`
    ("_CUARENTENA/", WITH the trailing slash) is a substring check --
    a `parent_path` of exactly `"_CUARENTENA"` (11 chars) can never
    start with a 12-char string that has one more character than it
    does. `RequeueNoConformesView` (and any manual move to the bare
    root) sets `parent_path` to precisely that value --
    `move_service.move_entry()` always `.strip("/")`s its destination,
    so there is no way to land a file's `parent_path` at
    `"_CUARENTENA/"` with the trailing slash still on it; the root
    itself is unavoidably the slash-less form. 133 files Miguel Ángel
    requeued from NO CONFORMES landed there, invisible to `EN COLA`
    and to `consume_quarantine_task`'s own query alike, silently
    stuck forever -- confirmed with real data (`EN COLA: 0` while the
    folder itself showed 196 files) before writing this fix, not
    guessed.

    Every place that needs "is this file in quarantine" must build
    its filter through this helper from now on, never repeat the raw
    `__startswith` -- `tasks.py`, `views.py`
    (`QuarantineStatusView`) and the `repair_reverted_quarantine_
    relocations` management command all had the exact same
    incomplete check independently; fixing one and not the others
    would just move the same incident somewhere else.

    ---

    Filtro Q que compara el `field` de un archivo (por defecto
    `parent_path`) contra cuarentena -- TANTO anidado
    (`"_CUARENTENA/DOC. MAQUINAS/..."`, el caso normal, refleja una
    carpeta local original) COMO suelto en la raíz pelada de
    cuarentena (`"_CUARENTENA"`, sin ningún segmento después).

    Incidente real, S042: `parent_path__startswith=QUARANTINE_PREFIX`
    ("_CUARENTENA/", CON la barra final) es una comprobación de
    subcadena -- un `parent_path` de exactamente `"_CUARENTENA"` (11
    caracteres) nunca puede empezar por una cadena de 12 caracteres
    que tiene uno más que él. `RequeueNoConformesView` (y cualquier
    movimiento manual a la raíz pelada) deja `parent_path` en
    precisamente ese valor -- `move_service.move_entry()` siempre le
    hace `.strip("/")` a su destino, así que no hay forma de que el
    `parent_path` de un archivo termine siendo `"_CUARENTENA/"` con la
    barra todavía puesta; la propia raíz es inevitablemente la forma
    sin barra. 133 archivos que Miguel Ángel reencoló desde NO
    CONFORMES aterrizaron ahí, invisibles tanto para `EN COLA` como
    para la propia consulta de `consume_quarantine_task`, atascados en
    silencio para siempre -- confirmado con datos reales (`EN COLA: 0`
    mientras la propia carpeta mostraba 196 archivos) antes de escribir
    este arreglo, nunca supuesto.

    Cualquier sitio que necesite "¿está este archivo en cuarentena?"
    debe construir su filtro a partir de este helper desde ahora,
    nunca repetir el `__startswith` en crudo -- `tasks.py`, `views.py`
    (`QuarantineStatusView`) y el comando de gestión `repair_reverted_
    quarantine_relocations` tenían todos, cada uno por su cuenta,
    exactamente la misma comprobación incompleta; arreglar uno y no
    los demás solo movería el mismo incidente a otro sitio.
    """
    root = QUARANTINE_PREFIX.rstrip("/")
    return (
        Q(**{field: root})
        | Q(**{"%s__startswith" % field: QUARANTINE_PREFIX})
    )

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
