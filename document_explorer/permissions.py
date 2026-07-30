# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/permissions.py
"""
Folder-level permission resolution for the explorer (H29).

The design decision that matters here is what this module REFUSES to
do: it never filters the index row by row.

Filtering rows by a permitted prefix would mean `LIKE 'prefix%'` over
`blob_name`, an unindexed TextField -- precisely the query shape
DocumentIndexEntry was built to avoid. Instead the check happens once,
against the folder being opened, and its children inherit the answer.
Grants are a handful of short strings per user, so the whole decision
is made in Python before a single row is read.

Three possible answers when opening a folder:

- ALL: a grant covers this folder, so every child is visible.
- PARTIAL: no grant covers it, but some grant lives further down. The
  user may only see the children that lead to their own grants -- just
  enough to navigate towards what they are entitled to.
- NONE: nothing here concerns this user.

ADMIN is exempt by code and needs no grant rows, per the decision of
S037: "yo podré borrar y añadir donde quiera, pero, por ejemplo,
supervisor de documentación única y exclusivamente podrá gestionar el
cubo de documentación".

---

Resolución de permisos por carpeta para el explorador (H29).

La decisión de diseño que importa aquí es lo que este módulo se NIEGA
a hacer: no filtra el índice fila a fila.

Filtrar filas por prefijo permitido significaría un `LIKE 'prefijo%'`
sobre `blob_name`, un TextField sin indexar -- justo la forma de
consulta que DocumentIndexEntry existe para evitar. En su lugar la
comprobación se hace una sola vez, contra la carpeta que se abre, y sus
hijos heredan la respuesta. Las concesiones son un puñado de cadenas
cortas por usuario, así que toda la decisión se toma en Python antes de
leer una sola fila.

Tres respuestas posibles al abrir una carpeta:

- ALL: una concesión cubre esta carpeta, así que se ven todos los
  hijos.
- PARTIAL: ninguna concesión la cubre, pero alguna vive más abajo. El
  usuario solo ve los hijos que llevan hacia sus propias concesiones
  -- lo justo para poder navegar hasta lo que le corresponde.
- NONE: aquí no hay nada que le incumba.

El ADMIN queda exento por código y no necesita filas de concesión,
según la decisión de S037: "yo podré borrar y añadir donde quiera,
pero, por ejemplo, supervisor de documentación única y exclusivamente
podrá gestionar el cubo de documentación".
"""
from ivr_config.models import CompanyUser

from document_explorer.buckets import INDEXED_BUCKETS
from document_explorer.models import DocumentFolderGrant

ALL = "ALL"
PARTIAL = "PARTIAL"
NONE = "NONE"


def is_unrestricted(company_user) -> bool:
    """
    Whether this user bypasses grants entirely.

    ---

    Si este usuario se salta las concesiones por completo.
    """
    return company_user.role == CompanyUser.ROLE_ADMIN


def grants_for(company_user, bucket=None):
    """
    Load the user's grants, optionally for a single bucket.

    Returns a list of (path_prefix, can_read, can_delete). Read once
    per request and reused: the caller must not re-query per folder.

    ---

    Carga las concesiones del usuario, opcionalmente de un solo cubo.

    Devuelve una lista de (path_prefix, can_read, can_delete). Se lee
    una vez por petición y se reutiliza: quien llame no debe volver a
    consultar por cada carpeta.
    """
    query = DocumentFolderGrant.objects.filter(
        user=company_user, can_read=True,
    )
    if bucket is not None:
        query = query.filter(bucket=bucket)
    return list(
        query.values_list("path_prefix", "can_read", "can_delete")
    )


def covers(prefix, folder_path) -> bool:
    """
    Whether a grant prefix covers a folder (itself or an ancestor).

    An empty prefix covers the whole bucket.

    ---

    Si un prefijo de concesión cubre una carpeta (ella misma o una
    antecesora).

    Un prefijo vacío cubre el cubo entero.
    """
    if prefix == "":
        return True
    return folder_path == prefix or folder_path.startswith(
        prefix + "/"
    )


