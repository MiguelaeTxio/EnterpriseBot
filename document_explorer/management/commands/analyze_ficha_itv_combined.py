# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/analyze_ficha_itv_combined.py
"""
H30 (S117), punto 4 -- SOLO LECTURA. Estructura real de páginas de los
documentos COMBINADOS ficha técnica + ITV (tipados como ITV, con
"FICHA" o "TARJETA" en el nombre -- 557 medidos con datos reales en
S117, p. ej. "0069-GXX FICHA TECNICA+ITV 19-1-2023.pdf").

Decisión de Miguel Ángel (S117): "Dividirlos, es más tedioso, pero, a
la larga, es lo correcto" -- cada combinado pasará a ser dos documentos
(FICHA_TECNICA e ITV). Mismo criterio que split_alta_idc_dossier (S66):
nunca se parte nada sin confirmar ANTES, con datos reales, cómo está
hecho el documento (qué página es qué). Este comando solo mide:

- número de páginas de cada combinado (o si es una imagen suelta, que
  no se puede partir por páginas);
- texto de CADA página (document_explorer.cloud_vision_service.
  extract_text() sobre un PDF de una sola página: texto incrustado
  primero, Cloud Vision después, nunca Tesseract local);
- clasificación de cada página por sus encabezados reales:
  F = ficha técnica / tarjeta ITV, I = informe de inspección ITV,
  ? = no reconocida;
- tabla de estructuras ("F+I", "I+F", "F", ...) con ejemplos y el
  arranque del texto de cada página, para decidir la regla de división.

Nunca escribe en BD, nunca modifica GCS. --limit para una muestra antes
de pasar por el OCR los 557. Log propio con heartbeat y ETA
(com-standards 0bis/0ter).
"""
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db.models import Q

import fitz

from document_explorer.cloud_vision_service import extract_text
from document_explorer.models import DocumentIndexEntry
from fleet.models import MachineAsset
from spare_parts.gcs_service import download_bytes

MAX_PAGES = 6
EXAMPLES_PER_STRUCTURE = 4
SNIPPET = 140

# Encabezados reales de cada documento oficial (sin acentos, mayúsculas).
FICHA_MARKERS = (
    "TARJETA DE INSPECCION TECNICA", "FICHA TECNICA", "TARJETA ITV",
    "CARACTERISTICAS TECNICAS", "HOMOLOGACION", "NUMERO DE BASTIDOR",
    "MASA MAXIMA", "TARA",
)
ITV_MARKERS = (
    "INFORME DE INSPECCION", "INFORME INSPECCION", "RESULTADO DE LA INSPECCION",
    "RESULTADO INSPECCION", "FAVORABLE", "DESFAVORABLE", "DEFECTOS",
    "PROXIMA INSPECCION", "FECHA LIMITE", "ESTACION ITV", "ESTACION DE ITV",
)


def _plain(text):
    return "".join(
        c for c in unicodedata.normalize("NFD", text or "")
        if unicodedata.category(c) != "Mn"
    ).upper()


def _classify(text):
    """
    F / I / ? for one page, by counting real headers of each document.
    ---
    F / I / ? para una página, contando encabezados reales de cada uno.
    """
    plain = _plain(text)
    ficha = sum(1 for marker in FICHA_MARKERS if marker in plain)
    itv = sum(1 for marker in ITV_MARKERS if marker in plain)
    if ficha > itv:
        return "F"
    if itv > ficha:
        return "I"
    return "?"


def _single_page(data, index):
    src = fitz.open(stream=data, filetype="pdf")
    out = fitz.open()
    out.insert_pdf(src, from_page=index, to_page=index)
    return out.tobytes()


class Command(BaseCommand):
    help = (
        "H30 (S117) -- SOLO LECTURA: estructura real de paginas de los "
        "combinados FICHA TECNICA + ITV, para decidir como dividirlos."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0,
                            help="Solo los N primeros (muestra). 0 = todos.")
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
            self._run(options["limit"])
        finally:
            self._log_handle.close()

    def _run(self, limit):
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        qs = DocumentIndexEntry.objects.filter(
            Q(name__icontains="FICHA") | Q(name__icontains="TARJETA"),
            entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__code="ITV",
            domain_content_type=machine_ct,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).order_by("parent_path", "name")
        entries = list(qs[:limit] if limit else qs)
        total = len(entries)
        self._log("SOLO LECTURA -- %d combinados FICHA+ITV a analizar%s"
                  % (total, " (muestra --limit %d)" % limit if limit else ""))

        structures = Counter()
        page_counts = Counter()
        examples = defaultdict(list)
        start_time = datetime.now()
        last_beat = time.monotonic()

        for index, entry in enumerate(entries, start=1):
            try:
                data = download_bytes(entry.bucket, entry.blob_name)
                if not entry.name.lower().endswith(".pdf"):
                    structure = "IMAGEN (%s)" % _classify(extract_text(entry.name, data))
                    pages_detail = []
                    page_counts["imagen"] += 1
                else:
                    doc = fitz.open(stream=data, filetype="pdf")
                    n_pages = doc.page_count
                    page_counts[str(n_pages) if n_pages <= MAX_PAGES else ">%d" % MAX_PAGES] += 1
                    labels, pages_detail = [], []
                    for page_index in range(min(n_pages, MAX_PAGES)):
                        text = extract_text("p.pdf", _single_page(data, page_index))
                        label = _classify(text)
                        labels.append(label)
                        pages_detail.append("p%d=%s: %s" % (
                            page_index + 1, label, " ".join(text.split())[:SNIPPET],
                        ))
                    structure = "+".join(labels) + ("+..." if n_pages > MAX_PAGES else "")
            except Exception as exc:  # un archivo que falla no para el resto
                structure = "ERROR"
                pages_detail = [str(exc)[:200]]
            structures[structure] += 1
            if len(examples[structure]) < EXAMPLES_PER_STRUCTURE:
                examples[structure].append(
                    ("%s/%s" % (entry.parent_path, entry.name), pages_detail)
                )

            if index % 10 == 0 or time.monotonic() - last_beat >= 30 or index == total:
                last_beat = time.monotonic()
                elapsed = (datetime.now() - start_time).total_seconds()
                eta_seg = (elapsed / index) * (total - index)
                hora_fin = (datetime.now() + timedelta(seconds=eta_seg)).strftime("%H:%M:%S")
                self._log("Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s)"
                          % (index, total, index * 100 // total if total else 100,
                             int(eta_seg // 60), int(eta_seg % 60), hora_fin))

        self._log_plain("=== RESUMEN (SOLO LECTURA, nada escrito) ===")
        self._log_plain("    combinados analizados: %d" % total)
        self._log_plain("--- Numero de paginas ---")
        for key, count in page_counts.most_common():
            self._log_plain("    %s: %d" % (key, count))
        self._log_plain("--- Estructuras (F=ficha tecnica, I=informe ITV, ?=no reconocida) ---")
        for key, count in structures.most_common():
            self._log_plain("    %s: %d" % (key, count))
        self._log_plain("--- Ejemplos por estructura ---")
        for key, _count in structures.most_common():
            self._log_plain("  [%s]" % key)
            for path, detail in examples[key]:
                self._log_plain("    %s" % path)
                for line in detail:
                    self._log_plain("        %s" % line)
