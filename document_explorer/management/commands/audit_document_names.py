# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/audit_document_names.py
"""
Django management command: audit_document_names.

First concrete step of H28 Fase 2 / H29 (decided S039): closing the
document-type vocabulary and the name normaliser needs the FULL
corpus, not the two-folder sample S035 worked from (48 + 85 files).
Before H29's index existed, that meant re-scanning GCS; now it is a
plain query over DocumentIndexEntry.

This command does NOT try to be the classifier. It is a discovery aid:
for every root folder under a bucket (generic -- Miguel Angel has said
more folders besides "DOC. MAQUINAS"/"DOC. PERSONAL" are coming, so
nothing here is hardcoded to those two names), it splits each file
name at the point where a date-like token first appears, using the
exact catalogue of formats S035 found by hand (Hallazgo 3 of the H28
annex), and reports the frequency of what comes before that point --
the candidate "tipo de documento" phrases a human curates into the
closed vocabulary. Names with no recognisable date are reported apart,
same as S035's own findings anticipated (Hallazgo 5: `+`-joined types,
scanner-opaque names, etc.).

Read-only. Writes nothing to the database or to GCS.

Uso:
    python -m dotenv run python manage.py audit_document_names --bucket cgs_grupo_alvarez
    python -m dotenv run python manage.py audit_document_names --bucket cgs_grupo_alvarez --root "DOC. PERSONAL"
    python -m dotenv run python manage.py audit_document_names --bucket cgs_grupo_alvarez --top 60

---

Comando de gestión Django: audit_document_names.

Primer paso concreto de la Fase 2 de H28 / H29 (decidido en S039):
cerrar el vocabulario de tipos documentales y el normalizador de
nombres necesita el corpus COMPLETO, no la muestra de dos carpetas con
la que trabajó S035 (48 + 85 archivos). Antes de que existiera el
índice de H29 eso obligaba a rebarrer GCS; ahora es una simple
consulta sobre DocumentIndexEntry.

Este comando NO pretende ser el clasificador. Es una ayuda de
descubrimiento: para cada carpeta raíz de un cubo (genérico -- Miguel
Ángel ya ha dicho que vendrán más carpetas además de "DOC. MAQUINAS"/
"DOC. PERSONAL", así que aquí no hay nada fijado a esos dos nombres),
parte cada nombre de archivo en el punto donde aparece por primera vez
un token con forma de fecha, usando el catálogo exacto de formatos que
S035 encontró a mano (Hallazgo 3 del anexo H28), e informa de la
frecuencia de lo que queda antes de ese punto -- las frases candidatas
a "tipo de documento" que una persona cura hacia el vocabulario
cerrado. Los nombres sin fecha reconocible se listan aparte, tal como
ya anticipaban los propios hallazgos de S035 (Hallazgo 5: tipos unidos
con `+`, nombres opacos de escáner, etc.).

Solo lectura. No escribe nada en la base de datos ni en GCS.
"""
import re

from django.core.management.base import BaseCommand, CommandError

from document_explorer.buckets import INDEXED_BUCKETS, QUARANTINE_PREFIX
from document_explorer.models import DocumentIndexEntry

