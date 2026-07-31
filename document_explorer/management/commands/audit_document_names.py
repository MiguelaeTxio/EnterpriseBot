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

**Extended S040 (2026-07-31):** files with no recognisable date are no
longer dropped straight into the "sin fecha" bucket. A second pass
strips machine-code/plate-like tokens (old and new Spanish plate
formats, short internal codes like "A-44", leading scan ordinals like
"01.") and uses whatever text remains as the candidate type -- this
alone rescued a large share of the corpus for DOC. MAQUINAS, where the
pattern "CÓDIGO TIPO" with no date in the name is very common.

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

**Ampliado en S040 (2026-07-31):** los archivos sin fecha reconocible
ya no van directos al cajón "sin fecha". Una segunda pasada quita
tokens con forma de código de máquina/matrícula (formatos de matrícula
española antigua y moderna, códigos internos cortos tipo "A-44",
prefijos ordinales de escaneo tipo "01.") y usa lo que queda como
candidato de tipo -- por sí solo esto rescató buena parte del corpus
en DOC. MAQUINAS, donde el patrón "CÓDIGO TIPO" sin fecha en el nombre
es muy frecuente.
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
    r"|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    # Prefijo de cámara/WhatsApp IMG, confirmado con datos reales
    # (S039, 2026-07-30): "IMG 1", "IMG-20160208-WA0000",
    # "IMG-20230208-WA0011 (1)" -- siempre que lo que sigue a "IMG" (y
    # al "WA" opcional) sean solo dígitos, espacios, guiones,
    # paréntesis o corchetes. Restringido a extensión de imagen (ver
    # _IMAGE_EXTENSIONS más abajo): existe al menos un caso real,
    # `IMG-20250408-WA0019[1].pdf`, con el mismo patrón de nombre pero
    # que sí es un documento real -- ese nunca debe caer aquí, y no
    # cae porque la extensión no es de imagen.
    r"|img(?:wa|[\d\s\-_()\[\].])*"
    r")$",
    re.IGNORECASE,
)
_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "heic", "heif", "gif", "bmp"}

# Código de máquina / matrícula (S040, ampliación tras auditar el
# corpus completo): 41% de DOC. MAQUINAS y 35% de DOC. PERSONAL no
# tienen fecha reconocible en el nombre, y la mayoría de esos SÍ
# tienen un tipo legible una vez se quita el código -- p. ej.
# "0069-GXX FICHA TECNICA.pdf", "0168-DZS SEGURO.pdf",
# "03.CE A-44 E-5250-BDP.pdf". Sin esto, ese 38% largo del corpus
# quedaba fuera del vocabulario candidato.
#
# Tres familias, confirmadas contra las frases candidatas reales de la
# primera pasada sobre el corpus completo (S040, 2026-07-31):
_MACHINE_CODE_PATTERNS = [
    # Matrícula antigua con letra de provincia: MA-00377-R, GI-0877-R,
    # SE-02681-R.
    r"[A-Z]{1,2}-\d{4,5}-[A-Z]",
    # Matrícula moderna, con o sin guion, con o sin prefijo de letra
    # interna de la empresa (E-/R-/G-...): E-5250-BDP, 8992-FCK,
    # 8992FCK, R3166BCG, R-7991-BBV, 00964-GTM (4 o 5 dígitos, visto
    # en el corpus real).
    r"(?:[A-Z]-)?\d{4,5}[- ]?[A-Z]{3}",
    # Código corto interno de máquina: A-44, G-03, Z-15, B-27.
    r"[A-Z]-\d{1,3}",
    # Prefijo numérico ordinal de archivo escaneado: "01.", "02.".
    r"\d{1,2}\.",
]
_MACHINE_CODE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:%s)(?![A-Za-z0-9])" % "|".join(_MACHINE_CODE_PATTERNS),
    re.IGNORECASE,
)


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
        rescued_via_code = 0
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
            if match:
                before = self._clean_candidate(stem[:match.start()])
                after = self._clean_candidate(stem[match.end():])
                # Casi siempre el tipo va antes de la fecha
                # ("Z-15 CERT.MANTENIMIENTO 04-04-26"), pero en DOC.
                # PERSONAL es frecuente el patrón inverso, típico de
                # escáner ("04022026_PARTE MEDICO DE CONFIRMACION...")
                # -- si no hay nada antes, se usa lo que viene después
                # en vez de descartar el archivo como si no tuviera
                # fecha.
                candidate = before or after
                if candidate:
                    phrase_counts[candidate] = (
                        phrase_counts.get(candidate, 0) + 1
                    )
                    continue

            # Sin fecha reconocible (o fecha encontrada pero sin nada
            # legible alrededor) -- S040: en vez de descartar
            # directamente, se intenta quitar el código de
            # máquina/matrícula y usar lo que quede como candidato.
            # Cubre el patrón muy frecuente en DOC. MAQUINAS de
            # "CÓDIGO TIPO" sin fecha en el nombre.
            without_code = _MACHINE_CODE_RE.sub(" ", stem)
            candidate = self._clean_candidate(without_code)
            if candidate:
                phrase_counts[candidate] = phrase_counts.get(candidate, 0) + 1
                rescued_via_code += 1
                continue

            undated.append(file_name)

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n--- %s -- %d archivo(s) ---" % (root, len(blob_names))
        ))
        self.stdout.write(
            "  %d con fecha reconocible, %d rescatados sin fecha "
            "(código de máquina/matrícula quitado), %d sin ningún tipo "
            "legible, %d ruido evidente (sync/capturas sueltas)."
            % (
                len(blob_names) - len(undated) - len(junk) - rescued_via_code,
                rescued_via_code, len(undated), len(junk),
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
                "\n  Sin ningún tipo legible (revisión manual, %d):"
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
