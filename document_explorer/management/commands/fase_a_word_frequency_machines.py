# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/fase_a_word_frequency_machines.py
"""
H30 (S117) -- SOLO LECTURA. Cierre de la Fase 1 (tipado por nombre) de
MÁQUINAS: frecuencia EXHAUSTIVA de palabras de los nombres de archivo
que la heurística actual deja sin tipo.

Origen real: el dry-run de run_fase_a_sweep_scoped (EnterpriseBot_001,
S117) tipaba solo 98 de 2.100 archivos dentro de alcance, y una
muestra de nombres reales sin tipo mostró variantes que el diccionario
no conoce (FRA.COMPRA, MANUAL OPERADOR, REV. ANUAL, PERMISO CIRC, AUT
PROV CIRC, IMPUESTO SOBRE VEHICULOS, TACOGRAFOR...). Miguel Ángel (S50)
exige repasar TODAS las palabras, no solo las más frecuentes: "no nos
podemos dejar documentos por el camino".

Recorre EXACTAMENTE el mismo alcance (SCOPE de run_fase_a_sweep_scoped,
confirmado carpeta a carpeta en S50) y aplica la MISMA heurística
(folder_based_type + resolve_document_type_heuristic). Para cada
archivo que sigue sin tipo, parte el nombre en palabras descartando lo
que nunca indica tipo documental: códigos de flota (A-29, Z131...),
matrículas (1234-ABC), fechas, números sueltos, extensiones y
palabras de menos de 3 letras. Cuenta palabras sueltas y parejas de
palabras consecutivas (en cuántos archivos aparecen, no repeticiones
dentro del mismo nombre), con hasta 3 nombres reales de ejemplo, y
cuenta aparte los nombres "ciegos" (sin ninguna palabra útil: Scan0754,
doc0700912..., A57.pdf) -- esos solo se resolverán con OCR (Fase 3).

Nunca escribe en BD, nunca toca GCS. Log propio con heartbeat y ETA
(com-standards 0bis/0ter).
"""
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand

from document_explorer.heuristic_type_service import (
    folder_based_type, resolve_document_type_heuristic,
)
from document_explorer.management.commands.calibrate_fase_a_keywords import (
    _strip_accents,
)
from document_explorer.management.commands.run_fase_a_sweep_scoped import (
    _scoped_files,
)

EXTENSIONS = {
    "PDF", "JPG", "JPEG", "PNG", "GIF", "TIF", "TIFF", "BMP", "HEIC", "DOC",
    "DOCX", "XLS", "XLSX", "ZIP", "RAR", "MSG", "PPT", "PPTX", "XPS",
}
FLEET_CODE_RE = re.compile(r"^[A-Z]{1,3}\d{1,4}$")
PLATE_RE = re.compile(r"^(\d{4}[A-Z]{3}|[A-Z]{1,2}\d{4}[A-Z]{1,3}|E\d{4}[A-Z]{3})$")
MIN_WORD_LEN = 3
EXAMPLES_PER_WORD = 3


def _tokens(name):
    """
    Meaningful words of a file name, in order (for bigrams).
    ---
    Palabras con significado de un nombre de archivo, en orden (para
    las parejas).
    """
    upper = _strip_accents(name).upper()
    # Une código de flota y matrícula partidos por guion ("A-29",
    # "1234-ABC") antes de trocear, para poder descartarlos enteros.
    # La matrícula de tres partes ("E-1462-BHF") ANTES que el código de
    # flota, o "E-1462" se uniría primero y dejaría "BHF" suelto.
    # Límites "no letra ni dígito" en vez de \b: el "_" cuenta como
    # carácter de palabra ("E-1462-BHF_compressed").
    upper = re.sub(
        r"(?<![A-Z0-9])([A-Z]{1,2})-(\d{4})-([A-Z]{1,3})(?![A-Z0-9])",
        r"\1\2\3", upper,
    )
    upper = re.sub(
        r"(?<![A-Z0-9])([A-Z]{1,3})-(\d{1,4})(?![A-Z0-9])", r"\1\2", upper,
    )
    upper = re.sub(
        r"(?<![A-Z0-9])(\d{4})[\s-]([A-Z]{3})(?![A-Z0-9])", r"\1\2", upper,
    )
    words = []
    for raw in re.split(r"[^A-Z0-9]+", upper):
        if len(raw) < MIN_WORD_LEN or raw in EXTENSIONS:
            continue
        if raw.isdigit() or FLEET_CODE_RE.match(raw) or PLATE_RE.match(raw):
            continue
        if not re.search(r"[A-Z]{3}", raw) or re.search(r"\d{3,}", raw):
            continue  # restos alfanuméricos (SCAN0754, DOC0700912...)
        words.append(raw)
    return words


