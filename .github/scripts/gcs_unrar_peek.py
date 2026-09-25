# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/.github/scripts/gcs_unrar_peek.py
"""
Read-only helper for file_fetch.yml, one-off use (H30, S119).
---
Script auxiliar de SOLO LECTURA, uso puntual (H30 S119): baja un .rar de
GCS por id de DocumentIndexEntry, lo descomprime en memoria (rarfile,
ya en requirements por extract-msg) y, para cada miembro, si es PDF o
imagen renderiza sus primeras páginas a PNG (PyMuPDF); si es de otro
tipo, deja constancia de su nombre y tamaño. Nunca escribe en BD ni en
GCS.

Uso: python3 gcs_unrar_peek.py <id> <out_dir> [max_paginas] [dpi]
"""
import io
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "enterprise_core.settings")
django.setup()

import fitz  # noqa: E402
import rarfile  # noqa: E402

from document_explorer.models import DocumentIndexEntry  # noqa: E402
from spare_parts.gcs_service import download_bytes  # noqa: E402

pk = int(sys.argv[1])
out_dir = sys.argv[2]
max_pages = int(sys.argv[3]) if len(sys.argv) > 3 else 4
dpi = int(sys.argv[4]) if len(sys.argv) > 4 else 140
os.makedirs(out_dir, exist_ok=True)

entry = DocumentIndexEntry.objects.get(pk=pk)
data = download_bytes(entry.bucket, entry.blob_name)
try:
    with rarfile.RarFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        print("Miembros del .rar id=%d: %s" % (pk, names), flush=True)
        for index, name in enumerate(names, start=1):
            lower = name.lower()
            member = archive.read(name)
            base = "%d_%d_%s" % (pk, index, os.path.basename(name))
            if lower.endswith((".jpg", ".jpeg", ".png")):
                doc = fitz.open(
                    stream=member, filetype=lower.rsplit(".", 1)[-1],
                )
            elif lower.endswith(".pdf"):
                doc = fitz.open(stream=member, filetype="pdf")
            else:
                with open(os.path.join(out_dir, base + "_SIN_RENDER.txt"),
                          "w", encoding="utf-8") as out:
                    out.write("%s -- %d bytes, sin extractor visual\n"
                              % (name, len(member)))
                print("  %s: sin extractor visual" % name, flush=True)
                continue
            with doc:
                for page_index in range(min(doc.page_count, max_pages)):
                    path = os.path.join(
                        out_dir, "%s_p%d.png" % (base, page_index + 1),
                    )
                    doc[page_index].get_pixmap(dpi=dpi).save(path)
                    print("  %s" % os.path.basename(path), flush=True)
except Exception:
    import traceback

    with open(os.path.join(out_dir, "%d_ERROR.txt" % pk), "w",
              encoding="utf-8") as out:
        out.write("RAR bytes: %d\n" % len(data))
        out.write(traceback.format_exc())
    print("ERROR descomprimiendo id=%d (ver %d_ERROR.txt)" % (pk, pk),
          flush=True)
