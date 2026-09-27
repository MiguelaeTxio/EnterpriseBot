# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/.github/scripts/gcs_render_pages.py
"""
Read-only helper for file_fetch.yml, mode gcs_image (H30, S119).
---
Script auxiliar de SOLO LECTURA para file_fetch.yml, modo gcs_image
(H30, S119). Origen real: el modelo necesita VER documentos escaneados
(tarjetas ITV cuyo OCR solo devuelve la trama "ESPAÑAESPAÑA...") y el
conector de Drive solo le entrega texto. Este script baja cada
documento por su id de DocumentIndexEntry (la ruta exacta sale de la
BD, nunca se teclea), convierte sus primeras páginas en PNG con
PyMuPDF (render, NO OCR: coste de CPU mínimo) y las deja en un
directorio de SWAP que el workflow recoge y publica como adjuntos de
una release privada, que el modelo sí puede descargar a su entorno y
mirar como imagen.

Nunca escribe en BD ni modifica GCS.

Uso: python3 gcs_render_pages.py <ids separados por coma> <out_dir>
     [max_paginas] [dpi]
"""
import os
import sys
import traceback

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "enterprise_core.settings")
django.setup()

import fitz  # noqa: E402

from document_explorer.models import DocumentIndexEntry  # noqa: E402
from spare_parts.gcs_service import download_bytes  # noqa: E402

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")

ids = [int(value) for value in sys.argv[1].split(",") if value.strip()]
out_dir = sys.argv[2]
max_pages = int(sys.argv[3]) if len(sys.argv) > 3 else 4
dpi = int(sys.argv[4]) if len(sys.argv) > 4 else 110
os.makedirs(out_dir, exist_ok=True)

for number, pk in enumerate(ids, start=1):
    print("[%d/%d] id=%d" % (number, len(ids), pk), flush=True)
    try:
        entry = DocumentIndexEntry.objects.get(pk=pk)
        data = download_bytes(entry.bucket, entry.blob_name)
        name = entry.blob_name.rsplit("/", 1)[-1].lower()
        if name.endswith(IMAGE_EXTENSIONS):
            doc = fitz.open(stream=data, filetype=name.rsplit(".", 1)[-1])
        else:
            doc = fitz.open(stream=data, filetype="pdf")
        with doc:
            # S121: marcador con el total de páginas, para saber si el
            # límite (max_pages) ha dejado páginas sin renderizar. Nunca
            # vacío: la release no admite adjuntos de 0 bytes.
            with open(os.path.join(
                out_dir, "%d_TOTAL_%d.txt" % (pk, doc.page_count),
            ), "w", encoding="utf-8") as marker:
                marker.write("%d\n" % doc.page_count)
            for page_index in range(min(doc.page_count, max_pages)):
                path = os.path.join(
                    out_dir, "%d_p%d.png" % (pk, page_index + 1),
                )
                doc[page_index].get_pixmap(dpi=dpi).save(path)
                print("    %s" % os.path.basename(path), flush=True)
    except Exception:
        with open(os.path.join(out_dir, "%d_ERROR.txt" % pk), "w",
                  encoding="utf-8") as out:
            out.write(traceback.format_exc())
        print("    ERROR (ver %d_ERROR.txt)" % pk, flush=True)
