# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/audit_manual_models.py
"""
Django management command: audit_manual_models.

H29, S041 -- primer paso de la tarea "un solo manual por modelo real
de máquina", a petición explícita de Miguel Ángel: antes de tocar
nada (ni `fleet.MachineAsset` en producción, ni los propios archivos
de manuales), auditar con datos reales qué modelo dice cada manual
que es de verdad, y compararlo contra el `brand_model` que hoy tiene
en base de datos la máquina de la que vino ese manual.

Origen real: 178 archivos ya viven en una carpeta compartida
("MANUALES DE USO", movidos ahí en S039/S040 con la herramienta de
mover), pero sin ninguna limpieza ni asociación por modelo -- varias
variantes del mismo manual por máquina ("-comp", "-opt", "opt2",
"PORTADA E INDICE"...), y ninguna forma de saber, desde la ficha de
una máquina, cuál es "su" manual. Antes de decidir el mecanismo de
asociación (modelo de datos nuevo, ver anexo H29 3.39/3.40) y antes
de deduplicar nada, hace falta saber con certeza, por cada manual:
de qué máquina vino (por el nombre de archivo -- ya no vive en la
carpeta de esa máquina) y qué modelo real dice el propio documento
que es.

Solo lectura. No escribe nada en `fleet.MachineAsset`, no mueve, no
borra, no renombra ningún archivo. Hace llamadas reales a Gemini (una
por manual) -- usar `--limit` para probar sobre un subconjunto antes
de lanzarlo sobre los 178.

Reutiliza la maquinaria ya validada de `classification_service`
(recorte de PDF a las primeras páginas, reintento ante 429, cliente
Gemini compartido) en vez de reinventarla -- mismo principio DRY que
el resto del proyecto.

Uso:
    python -m dotenv run python manage.py audit_manual_models \
        --bucket cgs_grupo_alvarez
    python -m dotenv run python manage.py audit_manual_models \
        --bucket cgs_grupo_alvarez --limit 10

---

Comando de gestión Django: audit_manual_models.

H29, S041 -- primer paso de la tarea "un solo manual por modelo real
de máquina", a petición explícita de Miguel Ángel: antes de tocar
nada (ni `fleet.MachineAsset` en producción, ni los propios archivos
de manuales), auditar con datos reales qué modelo dice cada manual
que es de verdad, y compararlo contra el `brand_model` que hoy tiene
en base de datos la máquina de la que vino ese manual.

Origen real: 178 archivos ya viven en una carpeta compartida
("MANUALES DE USO", movidos ahí en S039/S040 con la herramienta de
mover), pero sin ninguna limpieza ni asociación por modelo -- varias
variantes del mismo manual por máquina ("-comp", "-opt", "opt2",
"PORTADA E INDICE"...), y ninguna forma de saber, desde la ficha de
una máquina, cuál es "su" manual. Antes de decidir el mecanismo de
asociación (modelo de datos nuevo, ver anexo H29 3.39/3.40) y antes
de deduplicar nada, hace falta saber con certeza, por cada manual: de
qué máquina vino (por el nombre de archivo -- ya no vive en la
carpeta de esa máquina) y qué modelo real dice el propio documento
que es.

Solo lectura. No escribe nada en `fleet.MachineAsset`, no mueve, no
borra, no renombra ningún archivo. Hace llamadas reales a Gemini (una
por manual) -- usar `--limit` para probar sobre un subconjunto antes
de lanzarlo sobre los 178.

Reutiliza la maquinaria ya validada de `classification_service`
(recorte de PDF a las primeras páginas, reintento ante 429, cliente
Gemini compartido) en vez de reinventarla -- mismo principio DRY que
el resto del proyecto.
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from google.genai.types import GenerateContentConfig, HttpOptions, Part

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from document_explorer.classification_service import (
    _FOLDER_MACHINE_CODE_RE,
    _extract_pdf_edges,
    _generate_content_with_retry,
)
from document_explorer.models import DocumentIndexEntry
from fleet.models import MachineAsset
from spare_parts.gcs_service import download_bytes

_MANUAL_MODEL_SCHEMA = {
    "type": "object",
    "properties": {
        "brand_model": {"type": "string"},
        "confidence": {"type": "string", "enum": ["ALTA", "MEDIA", "BAJA"]},
        "reasoning": {"type": "string"},
    },
    "required": ["brand_model", "confidence", "reasoning"],
}

_MANUAL_MODEL_PROMPT = (
    "Eres un asistente que identifica la marca y el modelo real de una "
    "máquina a partir de su manual de uso/instrucciones (PDF). Busca en "
    "las primeras páginas (portada, título, cabecera) la denominación "
    "comercial EXACTA que da el propio FABRICANTE -- marca + modelo "
    '(p. ej. "LIEBHERR LTM 1230-5.1", "GENIE GTH-2506", "AUSA T 235 H"). '
    "NUNCA un código interno de flota de la empresa (tipo \"A-29\"), "
    "NUNCA una matrícula. Da tu mejor estimación siempre, aunque la "
    "confianza sea baja -- explica en reasoning qué has encontrado y "
    "por qué la confianza es la que es."
)

# Mismo umbral que classification_service (PDF > 45 MB se descarga y
# recorta antes de llamar) -- aquí se aplica siempre, sin condicional,
# porque para identificar el modelo real basta la portada/primeras
# páginas y descargar+recortar de menos es más barato y más fiable
# que decidir caso a caso por tamaño.
_MANUAL_EXCERPT_PAGES = 3


class Command(BaseCommand):
    help = (
        "Auditoría de solo lectura: para cada manual real bajo una "
        "carpeta de manuales, extrae con Gemini el modelo real "
        "(marca+modelo del fabricante) y lo compara contra el "
        "brand_model actual en fleet.MachineAsset de la máquina de "
        "origen (resuelta por el nombre de archivo). No escribe nada."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--bucket",
            required=True,
            help="Cubo indexado a auditar (obligatorio).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help=(
                "Máximo de manuales a procesar, para probar sobre un "
                "subconjunto antes de lanzarlo sobre el corpus "
                "completo. Por defecto, todos."
            ),
        )

    def handle(self, *args, **options):
        bucket = options["bucket"]
        limit = options["limit"]

        manuals = list(
            DocumentIndexEntry.objects.filter(
                bucket=bucket,
                entry_kind=DocumentIndexEntry.KIND_FILE,
                deleted_at__isnull=True,
                purged_at__isnull=True,
                parent_path__icontains="MANUAL",
            )
            # Bug real S041, primera corrida: "MANUAL" sin más también
            # casaba con DOC. PERSONAL/ENTREGA MANUAL COMBUSTIBLE (120
            # de 339 archivos, nada que ver con manuales de máquina --
            # gastó llamadas reales a Gemini y fue la causa de la
            # mayoría de los fallos de extracción). Un manual es por
            # definición un concepto de dominio MÁQUINA, nunca de
            # personal -- exclusión de principio, no un parche puntual.
            .exclude(parent_path__istartswith="DOC. PERSONAL")
            .order_by("parent_path", "name")
        )
        if not manuals:
            raise CommandError(
                "Sin archivos vivos con 'MANUAL' en parent_path en %s "
                "(fuera de DOC. PERSONAL)." % bucket
            )
        if limit:
            manuals = manuals[:limit]

        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== %d manual(es) a auditar (bucket=%s) ===" % (
                len(manuals), bucket,
            )
        ))
        self._print_folder_fragmentation(manuals)

        client = get_gemini_client()
        rows = []
        for index, entry in enumerate(manuals, start=1):
            self.stdout.write(
                "\n[%d/%d] %s / %s (%.1f MB)" % (
                    index, len(manuals), entry.parent_path, entry.name,
                    (entry.size_bytes or 0) / (1024 * 1024),
                )
            )
            # Bug real S044: una espera larga de reintentos de Gemini
            # (504 DEADLINE_EXCEEDED, 60s x 2) deja la conexión MySQL
            # inactiva más tiempo que `wait_timeout` del servidor --
            # MySQL la cierra sola, y la siguiente consulta del ORM
            # revienta con OperationalError 4031, tumbando todo el
            # comando en el archivo 2 de 291. close_old_connections()
            # fuerza a Django a abrir una conexión nueva si la que
            # tenía ya no es válida, sin cambiar nada del resto de la
            # lógica (mismo patrón que Django recomienda para tareas de
            # fondo de larga duración).
            close_old_connections()
            try:
                row = self._audit_one(client, entry)
            except Exception as exc:
                # Aislado por entrada: un fallo real e inesperado en un
                # manual (BD, GCS, lo que sea) no debe tirar los otros
                # 290 ya en cola -- se registra y se sigue, igual
                # criterio que los `except Exception` ya existentes
                # dentro de `_audit_one` para Gemini/descarga.
                self.stdout.write(self.style.ERROR(
                    "  Fallo inesperado, se omite esta entrada: %s" % exc
                ))
                row = None
            if row:
                rows.append(row)
                self.stdout.write(
                    "  código=%s -- BD.brand_model=%r -- "
                    "manual.brand_model=%r (%s) -- %s" % (
                        row["code"] or "?", row["db_model"],
                        row["manual_model"], row["confidence"],
                        "COINCIDE" if row["match"] else "REVISAR",
                    )
                )

        self._print_summary(rows)

    def _print_folder_fragmentation(self, manuals):
        by_folder = {}
        for entry in manuals:
            by_folder[entry.parent_path] = (
                by_folder.get(entry.parent_path, 0) + 1
            )
        self.stdout.write("\nCarpetas reales con manuales, fragmentación:")
        for folder, count in sorted(by_folder.items()):
            self.stdout.write("  %5d  %s" % (count, folder or "(raíz)"))

    def _extract_candidate_code(self, text: str) -> str | None:
        # Insensible a mayúsculas (bug real S041: nombres de archivo
        # reales en minúsculas, p. ej. "a29.pdf", no casaban con el
        # regex compartido que asume mayúsculas como las carpetas).
        for word in text.strip().split():
            match = _FOLDER_MACHINE_CODE_RE.match(word.upper())
            if match:
                return match.group(1).replace("-", "")
        return None

    def _resolve_code(self, entry) -> str | None:
        # Primero la CARPETA (igual que resolve_machine_asset) -- la
        # jerarquía antigua "MANUAL DE INSTRUCCIONES/{CODIGO}/..."
        # todavía conserva la máquina de origen en la ruta. Solo si
        # la carpeta no aporta nada (caso "MANUALES DE USO", plana,
        # sin subcarpetas por máquina) se cae al nombre de archivo --
        # bug real S041: mirar solo el nombre hacía que archivos como
        # "PARTE14.pdf"/"Binder1.pdf" (que SÍ tienen la máquina en la
        # carpeta) se quedaran sin código, y una discrepancia real de
        # marca/modelo (Binder1.pdf, A-44) no llegaba a compararse.
        for segment in entry.parent_path.split("/"):
            code = self._extract_candidate_code(segment)
            if code:
                return code
        return self._extract_candidate_code(entry.name)

    def _audit_one(self, client, entry) -> dict | None:
        machine_code = self._resolve_code(entry)
        asset = (
            MachineAsset.objects.filter(code__iexact=machine_code).first()
            if machine_code else None
        )
        db_model = asset.brand_model if asset else None

        try:
            content_bytes = download_bytes(entry.bucket, entry.blob_name)
        except Exception as exc:
            self.stdout.write(self.style.ERROR(
                "  Fallo descargando de GCS: %s" % exc
            ))
            return None

        excerpt = _extract_pdf_edges(
            content_bytes,
            first_pages=_MANUAL_EXCERPT_PAGES,
            last_pages=0,
        )
        if excerpt is None:
            self.stdout.write(self.style.WARNING(
                "  No se pudieron extraer páginas (PDF corrupto o no "
                "soportado) -- omitido."
            ))
            return None

        try:
            response = _generate_content_with_retry(
                client,
                model=DEFAULT_MODEL,
                contents=[
                    Part.from_bytes(
                        data=excerpt, mime_type="application/pdf",
                    ),
                    _MANUAL_MODEL_PROMPT,
                ],
                config=GenerateContentConfig(
                    http_options=HttpOptions(timeout=90_000),
                    response_mime_type="application/json",
                    response_schema=_MANUAL_MODEL_SCHEMA,
                    temperature=0.0,
                ),
            )
            result = json.loads(response.text.strip())
        except Exception as exc:
            self.stdout.write(self.style.ERROR("  Fallo Gemini: %s" % exc))
            return None

        real_model = (result.get("brand_model") or "").strip()
        # Comparación deliberadamente basta -- solo la primera palabra
        # (la marca), mismo criterio ya usado en check_machine_mismatch
        # (H29 3.25) para no generar falsos positivos por variantes de
        # modelo dentro de la misma marca.
        match = bool(
            real_model and db_model
            and real_model.split()[0].upper() == db_model.split()[0].upper()
        )

        return {
            "folder": entry.parent_path,
            "name": entry.name,
            "size_mb": round((entry.size_bytes or 0) / (1024 * 1024), 1),
            "code": machine_code,
            "db_model": db_model,
            "manual_model": real_model,
            "confidence": result.get("confidence", "?"),
            "reasoning": result.get("reasoning", ""),
            "match": match,
        }

    def _print_summary(self, rows):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== RESUMEN ==="))
        unresolved_code = [r for r in rows if not r["code"]]
        no_asset = [r for r in rows if r["code"] and not r["db_model"]]
        mismatches = [
            r for r in rows
            if r["code"] and r["db_model"] and not r["match"]
        ]
        self.stdout.write("Total procesados con éxito: %d" % len(rows))
        self.stdout.write(
            "Sin código de máquina resoluble por nombre de archivo: %d"
            % len(unresolved_code)
        )
        self.stdout.write(
            "Código resuelto pero sin MachineAsset real en BD: %d"
            % len(no_asset)
        )
        self.stdout.write(
            "brand_model en BD NO coincide con el del manual: %d"
            % len(mismatches)
        )
        if mismatches:
            self.stdout.write("\nDiscrepancias a revisar:")
            for r in mismatches:
                self.stdout.write(
                    "  %s -- BD=%r vs manual=%r (%s)" % (
                        r["name"], r["db_model"], r["manual_model"],
                        r["confidence"],
                    )
                )

        self.stdout.write(
            "\nAgrupado por modelo real detectado en el manual "
            "(candidatos a modelo canónico único):"
        )
        by_model = {}
        for row in rows:
            key = row["manual_model"] or "(sin identificar)"
            by_model.setdefault(key, []).append(row)
        ranked = sorted(
            by_model.items(), key=lambda kv: (-len(kv[1]), kv[0]),
        )
        for model, group in ranked:
            self.stdout.write("\n  %3d archivo(s) -- %s" % (
                len(group), model,
            ))
            for row in group:
                self.stdout.write(
                    "       %s (%s MB, código=%s)" % (
                        row["name"], row["size_mb"], row["code"] or "?",
                    )
                )