# Catálogo de formatos de fecha. Arranca del catálogo que S035 cerró a
# mano (Hallazgo 3 del anexo H28), ampliado tras el primer barrido real
# sobre el corpus completo (S039, 2026-07-30): esa muestra de dos
# carpetas no incluía ningún caso de fecha de 8 dígitos pegados sin
# separador (DDMMAAAA/AAAAMMDD, p.ej. `04022026_BHiRB.pdf`,
# `13042026_CONTRATO...`), que en el corpus completo resulta muy
# frecuente, sobre todo en DOC. PERSONAL. De más específico a menos
# para que el primero que case gane.
_DATE_PATTERNS = [
    # Dos AAMMDD pegadas: 151210150311
    r"\d{12}",
    # DDMMAAAA / AAAAMMDD pegados sin separador: 04022026
    r"\d{8}",
    # AAMMDD: 150611
    r"\d{6}",
    # DD-MM-AAAA / DD.MM.AAAA / DD_MM_AAAA
    r"\d{1,2}[-._]\d{1,2}[-._]\d{4}",
    # DD-MM-AA
    r"\d{1,2}[-._]\d{1,2}[-._]\d{2}\b",
    # Día + mes en palabra + año: 19 agost 2013
    r"\d{1,2}\s+[a-záéíóúñ]{3,10}\s+\d{4}",
    # MM-AAAA
    r"\d{1,2}[-._]\d{4}",
    # DD-MM sin año
    r"\d{1,2}[-._]\d{1,2}\b",
    # AAAA suelto, siglo XXI (S035: ni un caso anterior a 2013)
    r"(19|20)\d{2}",
]
# Límite de palabra propio: el guion bajo es un separador real en estos
# nombres (`04022026_BHiRB`), no una continuación de palabra -- \w de
# Python lo trata como carácter de palabra e impediría casar una fecha
# pegada a un guion bajo. Solo letras y dígitos cuentan como
# continuación aquí; guion bajo, guion, espacio y punto son frontera.
_DATE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:%s)(?![A-Za-z0-9])" % "|".join(_DATE_PATTERNS),
    re.IGNORECASE,
)

# Separadores que se colapsan a un único espacio para contar frases
# candidatas, sin fundir palabras pegadas por guion que sí importan
# (p. ej. un código de máquina).
_SEPARATOR_RE = re.compile(r"[_,]+")
_MULTISPACE_RE = re.compile(r"\s+")

# Ruido evidente detectado en el primer barrido real sobre el corpus
# completo (S039, 2026-07-30): artefactos de sincronización de OneDrive
# /Windows, ninguno es un documento clasificable.
_JUNK_STEM_RE = re.compile(
    r"^(?:ppinfocache|00000000|whatsapp image|imagen de whatsapp)$",
    re.IGNORECASE,
)

# Fotos sueltas con nombre opaco (cámara/mensajería: puramente
# numérico o hexadecimal tipo UUID) -- pero SOLO cuando la extensión es
# de imagen. Corregido tras la segunda pasada real (S039, 2026-07-30):
# la primera versión trataba cualquier nombre puramente numérico como
# ruido, y eso metía en el saco documentos de escáner reales en PDF
# (`05032025000023.pdf`, `140703012854.pdf`) que sí tienen fecha
# reconocible y son documentación legítima -- error de categorización
# propio, corregido en la misma sesión (directriz 4.9). Los PDF/Word
# con nombre numérico siguen ahora el flujo normal de detección de
# fecha; solo las imágenes con nombre opaco se apartan como fotos.
_OPAQUE_STEM_RE = re.compile(
    r"^(?:[0-9a-f]{8,}"
    r"|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$",
    re.IGNORECASE,
)
_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "heic", "heif", "gif", "bmp"}


