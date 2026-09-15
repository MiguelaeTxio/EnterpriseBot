# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/templatetags/document_explorer_extras.py
"""
Custom template filters for the document explorer (H31, S98).

`basename` backs the "show original filename" toggle requested by
Miguel Angel right after the H31 canonical bulk rename of PERSONAL:
the rename is virtual-only (S040, `classification_service.
apply_personal_canonical_rename`) -- it only ever rewrites
`DocumentIndexEntry.name`, never `blob_name` (the real object path in
GCS) -- so the original filename a person actually typed is never
lost, it just moved from `.name` into the last path segment of
`.blob_name`. This filter is the one place that extracts it back out
for display.

---

Filtros de template personalizados para el explorador de documentos
(H31, S98).

`basename` sostiene el toggle "mostrar nombre de archivo original"
que pidió Miguel Ángel justo después del renombrado canónico masivo
de PERSONAL de H31: el renombrado es solo virtual (S040,
`classification_service.apply_personal_canonical_rename`) -- solo
reescribe `DocumentIndexEntry.name`, nunca `blob_name` (la ruta real
del objeto en GCS) -- así que el nombre de archivo original que
tecleó una persona nunca se pierde, simplemente pasó de `.name` al
último segmento de `.blob_name`. Este filtro es el único sitio que lo
vuelve a extraer para mostrarlo.
"""
from django import template

register = template.Library()


@register.filter
def basename(blob_name):
    """
    Last path segment of a GCS object path, or "" for a blank/empty
    input -- callers chain `|default:entry.name` to fall back to the
    canonical name when there is nothing real to extract (folders,
    or any legacy row with `blob_name` blank).

    ---

    Último segmento de una ruta de objeto de GCS, o "" si la entrada
    está vacía -- quien llama encadena `|default:entry.name` para
    caer en el nombre canónico cuando no hay nada real que extraer
    (carpetas, o alguna fila legacy con `blob_name` en blanco).
    """
    if not blob_name:
        return ""
    return blob_name.rstrip("/").rsplit("/", 1)[-1]


_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")


@register.filter
def is_image_document(name):
    """
    H35 (S105). True si `name` (DocumentIndexEntry.name) termina en
    una extensión de imagen real -- respalda el botón "Usar como foto
    de perfil" de la ficha de personal (PersonalSetAvatarView), que
    solo debe aparecer junto a documentos que de verdad son una
    imagen, nunca un PDF aunque su contenido sea una foto escaneada.
    Mismo criterio de "es imagen" (extensión, nunca inferencia de
    contenido) que ya usa el resto del proyecto.

    ---

    H35 (S105). True si `name` (DocumentIndexEntry.name) termina en
    una extensión de imagen real -- respalda el botón "Usar como foto
    de perfil" de la ficha de personal (PersonalSetAvatarView).
    """
    return bool(name) and name.lower().endswith(_IMAGE_EXTENSIONS)
