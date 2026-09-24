# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/split_ficha_itv_combined.py
"""
H30 (S117), punto 4 -- parte físicamente cada combinado FICHA TÉCNICA +
ITV (tarjeta ITV escaneada: anverso con los datos técnicos + hoja
adicional con los sellos de cada inspección / informe de la estación)
en dos documentos: FICHA_TECNICA e ITV.

Decisión de Miguel Ángel (S117): "Dividirlos, es más tedioso, pero, a
la larga, es lo correcto". Regla CONFIRMADA por él ("Confirmo") tras el
análisis real de 60 combinados (analyze_ficha_itv_combined,
EnterpriseBot_018 -- 55 de 60 con la página 1 reconocida como ficha):

1. Página 1 reconocida como ficha técnica -> archivo nuevo FICHA_TECNICA
   con esa única página (sin fecha propia: nunca se inventa la de su
   emisión).
2. Resto de páginas -> archivo nuevo ITV, con las fechas del combinado
   (caducidad/emisión) -- las mismas que ya tenía.
3. El original va a la papelera (trash_dossier_entry) SOLO cuando las
   dos piezas se han subido e indexado bien.
4. Si la página 1 NO se reconoce como ficha (escaneado en otro orden,
   anverso ilegible), NO se parte: lista de revisión manual.
Ambas piezas heredan el is_obsolete del combinado (un combinado ya
obsoleto da dos piezas obsoletas); después pasan por el cálculo normal
de vigencia como cualquier documento. La regla de S50 (si ya existen
ficha técnica e ITV sueltas, el combinado sobra) sigue intacta.

Mismo mecanismo que split_alta_idc_dossier (S66): única operación
física sobre GCS permitida por 4.12 ("contenido que mezcla de verdad
documentos distintos"); nunca toca el blob_name de una fila existente.
Las piezas se suben a la carpeta REAL del blob original (no a su ruta
virtual del explorador) para que refresh_folder las indexe siempre.

DRY-RUN por defecto; --apply escribe. --limit para ir por tandas (mismo
orden que el análisis: la muestra de 60 va primero). Log propio con
heartbeat y ETA (com-standards 0bis/0ter).
"""
import posixpath
import re
import time
from datetime import date, datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db.models import Q

import fitz

from document_explorer.classification_service import trash_dossier_entry
from document_explorer.cloud_vision_service import extract_text
from document_explorer.index_writer import refresh_folder
from document_explorer.management.commands.analyze_ficha_itv_combined import (
    _classify, _single_page,
)
from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog
from document_explorer.naming_service import build_filename_machine
from fleet.models import MachineAsset
from spare_parts.gcs_service import download_bytes, upload_bytes

_DATE_RE = re.compile(r"(\d{1,2})[-.](\d{1,2})[-.](\d{2,4})")


def _pages_range(data, first, last):
    """
    Bytes of a new PDF with pages first..last (0-based, inclusive).
    ---
    Bytes de un PDF nuevo con las páginas first..last (base 0, incl.).
    """
    src = fitz.open(stream=data, filetype="pdf")
    out = fitz.open()
    out.insert_pdf(src, from_page=first, to_page=last)
    result = out.tobytes()
    out.close()
    src.close()
    return result


def _date_from_name(name):
    match = _DATE_RE.search(name)
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


