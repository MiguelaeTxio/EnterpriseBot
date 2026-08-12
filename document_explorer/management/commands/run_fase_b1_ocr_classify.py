# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/run_fase_b1_ocr_classify.py
"""
H30 (S50) -- Fase B1 extendida: usa el mismo motor de OCR ya
construido en S48 (`date_verification_service.extract_text`) no solo
para fechas, sino para intentar resolver el TIPO documental de los
archivos que agotaron ya la heuristica de nombre (Fase A) dentro del
mapa acotado confirmado en S50 (`run_fase_a_sweep_scoped.SCOPE`).

Origen real, Miguel Angel verbatim (S50), al pedir lanzar la fase
OCR: "no solamente para las fechas de los archivos conocidos, sino
para saber si podemos encuadrar parte de los desconocidos" --
correccion explicita de alcance frente al Fase B1 original
(`run_fase_b1_ocr_dates.py`), que solo procesa documentos que YA
tienen `document_type` asignado y `tracks_expiry=True`.

CORREGIDO EN LA MISMA SESION (S50): la primera version reutilizaba
`_match_candidates()`/`_resolve_document_type()` tal cual (el mismo
framework de palabra suelta que usa la heuristica de NOMBRE) pasandole
el texto OCR en vez del nombre de archivo. Se detectaron 2 falsos
positivos reales en el primer lote de prueba: un informe de
mantenimiento que mencionaba "ITV" de pasada se clasifico como ITV;
una lista de chequeo que mencionaba "CE" se clasifico como CE. Un
nombre de archivo es corto y deliberado -- el cuerpo de un documento
es largo, en lenguaje natural, y puede mencionar un concepto sin SER
ese tipo de documento.

Corregido construyendo CONTENT_MARKERS a partir de patrones REALES
descubiertos con `sample_known_type_ocr_text` (S50): frases largas y
especificas que aparecieron de forma consistente en 3 ejemplos reales
de cada tipo ya confirmado (nunca palabras sueltas de una sola
palabra como "CE" o "ITV", que son las que causaban los falsos
positivos). Si el texto OCR coincide con marcadores de MAS de un tipo
a la vez, se considera ambiguo y no se resuelve -- mejor dejarlo sin
tipo que asignar mal.

IPO_ITC (migracion 0031, S50): fusionados porque el contenido real es
literalmente el mismo documento (acta de inspeccion periodica de
grua/plataforma) -- no hay marcador de contenido que distinga IPO de
ITC, por eso ahora es un solo tipo.

Alcance: mismo SCOPE de `run_fase_a_sweep_scoped`, documentos SIN
tipo, excluyendo fotos (Miguel Angel, S50: "las fotos [...] no las
vamos a meter en las fichas de la maquinaria").

Si el tipo resuelto tiene `tracks_expiry=True`, en la misma pasada
intenta tambien `classify_dates_in_text()` sobre el mismo texto OCR
ya extraido -- evita una segunda descarga/OCR del mismo archivo.

DRY-RUN POR DEFECTO. `--limit N` (defecto 20, el OCR es caro en
tiempo real de servidor). Con --apply escribe document_type/
domain_content_type/domain_object_id (y fecha si aplica) de verdad.
"""
import re

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.classification_service import (
    resolve_or_create_machine_asset,
)
from document_explorer.date_verification_service import (
    classify_dates_in_text, extract_text,
)
from document_explorer.management.commands.calibrate_fase_a_keywords import (
    _strip_accents,
)
from document_explorer.management.commands.run_fase_a_sweep_scoped import (
    _scoped_files,
)
from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog
from fleet.models import MachineAsset
from spare_parts.gcs_service import download_bytes

IMG_EXT = re.compile(r"\.(jpe?g|png|heic|gif|bmp|tiff?)$", re.IGNORECASE)
IMG_NAME = re.compile(
    r"^(img[-_]|whatsapp image|imagen de whatsapp|foto\b|_?foto\b)",
    re.IGNORECASE,
)

# Descubiertos con sample_known_type_ocr_text (S50), 3 ejemplos reales
# por tipo -- ver EnterpriseBot_055_GET.txt de la sesion. Frases
# largas y especificas a proposito, nunca palabras sueltas de una
# sola palabra (esas ya demostraron dar falsos positivos).
CONTENT_MARKERS = {
    "CE": [
        "DECLARACION DE CONFORMIDAD", "DECLARATION DE CONFORMITE",
        "DECLARATION OF CONFORMITY",
    ],
    "CERT_MANTENIMIENTO": [
        "REALIZA TODAS SUS REVISIONES DE MANTENIMIENTO",
        "COMO EMPRESA CONSERVADORA",
    ],
    "TARJETA_TRANSPORTE": ["TARJETA DE TRANSPORTE"],
    "SEGURO": ["DOMICILIACION DE PAGOS", "COMUNICACION OPERACION EN CUENTA"],
    "POLIZA_SEGURO": [
        "CONDICIONES PARTICULARES DEL SEGURO", "POLIZA DE SEGURO",
    ],
    "DECLARACION_HOMOLOGACION": [
        "HOMOLOGACION INDIVIDUAL", "CERTIFICADO DE HOMOLOGACION",
    ],
    "OCA": ["OCA GLOBAL", "ACREDITADO POR ENAC"],
    "C_ADECUACION": [
        "CERTIFICADO DE ADECUACION",
        "CONDICIONES DE SEGURIDAD Y SALUD EN LAS MAQUINAS",
    ],
    "IPO_ITC": [
        "ACTA DE INSPECCION PERIODICA", "INSPECCION PERIODICA OFICIAL",
        "INSPECCION PERIODICA DE GRUAS MOVILES",
    ],
}


