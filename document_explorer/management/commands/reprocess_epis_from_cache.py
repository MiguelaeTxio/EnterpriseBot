# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/reprocess_epis_from_cache.py
"""
H30 (S82) -- reprocesa los DocumentIndexEntry tipo EPIS que ya tienen
`ocr_text` cacheado (leidos por `extract_epis_deliveries_vm.py` en un
barrido anterior, pero que quedaron sin resolver -- SIN DNI, SIN
PersonIdentity, o SIN ITEMS) contra los dos arreglos reales de hoy:

1. Soporte de NIE (letra X/Y/Z) en la extraccion de DNI -- antes solo
   aceptaba digitos, perdiendo a cualquier trabajador extranjero
   (confirmado real: Petru Iordachi, NIE X6854905P).
2. Fallback de plantilla sin marcas de casilla -- documentos que
   listan los EPIs entregados con guion, sin ninguna X (confirmado
   real: Zafra Peralta, Ruiz Leiva).

Deliberadamente NO reintenta la lectura por tabla/posicion espacial
de palabras (`_parse_marked_labels_spatial`) -- esa informacion NO
se cacheo en su dia, solo el texto plano. Los documentos cuyo unico
problema era la tabla con marcas (no el DNI ni la plantilla) siguen
sin resolverse aqui; para esos hace falta un barrido nuevo con
OCR real (VM), fuera de alcance de este comando.

No toca GCS ni Tesseract -- coste de CPU minimo, seguro de ejecutar
en la consola Bash de PythonAnywhere (com-standards, tabla de coste
de OCR: esto no es OCR, es solo regex sobre texto ya guardado).

DRY-RUN POR DEFECTO. Con --apply escribe de verdad: crea EpiDelivery
(mismo chequeo de duplicados por person+epi+delivery_date que ya usa
extract_epis_deliveries_vm.py) y archiva (deleted_at) el documento
original cuando todos sus items quedan resueltos.
"""
import re
import unicodedata

from django.core.management.base import BaseCommand
from django.utils import timezone

from document_explorer.classification_service import trash_dossier_entry
from document_explorer.models import DocumentIndexEntry, EpiDelivery, EpiItemCatalog, PersonIdentity

# ----------------------------------------------------------------------
# Duplicado a proposito de h28_migration_agent/extract_epis_deliveries_vm.py
# -- ese script corre en un venv aparte en la VM, sin Django instalado,
# no puede importar de este proyecto. Misma logica exacta, verificada
# hoy contra 4 documentos reales (S82).
# ----------------------------------------------------------------------

_DNI_LETTER_TABLE = "TRWAGMYFPDXBNJZSQVHLCKE"
_DNI_DIGITS_RE = re.compile(
    r"D\.?\s*N\.?\s*[I1]\.?\s*[:.]?\s*([XYZxyz]?[0-9]{1,2}[.\s]?[0-9]{3}[.\s]?[0-9]{3})"
)
_NIE_PREFIX_MAP = {"X": "0", "Y": "1", "Z": "2"}

_FILENAME_DATE_RE = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{2,4})")
_CONTENT_DATE_RE = re.compile(
    r"(?:A\s+fecha|FECHA)\s*[:.(]?\s*(\d{1,2})\s*[/-]\s*(\d{1,2})\s*[/-]\s*(\d{2,4})",
    re.IGNORECASE,
)