class Command(BaseCommand):
    help = (
        "H30 (S117) -- parte los combinados FICHA TECNICA + ITV en dos "
        "documentos. Dry-run por defecto, --apply para escribir."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=0,
                            help="Solo los N primeros (tandas). 0 = todos.")
        parser.add_argument(
            "--shard", default="1/1",
            help="Reparto en procesos paralelos, numerado desde 1: '2/3' = "
                 "segundo de tres. Por maquina (id de la maquina modulo el "
                 "total), nunca por posicion: dos procesos nunca trabajan "
                 "en la carpeta de la misma maquina a la vez.",
        )
        parser.add_argument("--log-file", required=True)

    def _log(self, message):
        self._log_plain("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message))

    def _log_plain(self, message):
        print(message, flush=True)
        self._log_handle.write(message + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            shard_index, shard_total = (int(part) for part in options["shard"].split("/"))
            if not 1 <= shard_index <= shard_total:
                raise ValueError("--shard fuera de rango: %s" % options["shard"])
            self._run(options["apply"], options["limit"], shard_index, shard_total)
        finally:
            self._log_handle.close()

    def _free_name(self, bucket, folder, code, type_code, doc_date):
        """
        Canonical machine filename not yet used in that folder.
        ---
        Nombre canónico de máquina aún no usado en esa carpeta.
        """
        ordinal = None
        while True:
            name = build_filename_machine(code, type_code, doc_date, ordinal=ordinal)
            if not DocumentIndexEntry.objects.filter(
                bucket=bucket, parent_path=folder, name=name,
            ).exists():
                return name
            ordinal = (ordinal or 1) + 1

    def _run(self, apply_changes, limit, shard_index=1, shard_total=1):
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        ficha_type = DocumentTypeCatalog.objects.get(code="FICHA_TECNICA")
        itv_type = DocumentTypeCatalog.objects.get(code="ITV")
        qs = DocumentIndexEntry.objects.filter(
            Q(name__icontains="FICHA") | Q(name__icontains="TARJETA"),
            entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__code="ITV",
            domain_content_type=machine_ct,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).order_by("parent_path", "name")
        # S117: reparto por máquina en --shard k/n (1-based) -- nunca dos
        # procesos en la carpeta de la misma máquina a la vez.
        entries = [
            e for e in qs
            if (e.domain_object_id % shard_total) == (shard_index - 1)
        ]
        if limit:
            entries = entries[:limit]
        total = len(entries)
        self._log(
            "MODO: %s -- %d combinados FICHA+ITV%s -- proceso %d de %d"
            % ("APLICAR (sube a GCS, indexa, papelera)" if apply_changes
               else "DRY-RUN (no escribe nada)",
               total, " (tanda --limit %d)" % limit if limit else "",
               shard_index, shard_total)
        )

        stats = {"divididos": 0, "revision_manual": 0, "errores": 0}
        manual = []
        start_time = datetime.now()
        last_beat = time.monotonic()

        for index, entry in enumerate(entries, start=1):
            path = "%s/%s" % (entry.parent_path, entry.name)
            try:
                reason = None
                asset = MachineAsset.objects.filter(pk=entry.domain_object_id).first()
                doc_date = entry.expiry_date or entry.issue_date or _date_from_name(entry.name)
                if not entry.name.lower().endswith(".pdf"):
                    reason = "no es PDF (imagen suelta)"
                elif not asset:
                    reason = "sin maquina asignada"
                elif not doc_date:
                    reason = "sin fecha para el nombre canonico"
                if not reason:
                    data = download_bytes(entry.bucket, entry.blob_name)
                    doc = fitz.open(stream=data, filetype="pdf")
                    n_pages = doc.page_count
                    doc.close()
                    if n_pages < 2:
                        reason = "una sola pagina"
                    else:
                        label = _classify(extract_text("p.pdf", _single_page(data, 0)))
                        if label != "F":
                            reason = "pagina 1 no reconocida como ficha (%s)" % label
                if reason:
                    stats["revision_manual"] += 1
                    manual.append("%s -- %s" % (path, reason))
                    self._log("REVISION MANUAL [%s] %s" % (reason, path))
                else:
                    real_folder = posixpath.dirname(entry.blob_name)
                    self._log(
                        "DIVIDIR %s -> p1 FICHA_TECNICA + p2-%d ITV (%s, %s)"
                        % (path, n_pages, asset.code, doc_date.isoformat())
                    )
                    if apply_changes:
                        pieces = (
                            (ficha_type, _pages_range(data, 0, 0), False),
                            (itv_type, _pages_range(data, 1, n_pages - 1), True),
                        )
                        created = []
                        for doc_type, piece_bytes, keep_dates in pieces:
                            name = self._free_name(
                                entry.bucket, real_folder, asset.code, doc_type.code, doc_date,
                            )
                            upload_bytes(entry.bucket, "%s/%s" % (real_folder, name), piece_bytes)
                            refresh_folder(entry.bucket, real_folder)
                            new_entry = DocumentIndexEntry.objects.get(
                                bucket=entry.bucket, parent_path=real_folder, name=name,
                            )
                            new_entry.document_type = doc_type
                            new_entry.domain_content_type = machine_ct
                            new_entry.domain_object_id = asset.pk
                            new_entry.is_obsolete = entry.is_obsolete
                            fields = ["document_type", "domain_content_type",
                                      "domain_object_id", "is_obsolete"]
                            if keep_dates:
                                new_entry.expiry_date = entry.expiry_date
                                new_entry.issue_date = entry.issue_date
                                fields += ["expiry_date", "issue_date"]
                            new_entry.save(update_fields=fields)
                            created.append(name)
                            self._log("    CREADO %s/%s (%s)" % (real_folder, name, doc_type.code))
                        if len(created) == 2 and trash_dossier_entry(entry):
                            self._log("    original a papelera: %s" % entry.name)
                    stats["divididos"] += 1
            except Exception as exc:  # un archivo que falla no para el resto
                stats["errores"] += 1
                self._log("ERROR %s -- %s" % (path, exc))

            if index % 10 == 0 or time.monotonic() - last_beat >= 30 or index == total:
                last_beat = time.monotonic()
                elapsed = (datetime.now() - start_time).total_seconds()
                eta_seg = (elapsed / index) * (total - index)
                hora_fin = (datetime.now() + timedelta(seconds=eta_seg)).strftime("%H:%M:%S")
                self._log("Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s) -- divididos=%d, manual=%d, errores=%d"
                          % (index, total, index * 100 // total if total else 100,
                             int(eta_seg // 60), int(eta_seg % 60), hora_fin,
                             stats["divididos"], stats["revision_manual"], stats["errores"]))

        self._log_plain("=== RESUMEN (%s) ===" % ("APLICADO" if apply_changes else "DRY-RUN, nada escrito"))
        for key, value in stats.items():
            self._log_plain("    %s: %d" % (key, value))
        self._log_plain("--- REVISION MANUAL (no se parten) ---")
        for line in manual:
            self._log_plain("    %s" % line)