class Command(BaseCommand):
    help = (
        "H30 (S117) -- SOLO LECTURA: frecuencia exhaustiva de palabras de "
        "los nombres de MAQUINAS que la heuristica deja sin tipo."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--log-file", required=True,
            help="Log propio (pantalla y archivo a la vez, com-standards 0bis).",
        )

    def _log(self, message):
        self._log_plain("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message))

    def _log_plain(self, message):
        print(message, flush=True)
        self._log_handle.write(message + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run()
        finally:
            self._log_handle.close()

    def _run(self):
        entries = list(_scoped_files().only("id", "name", "parent_path"))
        total = len(entries)
        self._log(
            "SOLO LECTURA -- MACHINE (alcance S50): %d archivos sin tipo "
            "en alcance" % total
        )

        word_files = Counter()
        pair_files = Counter()
        word_examples = defaultdict(list)
        pair_examples = defaultdict(list)
        resolved = 0
        blind = []
        start_time = datetime.now()
        last_beat = time.monotonic()

        for index, entry in enumerate(entries, start=1):
            name_upper = _strip_accents(entry.name).upper()
            code = folder_based_type(entry, "MACHINE")
            dossier_pair = None
            if not code:
                code, dossier_pair = resolve_document_type_heuristic(
                    entry, "MACHINE", name_upper,
                )
            if code or dossier_pair:
                resolved += 1
            else:
                words = _tokens(entry.name)
                if not words:
                    blind.append(entry.name)
                for word in set(words):
                    word_files[word] += 1
                    if len(word_examples[word]) < EXAMPLES_PER_WORD:
                        word_examples[word].append(entry.name)
                for pair in set(zip(words, words[1:])):
                    joined = "%s %s" % pair
                    pair_files[joined] += 1
                    if len(pair_examples[joined]) < EXAMPLES_PER_WORD:
                        pair_examples[joined].append(entry.name)

            if index % 100 == 0 or time.monotonic() - last_beat >= 30 or index == total:
                last_beat = time.monotonic()
                elapsed = (datetime.now() - start_time).total_seconds()
                eta_seg = (elapsed / index) * (total - index)
                hora_fin = (
                    datetime.now() + timedelta(seconds=eta_seg)
                ).strftime("%H:%M:%S")
                self._log(
                    "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s)"
                    % (
                        index, total, index * 100 // total if total else 100,
                        int(eta_seg // 60), int(eta_seg % 60), hora_fin,
                    )
                )

        unresolved = total - resolved
        self._log_plain("=== RESUMEN (SOLO LECTURA, nada escrito) ===")
        self._log_plain("    archivos en alcance sin tipo: %d" % total)
        self._log_plain("    los tipa ya la heuristica actual: %d" % resolved)
        self._log_plain("    siguen sin tipo: %d" % unresolved)
        self._log_plain("    nombres ciegos (sin ninguna palabra util): %d" % len(blind))
        self._log_plain("    palabras distintas: %d" % len(word_files))
        self._log_plain(
            "--- PALABRAS (archivos en que aparece | palabra | ejemplos), TODAS ---"
        )
        for word, count in sorted(word_files.items(), key=lambda kv: (-kv[1], kv[0])):
            self._log_plain(
                "    %4d | %s | %s" % (count, word, " || ".join(word_examples[word]))
            )
        self._log_plain(
            "--- PAREJAS DE PALABRAS en 2 o mas archivos ---"
        )
        for pair, count in sorted(pair_files.items(), key=lambda kv: (-kv[1], kv[0])):
            if count < 2:
                continue
            self._log_plain(
                "    %4d | %s | %s" % (count, pair, " || ".join(pair_examples[pair]))
            )
        self._log_plain("--- NOMBRES CIEGOS (solo OCR, Fase 3) ---")
        for name in sorted(blind):
            self._log_plain("    %s" % name)