def _is_photo(entry):
    return bool(IMG_EXT.search(entry.name) or IMG_NAME.match(entry.name))


def _match_content(text_upper):
    """
    Devuelve (code, None) si el texto coincide con los marcadores de
    EXACTAMENTE un tipo, o (None, matched_codes) si coincide con mas
    de uno a la vez (ambiguo, no se resuelve).
    """
    matched = set()
    for code, phrases in CONTENT_MARKERS.items():
        for phrase in phrases:
            if phrase in text_upper:
                matched.add(code)
                break
    if len(matched) == 1:
        return next(iter(matched)), None
    if len(matched) > 1:
        return None, matched
    return None, None


class Command(BaseCommand):
    help = (
        "H30 (S50) -- Fase B1 extendida: OCR con marcadores de "
        "contenido reales (frase larga, no palabra suelta) para "
        "resolver TIPO documental. Dry-run por defecto, --apply para "
        "escribir, --limit N (defecto 20)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        limit = options["limit"]
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        type_catalog = {
            t.code: t
            for t in DocumentTypeCatalog.objects.filter(is_active=True)
        }

        stats = {
            "tipo_resuelto_por_ocr": 0,
            "tipo_y_fecha_resueltos": 0,
            "dominio_sin_resolver": 0,
            "sin_tipo_reconocible_en_ocr": 0,
            "ambiguo_varios_marcadores": 0,
            "extension_no_soportada": 0,
            "error_descarga_u_ocr": 0,
            "fotos_excluidas": 0,
        }

        candidatos = []
        for e in _scoped_files().only(
            "id", "name", "parent_path", "bucket", "blob_name",
        ).order_by("id"):
            if _is_photo(e):
                stats["fotos_excluidas"] += 1
                continue
            candidatos.append(e)
            if len(candidatos) >= limit:
                break

        self.stdout.write(
            "--- Fase B1 extendida, marcadores de contenido reales "
            "(alcance acotado S50): %d candidatos en este lote "
            "(limit=%d) ---" % (len(candidatos), limit)
        )

        for entry in candidatos:
            try:
                data = download_bytes(entry.bucket, entry.blob_name)
                text = extract_text(entry.name, data)
            except Exception as exc:
                stats["error_descarga_u_ocr"] += 1
                self.stdout.write(
                    "ERROR [%s] %s -- %s"
                    % (entry.parent_path, entry.name, exc)
                )
                continue

            if text is None:
                stats["extension_no_soportada"] += 1
                continue

            text_upper = _strip_accents(text).upper()
            code, ambiguous = _match_content(text_upper)

            if ambiguous:
                stats["ambiguo_varios_marcadores"] += 1
                self.stdout.write(
                    "AMBIGUO (%s)  [%s] %s"
                    % (sorted(ambiguous), entry.parent_path, entry.name)
                )
                continue

            if not code:
                stats["sin_tipo_reconocible_en_ocr"] += 1
                continue

            asset = resolve_or_create_machine_asset(entry, {})
            if not asset:
                stats["dominio_sin_resolver"] += 1
                self.stdout.write(
                    "TIPO OK POR OCR, DOMINIO SIN RESOLVER  [%s] %s -> %s"
                    % (entry.parent_path, entry.name, code)
                )
                continue

            doc_type = type_catalog[code]
            expiry_date = issue_date = None
            if doc_type.tracks_expiry:
                expiry, issue, _other = classify_dates_in_text(text)
                expiry_date, issue_date = expiry, issue

            if expiry_date or issue_date:
                stats["tipo_y_fecha_resueltos"] += 1
                self.stdout.write(
                    "TIPO+FECHA POR OCR  [%s] %s -> %s (expiry=%s issue=%s)"
                    % (
                        entry.parent_path, entry.name, code,
                        expiry_date, issue_date,
                    )
                )
            else:
                stats["tipo_resuelto_por_ocr"] += 1
                self.stdout.write(
                    "TIPO POR OCR  [%s] %s -> %s"
                    % (entry.parent_path, entry.name, code)
                )

            if apply_changes:
                entry.document_type = doc_type
                entry.domain_content_type = machine_ct
                entry.domain_object_id = asset.pk
                update_fields = [
                    "document_type", "domain_content_type",
                    "domain_object_id",
                ]
                if expiry_date:
                    entry.expiry_date = expiry_date
                    update_fields.append("expiry_date")
                if issue_date:
                    entry.issue_date = issue_date
                    update_fields.append("issue_date")
                entry.save(update_fields=update_fields)

        self.stdout.write("=== RESUMEN (%s, limit=%d) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito", limit,
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