class Command(BaseCommand):
    help = (
        "Audita los nombres reales de un cubo indexado para cerrar el "
        "vocabulario de tipos documentales sobre el corpus completo. "
        "Solo lectura, no escribe nada."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--bucket",
            required=True,
            help="Cubo indexado a auditar (obligatorio).",
        )
        parser.add_argument(
            "--root",
            action="append",
            dest="roots",
            help=(
                "Carpeta raíz concreta a auditar (primer segmento de "
                "la ruta). Se puede repetir. Por defecto, todas las "
                "carpetas raíz reales del cubo."
            ),
        )
        parser.add_argument(
            "--top",
            type=int,
            default=40,
            help=(
                "Cuántas frases candidatas mostrar por carpeta raíz, "
                "de más a menos frecuente. Por defecto 40."
            ),
        )

    def handle(self, *args, **options):
        bucket = options["bucket"]
        if bucket not in INDEXED_BUCKETS:
            raise CommandError(
                "Cubo no indexado: %s (indexados: %s)"
                % (bucket, ", ".join(INDEXED_BUCKETS))
            )
        top_n = options["top"]

        names = list(
            DocumentIndexEntry.objects
            .filter(
                bucket=bucket,
                entry_kind=DocumentIndexEntry.KIND_FILE,
                purged_at__isnull=True,
            )
            .exclude(blob_name__startswith=QUARANTINE_PREFIX)
            .values_list("blob_name", flat=True)
        )
        if not names:
            self.stdout.write(self.style.WARNING(
                "Sin archivos indexados en %s (¿falta sembrar el "
                "índice con seed_document_index?)." % bucket
            ))
            return

        by_root = {}
        for blob_name in names:
            root = blob_name.split("/", 1)[0]
            by_root.setdefault(root, []).append(blob_name)

        selected_roots = options.get("roots") or sorted(by_root)
        unknown = [r for r in selected_roots if r not in by_root]
        if unknown:
            raise CommandError(
                "Carpeta(s) raíz sin archivos en %s: %s"
                % (bucket, ", ".join(unknown))
            )

        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== %s -- %d archivo(s), %d carpeta(s) raíz ==="
            % (bucket, len(names), len(by_root))
        ))
        for root in selected_roots:
            self._audit_root(root, by_root[root], top_n)

    def _clean_candidate(self, text):
        text = _SEPARATOR_RE.sub(" ", text)
        text = _MULTISPACE_RE.sub(" ", text).strip(" -")
        return text.upper()

    def _audit_root(self, root, blob_names, top_n):
        phrase_counts = {}
        undated = []
        junk = []

        for blob_name in blob_names:
            file_name = blob_name.rsplit("/", 1)[-1]
            if "." in file_name:
                stem, extension = file_name.rsplit(".", 1)
                extension = extension.lower()
            else:
                stem, extension = file_name, ""

            if _JUNK_STEM_RE.match(stem):
                junk.append(file_name)
                continue
            if extension in _IMAGE_EXTENSIONS and _OPAQUE_STEM_RE.match(stem):
                junk.append(file_name)
                continue

            match = _DATE_RE.search(stem)
            if not match:
                undated.append(file_name)
                continue

            before = self._clean_candidate(stem[:match.start()])
            after = self._clean_candidate(stem[match.end():])
            # Casi siempre el tipo va antes de la fecha
            # ("Z-15 CERT.MANTENIMIENTO 04-04-26"), pero en DOC.
            # PERSONAL es frecuente el patrón inverso, típico de
            # escáner ("04022026_PARTE MEDICO DE CONFIRMACION...") --
            # si no hay nada antes, se usa lo que viene después en vez
            # de descartar el archivo como si no tuviera fecha.
            candidate = before or after
            if not candidate:
                undated.append(file_name)
                continue
            phrase_counts[candidate] = phrase_counts.get(candidate, 0) + 1

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n--- %s -- %d archivo(s) ---" % (root, len(blob_names))
        ))
        self.stdout.write(
            "  %d con fecha reconocible, %d sin ella, %d ruido evidente "
            "(sync/capturas sueltas)."
            % (
                len(blob_names) - len(undated) - len(junk),
                len(undated), len(junk),
            )
        )

        ranked = sorted(
            phrase_counts.items(), key=lambda item: (-item[1], item[0]),
        )
        self.stdout.write(
            "\n  Frases candidatas a tipo, las %d más frecuentes de %d:"
            % (min(top_n, len(ranked)), len(ranked))
        )
        for phrase, count in ranked[:top_n]:
            self.stdout.write("    %5d  %s" % (count, phrase))

        if undated:
            self.stdout.write(
                "\n  Sin fecha reconocible (revisión manual, %d):"
                % len(undated)
            )
            for file_name in sorted(undated)[:top_n]:
                self.stdout.write("    %s" % file_name)
            if len(undated) > top_n:
                self.stdout.write(
                    "    ... y %d más." % (len(undated) - top_n)
                )

        if junk:
            self.stdout.write(
                "\n  Ruido evidente, muestra (%d en total):" % len(junk)
            )
            for file_name in sorted(junk)[:10]:
                self.stdout.write("    %s" % file_name)
