# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/convertir_fotos_carnet_pdf.py
"""
H30 (S68) -- 20 archivos de `DOC. PERSONAL/FOTOS CARNET` son fotos de
carnet reales guardadas como PDF en vez de imagen suelta (confirmado
a mano por Miguel Angel con una captura real: una foto de carnet
numerada dentro de uno de estos PDF). Decision verbatim: "convertimos
los pdf de esa carpeta a jpg y tipamos como imagenes llevado a su
dominio por el nombre".

Por archivo:
1. Descarga el PDF real (`spare_parts.gcs_service.download_bytes`).
2. Extrae la imagen: si el PDF tiene una imagen embebida (foto
   escaneada normal, el caso mas comun), se extrae tal cual --
   maxima calidad, sin perdida de recompresion. Si no hay imagen
   embebida (PDF vectorial o texto), se renderiza la pagina a 300dpi
   como alternativa.
3. Sube el `.jpg` resultante como blob nuevo, mismo nombre base +
   `.jpg`, misma carpeta (`upload_bytes`, content_type image/jpeg).
4. `refresh_document_folder`-equivalente (`index_writer.refresh_folder`)
   para que el nuevo blob entre en `DocumentIndexEntry` sin escribir
   la fila a mano.
5. Tipa el nuevo `DocumentIndexEntry` como `IMAGEN`, domain resuelto
   por coincidencia de identidad completa contra `PersonIdentity`
   (activos e inactivos, coincidencia por subconjunto de tokens, ya
   validada en S68 -- ver `trash_contractual_bajas.py`).
6. Manda el PDF original a papelera (`trash_dossier_entry`) -- queda
   sustituido por el JPG, principio 4.12 respetado (blob_name del PDF
   nunca se toca, solo `deleted_at`).

Excluidos explicitamente de este comando (decision aparte pendiente,
nunca forzados aqui): `FRANCISCO GOMEZ GOMEZ.docx` (no es PDF),
`INDICE.pub` y `LISTADO DE FOTOS.pub` (indices, no fotos).

DRY-RUN POR DEFECTO. Con --apply escribe y sube de verdad.
"""
import io
import re

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.classification_service import trash_dossier_entry
from document_explorer.index_writer import refresh_folder
from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity
from spare_parts.gcs_service import download_bytes, upload_bytes

ROOT = "DOC. PERSONAL/FOTOS CARNET"
EXCLUIDOS = {"FRANCISCO GOMEZ GOMEZ.docx", "INDICE.pub", "LISTADO DE FOTOS.pub"}

_PAREN_RE = re.compile(r"\([^)]*\)")
_RUIDO = {"NUEVO", "FOTO", "FOTOS", "COMPRIMIDO", "RED", "II", "III", "IV"}


def _tokens(texto):
    t = _PAREN_RE.sub(" ", texto)
    t = t.replace(",", " ").replace(".", " ")
    return set(
        w for w in re.split(r"\s+", t.strip().upper())
        if len(w) > 1 and w not in _RUIDO
    )


def _extraer_jpg(data):
    """
    Devuelve bytes JPEG reales a partir de un PDF de una pagina.
    Prioriza la imagen embebida (sin perdida de recompresion); si no
    hay ninguna, renderiza la pagina a 300dpi como alternativa.
    """
    import fitz
    from PIL import Image

    doc = fitz.open(stream=data, filetype="pdf")
    page = doc.load_page(0)
    imagenes = page.get_images(full=True)
    if imagenes:
        xref = imagenes[0][0]
        base = doc.extract_image(xref)
        img = Image.open(io.BytesIO(base["image"]))
        origen = "embebida"
    else:
        pix = page.get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        origen = "render"
    doc.close()

    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue(), origen


class Command(BaseCommand):
    help = (
        "H30 (S68) -- convierte los PDF de FOTOS CARNET a JPG real, "
        "tipa como IMAGEN, resuelve dominio por nombre y manda el PDF "
        "original a papelera. Dry-run por defecto, --apply para "
        "escribir y subir de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe y sube de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        personas = list(
            PersonIdentity.objects.all()
            .values_list("id", "first_surname", "second_surname", "given_name")
        )
        personas_tokens = []
        for pk, fs, ss, gn in personas:
            full = "%s %s %s" % (fs, ss or "", gn)
            personas_tokens.append((pk, full.strip(), _tokens(full)))

        entries = DocumentIndexEntry.objects.filter(
            bucket="cgs_grupo_alvarez", entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            document_type__isnull=True,
            parent_path__startswith=ROOT,
            name__iendswith=".pdf",
        ).exclude(name__in=EXCLUIDOS).only("id", "parent_path", "name", "bucket", "blob_name")

        tipo_imagen = DocumentTypeCatalog.objects.get(code="IMAGEN")
        totales = {"convertidos": 0, "fallos": 0, "dominio_resuelto": 0, "dominio_ambiguo": 0}

        for entry in entries.iterator():
            base_nombre = entry.name.rsplit(".", 1)[0]
            t = _tokens(base_nombre)
            candidatos = [(pk, full) for pk, full, pt in personas_tokens if pt and t.issubset(pt)]
            quien = None
            if len(candidatos) == 1:
                quien = candidatos[0]
                totales["dominio_resuelto"] += 1
            elif len(candidatos) > 1:
                totales["dominio_ambiguo"] += 1
                self.stdout.write(
                    "DOMINIO AMBIGUO (%d candidatos, se deja sin dominio): %s -> %s"
                    % (len(candidatos), entry.name, [c[1] for c in candidatos])
                )

            if not apply_changes:
                self.stdout.write(
                    "CONVERTIRIA: %s / %s -> %s.jpg | dominio: %s"
                    % (entry.parent_path, entry.name, base_nombre,
                       quien[1] if quien else "SIN RESOLVER")
                )
                continue

            try:
                data = download_bytes(entry.bucket, entry.blob_name)
                jpg_bytes, origen = _extraer_jpg(data)
                nuevo_blob_name = entry.blob_name.rsplit(".", 1)[0] + ".jpg"
                upload_bytes(entry.bucket, nuevo_blob_name, jpg_bytes, content_type="image/jpeg")
                refresh_folder(entry.bucket, entry.parent_path)

                nueva_entry = DocumentIndexEntry.objects.filter(
                    bucket=entry.bucket, parent_path=entry.parent_path,
                    name=base_nombre + ".jpg",
                ).first()
                if nueva_entry is None:
                    totales["fallos"] += 1
                    self.stdout.write("FALLO: no se encontro la fila nueva tras refrescar -- %s" % entry.name)
                    continue

                nueva_entry.document_type = tipo_imagen
                if quien:
                    nueva_entry.domain_object_id = quien[0]
                    nueva_entry.domain_content_type = ContentType.objects.get_for_model(PersonIdentity)
                nueva_entry.save(update_fields=["document_type", "domain_object_id", "domain_content_type"])

                trash_dossier_entry(entry)
                totales["convertidos"] += 1
                self.stdout.write(
                    "CONVERTIDO (%s): %s -> %s.jpg | dominio: %s"
                    % (origen, entry.name, base_nombre, quien[1] if quien else "SIN RESOLVER")
                )
            except Exception as exc:
                totales["fallos"] += 1
                self.stdout.write("FALLO: %s -- %s: %s" % (entry.name, type(exc).__name__, exc))

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in totales.items():
            self.stdout.write("    %s: %d" % (key, value))