ITEM_LABEL_MAP = [
    ("MASCARILLA FILTRO ANTIPARTICULAS", "MASCARILLA_FILTRO_ANTIPARTICULAS"),
    ("MASCARILLA CON FILTRO ANTI PARTICULAS", "MASCARILLA_FILTRO_ANTIPARTICULAS"),
    ("MASCARILLA BUCONASAL", "MASCARILLA_BUCONASAL"),
    ("MASCARA MEDIA", "MASCARA_MEDIA_RESPIRADOR"),
    ("MASCARA SOLDAR", "MASCARA_SOLDAR"),
    ("MASCARA DE SOLDAR", "MASCARA_SOLDAR"),
    ("CARETA DE PROTECCION", "CARETA_PROTECCION"),
    ("FILTROS VAPORES", "FILTRO_VAPORES_GASES_ACIDOS"),
    ("RETENEDOR DE FILTROS", "RETENEDOR_FILTROS"),
    ("BOLSA PORTARESPIRADOR", "BOLSA_PORTARRESPIRADOR"),
    ("BOLSA PORTARRESPIRADOR", "BOLSA_PORTARRESPIRADOR"),
    ("PREFILTRO P3", "PREFILTRO_P3"),
    ("FILTRO PARTICULAS", "PREFILTRO_P3"),
    ("GUANTES DE ACCION MECANICA Y QUIMICA", "GUANTES_MECANICA_QUIMICA"),
    ("GUANTES DE ACCION QUIMICA", "GUANTES_QUIMICA"),
    ("GUANTES ACCION QUIMICA", "GUANTES_QUIMICA"),
    ("GUANTES DE ACCION MECANICA", "GUANTES_MECANICA"),
    ("GUANTES ACCION MECANICA", "GUANTES_MECANICA"),
    ("GUANTES DE PROTECCION", "GUANTES_PROTECCION"),
    ("TRAJE DE AGUA", "TRAJE_AGUA"),
    ("POLAR", "POLAR"),
    ("BUZO DE TRABAJO", "BUZO_ALTA_VISIBILIDAD"),
    ("PANTALON DE TRABAJO", "PANTALON_ALTA_VISIBILIDAD"),
    ("PANTALON", "PANTALON_ALTA_VISIBILIDAD"),
    ("POLO MANGA CORTA", "POLO_ALTA_VISIBILIDAD"),
    ("POLO", "POLO_ALTA_VISIBILIDAD"),
    ("MONO DE TRABAJO", "MONO_ALTA_VISIBILIDAD"),
    ("CHAQUETA", "CHAQUETA_ALTA_VISIBILIDAD"),
    ("CINTURON DE SEG", "CINTURON_DOS_AMARRES"),
    ("ELEMENTO DE AMARRE", "ELEMENTO_AMARRE"),
    ("ARNE", "ARNES_SEGURIDAD"),
    ("ROPA IGNIFUGA", "ROPA_IGNIFUGA_ARCO"),
    ("ROPA INGNIFUGA", "ROPA_IGNIFUGA_ARCO"),
    ("ROPA DE TRABAJO", "ROPA_TRABAJO"),
    ("CASCO", "CASCO_SEGURIDAD"),
    ("CHALECO REFLECTANTE", "CHALECO_REFLECTANTE"),
    ("ZAPATOS DE SEGURIDAD", "ZAPATOS_SEGURIDAD"),
    ("PROTECCION AUDITIVA", "PROTECCION_AUDITIVA"),
    ("ROPA DE SENALIZACION", "BUZO_ALTA_VISIBILIDAD"),
    ("GAFAS", "GAFAS_ANTIPARTICULAS"),
]
ITEM_LABEL_MAP.append(("GUANTES", "GUANTES_PROTECCION"))

_NON_DELIVERY_SIGNALS = [
    ("CERTIFICADO DE PARTICIPACION", "FORMACION"),
    ("ACCION FORMATIVA", "FORMACION"),
    ("ENTREGA DE INFORMACION EN PREVENCION", "ENTREGA_INFORMACION"),
    ("AUTORIZACION DE MANEJO DE MAQUINARIA", "AUTORIZACION_USO_MAQUINARIA"),
    ("NUMERO DE ALBARAN", "OTROS_DOCUMENTOS"),
    ("ABONO IMPARTICION", "OTROS_DOCUMENTOS"),
    ("BASE IMPONIBLE", "OTROS_DOCUMENTOS"),
]