def _next_segment(prefix, folder_path):
    """
    The child of `folder_path` that leads towards `prefix`.

    ---

    El hijo de `folder_path` que lleva hacia `prefix`.
    """
    if folder_path == "":
        remainder = prefix
    elif prefix.startswith(folder_path + "/"):
        remainder = prefix[len(folder_path) + 1:]
    else:
        return None
    return remainder.split("/")[0] if remainder else None


def visibility(company_user, bucket, folder_path, grants=None):
    """
    Resolve what this user may see inside a folder.

    Returns (mode, allowed_child_names). `allowed_child_names` is only
    meaningful when mode is PARTIAL.

    ---

    Resuelve qué puede ver este usuario dentro de una carpeta.

    Devuelve (modo, nombres_de_hijo_permitidos). El segundo valor solo
    tiene sentido cuando el modo es PARTIAL.
    """
    if is_unrestricted(company_user):
        return ALL, None

    if grants is None:
        grants = grants_for(company_user, bucket)

    if any(covers(prefix, folder_path) for prefix, _r, _d in grants):
        return ALL, None

    children = set()
    for prefix, _read, _delete in grants:
        segment = _next_segment(prefix, folder_path)
        if segment:
            children.add(segment)

    if children:
        return PARTIAL, children
    return NONE, None


def can_delete_in(company_user, bucket, folder_path, grants=None):
    """
    Whether the user may send items of this folder to their trash.

    ---

    Si el usuario puede mandar elementos de esta carpeta a su papelera.
    """
    if is_unrestricted(company_user):
        return True
    if grants is None:
        grants = grants_for(company_user, bucket)
    return any(
        delete_flag and covers(prefix, folder_path)
        for prefix, _read, delete_flag in grants
    )


def readable_buckets(company_user):
    """
    Buckets in which the user has at least one grant.

    ---

    Cubos en los que el usuario tiene al menos una concesión.
    """
    if is_unrestricted(company_user):
        return list(INDEXED_BUCKETS)

    granted = set(
        DocumentFolderGrant.objects
        .filter(user=company_user, can_read=True)
        .values_list("bucket", flat=True)
    )
    return [b for b in INDEXED_BUCKETS if b in granted]


def readable_prefixes(company_user, bucket):
    """
    Grant prefixes to use as an OR filter in a recursive search
    (S039), never as a per-row check.

    Returns `None` when the user may read the whole bucket without
    restriction (ADMIN, or an explicit empty-prefix grant) -- the
    caller then applies no extra filter at all. Otherwise returns the
    list of prefixes the user may read, which may be empty (no access
    to this bucket whatsoever).

    This is deliberately a different trade-off than `visibility()`:
    that function resolves a single folder and lets the caller avoid
    ever touching `blob_name`. A recursive search has no single folder
    to resolve against -- it inherently scans a subtree -- so the
    permission check here is the same handful of grant strings applied
    as `blob_name__startswith` conditions, still O(number of grants),
    never O(number of rows).

    ---

    Prefijos de concesión para usar como filtro OR en una búsqueda
    recursiva (S039), nunca como comprobación fila a fila.

    Devuelve `None` cuando el usuario puede leer el cubo entero sin
    restricción (ADMIN, o una concesión explícita de prefijo vacío) --
    quien llame no aplica entonces ningún filtro adicional. Si no,
    devuelve la lista de prefijos que el usuario puede leer, que puede
    estar vacía (sin ningún acceso a este cubo).

    Es deliberadamente un compromiso distinto al de `visibility()`:
    esa función resuelve una única carpeta y evita que quien llama
    toque nunca `blob_name`. Una búsqueda recursiva no tiene una única
    carpeta que resolver -- por su propia naturaleza recorre un
    subárbol -- así que la comprobación de permiso aquí es el mismo
    puñado de cadenas de concesión aplicadas como condiciones
    `blob_name__startswith`, sigue siendo O(número de concesiones),
    nunca O(número de filas).
    """
    if is_unrestricted(company_user):
        return None
    grants = grants_for(company_user, bucket)
    prefixes = [prefix for prefix, can_read, _delete in grants if can_read]
    if "" in prefixes:
        return None
    return prefixes
