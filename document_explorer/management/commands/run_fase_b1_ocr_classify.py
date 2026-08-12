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

Reutiliza SIN modificar:
- `extract_text()` (S48) para el OCR/lectura real del archivo.
- `_match_candidates()`/`_resolve_document_type()` (S48/S50) para el
  mismo framework de prioridades/dosier ya usado en la heuristica de
  nombre -- la unica diferencia real es que el texto que se le pasa
  es el contenido OCR, no `entry.name`.
- `resolve_or_create_machine_asset()` para el dominio, exactamente
  igual que en Fase A.

Alcance: mismo SCOPE de `run_fase_a_sweep_scoped` (las carpetas de
maquina real confirmadas carpeta por carpeta en S50), documentos SIN
tipo, excluyendo fotos (Miguel Angel, S50: "las fotos [...] no las
vamos a subir [...] no las vamos a meter en las fichas de la
maquinaria") y nombres de escaner genericos evidentes ya cubiertos
por este mismo filtro previamente medido.

Si el OCR SI resuelve un tipo, en la misma pasada intenta tambien
extraer fecha via `classify_dates_in_text()` (mismo texto OCR, sin
descargar el archivo dos veces) cuando el tipo resuelto tiene
`tracks_expiry=True` -- evita una segunda pasada de Fase B1 clasica
sobre el mismo archivo.

DRY-RUN POR DEFECTO. `--limit N` limita cuantos procesa esta
ejecucion (por defecto 20, mismo criterio de coste que Fase B1
original -- el OCR es caro en tiempo real de servidor). Con --apply
escribe document_type/domain_content_type/domain_object_id (y fecha
si aplica) de verdad.
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
from document_explorer.management.commands.run_fase_a_sweep import (
    _resolve_document_type,
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


def _is_photo(entry):
    return bool(IMG_EXT.search(entry.name) or IMG_NAME.match(entry.name))


class Command(BaseCommand):
    help = (
        "H30 (S50) -- Fase B1 extendida: OCR para resolver TIPO "
        "documental (no solo fecha) de lo que ya agoto la heuristica "
        "de nombre, dentro del mapa acotado de maquinaria. Dry-run "
        "por defecto, --apply para escribir, --limit N (defecto 20)."
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
            "--- Fase B1 extendida (alcance acotado S50): %d candidatos "
            "en este lote (limit=%d) ---" % (len(candidatos), limit)
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
            code, dossier_pair = _resolve_document_type(
                entry, "MACHINE", text_upper,
            )

            if dossier_pair or not code:
                stats["sin_tipo_reconocible_en_ocr"] += 1
                snippet = " ".join(text.split())[:200]
                self.stdout.write(
                    "SIN TIPO  [%s] %s | texto OCR (200 char): %r"
                    % (entry.parent_path, entry.name, snippet)
                )
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