def _normalize(label):
    label = unicodedata.normalize("NFKD", (label or "").upper())
    label = "".join(c for c in label if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", label).strip()


def _map_label(label):
    norm = _normalize(label)
    for phrase, code in ITEM_LABEL_MAP:
        if phrase in norm:
            return code
    return None


_REAL_EPIS_HEADER_RE = re.compile(
    r"ENTREGA DE EPI|SE HACE ENTREGA A|LA EMPRESA HA HECHO ENTREGA"
    r"|EQUIPO.{0,80}PROTECCI[OÓ]N INDIVIDUAL.{0,400}?ENTREGAD[OA]S?"
    r".{0,60}TRABAJADOR",
    re.IGNORECASE | re.DOTALL,
)


def _detect_non_delivery(text):
    if _REAL_EPIS_HEADER_RE.search(text):
        return None
    norm = _normalize(text)
    for signal, suggested_code in _NON_DELIVERY_SIGNALS:
        if signal in norm:
            return suggested_code
    return None


def _compute_full_dni(digits):
    clean = re.sub(r"[.\s]", "", digits).upper()
    if not clean:
        return None
    prefix = clean[0] if clean[0] in _NIE_PREFIX_MAP else ""
    numeric_str = (
        _NIE_PREFIX_MAP[prefix] + clean[1:] if prefix else clean
    )
    if not numeric_str.isdigit():
        return None
    control = _DNI_LETTER_TABLE[int(numeric_str) % 23]
    return clean + control


def _parse_dni(text):
    dni_match = _DNI_DIGITS_RE.search(text)
    return _compute_full_dni(dni_match.group(1)) if dni_match else None


def _normalize_dni(dni):
    return re.sub(r"[.\s\-]", "", dni).upper()


def _parse_date_from_filename(name):
    match = _FILENAME_DATE_RE.search(name)
    if not match:
        return None
    day, month, year = match.groups()
    return _build_date(day, month, year)


def _parse_date_from_content(text):
    match = _CONTENT_DATE_RE.search(text)
    if not match:
        return None
    day, month, year = match.groups()
    return _build_date(day, month, year)


def _build_date(day, month, year):
    import datetime
    try:
        day, month = int(day), int(month)
        year = int(year)
        if year < 100:
            year += 2000
        # S82: sanity real -- 2 fechas imposibles (2041, 0201) en la
        # muestra de hoy, ambas con toda pinta de digito transpuesto
        # por OCR (14->41) o año mal formado. Los documentos de este
        # lote son historicos, nunca antes de 2005 ni posteriores a
        # hoy -- fuera de ese rango, se descarta en vez de crear un
        # registro con fecha imposible.
        hoy = datetime.date.today()
        if not (2005 <= year <= hoy.year):
            return None
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _parse_plain_list_items(text):
    match = re.search(
        r"EQUIPO.{0,80}PROTECCI[OÓ]N INDIVIDUAL.{0,400}?ENTREGAD[OA]S?"
        r".{0,60}TRABAJADOR",
        text, re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return set()
    start = match.end()
    next_section = re.search(r"\n\s*\d+[oº°]?[-.]", text[start:])
    end = start + next_section.start() if next_section else len(text)
    block = text[start:end]
    codes = set()
    for fragment in re.split(r"[-\u2010-\u2015\u2018-\u201F]", block):
        fragment = fragment.strip()
        if not fragment:
            continue
        code = _map_label(fragment)
        if code:
            codes.add(code)
    return codes


class Command(BaseCommand):
    help = (
        "H30 (S82) -- reprocesa EPIS con ocr_text ya cacheado contra "
        "los arreglos de NIE y plantilla sin marcas, sin tocar GCS ni "
        "OCR. Dry-run por defecto, usar --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        qs = DocumentIndexEntry.objects.filter(
            document_type__code="EPIS",
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
        ).exclude(ocr_text__in=["", None])

        stats = {
            "total_candidatos": qs.count(),
            "no_es_entrega": 0,
            "sin_dni": 0,
            "dni_sin_person_identity": 0,
            "sin_fecha": 0,
            "sin_items": 0,
            "resueltos_nie": 0,
            "resueltos_lista_plana": 0,
            "documentos_completos": 0,
            "deliveries_creadas": 0,
        }

        for entry in qs.iterator():
            text = entry.ocr_text

            no_delivery = _detect_non_delivery(text)
            if no_delivery:
                stats["no_es_entrega"] += 1
                continue

            dni = _parse_dni(text)
            if not dni:
                stats["sin_dni"] += 1
                continue
            es_nie = dni[0] in _NIE_PREFIX_MAP

            person = PersonIdentity.objects.filter(
                dni=_normalize_dni(dni),
            ).first()
            if person is None:
                stats["dni_sin_person_identity"] += 1
                continue

            date_ = (
                _parse_date_from_filename(entry.name)
                or _parse_date_from_content(text)
            )
            if not date_:
                stats["sin_fecha"] += 1
                continue

            codes = _parse_plain_list_items(text)
            if not codes:
                stats["sin_items"] += 1
                continue

            if es_nie:
                stats["resueltos_nie"] += 1
            else:
                stats["resueltos_lista_plana"] += 1

            self.stdout.write(
                "%s  id=%d  persona=%s  dni=%s  fecha=%s  items=%s  [%s]"
                % (
                    "APLICADO" if apply_changes else "CANDIDATO",
                    entry.pk, person, dni, date_, sorted(codes),
                    entry.name,
                )
            )

            if not apply_changes:
                continue

            catalog_by_code = {
                e.code: e.pk
                for e in EpiItemCatalog.objects.filter(code__in=codes)
            }
            created_this_doc = 0
            new_rows_this_doc = 0
            for code in codes:
                epi_pk = catalog_by_code.get(code)
                if epi_pk is None:
                    continue
                created_this_doc += 1
                _, created = EpiDelivery.objects.get_or_create(
                    person=person,
                    epi_id=epi_pk,
                    delivery_date=date_,
                    defaults={
                        "source_entry": entry,
                        "extraction_method": EpiDelivery.METHOD_HEURISTIC,
                    },
                )
                if created:
                    new_rows_this_doc += 1

            stats["deliveries_creadas"] += new_rows_this_doc
            if created_this_doc == len(codes):
                trashed = trash_dossier_entry(entry)
                if trashed:
                    stats["documentos_completos"] += 1

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
