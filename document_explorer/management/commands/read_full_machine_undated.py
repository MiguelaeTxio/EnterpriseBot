# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/read_full_machine_undated.py
"""
H30 (S119), roadmap item 1 -- real closure: read ENTIRELY every
expiring document of an active machine that is still undated.
---
H30 (S119), punto 1 de la hoja de ruta -- cierre real. Miguel Ángel:
"hasta que no quede nada pendiente no está terminado el punto 1". Los
que siguen sin ninguna fecha tras las reglas sobre `ocr_text` se leen
ENTEROS, no solo las 2 primeras páginas que se cachearon:

- PDF: texto incrustado de TODAS las páginas y, para las que no lo
  tienen, Cloud Vision (el lector aprobado de la hoja de ruta; nunca
  Gemini) de dos en dos páginas desde la 3 hasta `--max-pages`.
- DOCX y MSG: los extractores ya probados del proyecto
  (`date_verification_service.docx_to_text` con tablas incluidas,
  `msg_to_text`), que estos documentos nunca pasaron.
- EML: asunto y cuerpo con la librería estándar `email`.
- La fecha de ENVÍO de un correo nunca fecha el documento (criterio
  S92 de Miguel Ángel: es la fecha de reenvío); solo se anota en el
  log para decidir a mano.

Después aplica las MISMAS reglas que `date_machine_documents_free`
(reglas por tipo S119, nombre ORIGINAL de `blob_name`, texto), sobre el
texto completo. Con --apply guarda el texto completo en `ocr_text` y la
fecha hallada. Los que sigan sin fecha van al final del log con TODAS
las fechas que aparecen en su texto completo y su contexto, para
resolverlos uno a uno.

DRY-RUN por defecto. Log propio (pantalla y archivo a la vez) con
heartbeat y ETA.
"""
import email
import email.policy
import re
import time
from datetime import datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.cloud_vision_service import (
    cloud_vision_text,
    pdf_embedded_text,
)
from document_explorer.date_verification_service import (
    docx_to_text,
    msg_to_text,
)
from document_explorer.management.commands.date_machine_documents_free import (  # noqa: E501
    Command as DatingCommand,
    original_name,
)
from document_explorer.models import DocumentIndexEntry
from fleet.models import MachineAsset
from spare_parts.gcs_service import download_bytes

BUCKET = "cgs_grupo_alvarez"
DATE_TOKEN_RE = re.compile(
    r"(?<!\d)\d{1,2}[-./]\d{1,2}[-./](?:\d{4}|\d{2})(?!\d)"
    r"|\b\d{1,2}\s+de\s+[a-záéíóú]+\s+de\s+\d{4}\b",
    re.IGNORECASE,
)


def _pdf_page_count(data):
    import fitz

    with fitz.open(stream=data, filetype="pdf") as doc:
        return doc.page_count


def _full_pdf_text(data, filename, max_pages, notes):
    """
    All embedded text, plus Cloud Vision for pages 3..max_pages.
    ---
    Todo el texto incrustado y, página a página de dos en dos desde la 3,
    Cloud Vision donde el incrustado no aporta nada.
    """
    pages = _pdf_page_count(data)
    notes.append("%d paginas" % pages)
    parts = [pdf_embedded_text(data, page_range=(0, pages))]
    start = 3
    while start <= min(pages, max_pages):
        end = min(start + 1, pages, max_pages)
        try:
            parts.append(cloud_vision_text(data, filename, (start, end)))
        except Exception as exc:  # una pagina que falla no para el resto
            notes.append("GCV %d-%d fallo: %s" % (start, end, exc))
        start = end + 1
    if pages > max_pages:
        notes.append("leidas hasta la %d" % max_pages)
    return "\n".join(part for part in parts if part)


def _eml_text(data, notes):
    message = email.message_from_bytes(data, policy=email.policy.default)
    if message["date"]:
        notes.append("fecha de envio del correo: %s" % message["date"])
    parts = [str(message["subject"] or "")]
    body = message.get_body(preferencelist=("plain", "html"))
    if body is not None:
        parts.append(body.get_content())
    return "\n".join(part for part in parts if part)


def full_text(entry, max_pages, notes):
    """
    Read the whole document; return its text ('' if unreadable).
    ---
    Lee el documento entero según su extensión; '' si no se puede.
    """
    filename = original_name(entry)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename \
        else ""
    data = download_bytes(entry.bucket, entry.blob_name)
    # Sin extensión en el nombre (caso real: "SEGURO A58"): se mira el
    # contenido para saber qué es.
    if extension not in ("pdf", "docx", "msg", "eml", "jpg", "jpeg", "png"):
        if data[:5] == b"%PDF-":
            extension = "pdf"
            notes.append("sin extension, contenido PDF")
        elif data[:3] == b"\xff\xd8\xff":
            extension = "jpg"
            notes.append("sin extension, contenido JPG")
    if extension == "pdf":
        return _full_pdf_text(data, filename, max_pages, notes)
    if extension == "docx":
        return docx_to_text(data)
    if extension == "msg":
        return msg_to_text(data)
    if extension == "eml":
        return _eml_text(data, notes)
    if extension in ("jpg", "jpeg", "png"):
        return cloud_vision_text(data, filename)
    notes.append("extension .%s sin extractor" % (extension or "?"))
    return ""


class Command(BaseCommand):
    help = (
        "H30 (S119) -- punto 1: lee entero cada caducable de maquina "
        "activa sin fecha y lo fecha. Dry-run por defecto."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--max-pages", type=int, default=20)
        parser.add_argument(
            "--log-file", required=True,
            help="Log propio (pantalla y archivo a la vez, 0bis).",
        )

    def _log(self, message):
        self._log_plain(
            "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message),
        )

    def _log_plain(self, message):
        print(message, flush=True)
        self._log_handle.write(message + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options["apply"], options["max_pages"])
        finally:
            self._log_handle.close()

    def _run(self, apply_changes, max_pages):
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        active_ids = list(
            MachineAsset.objects.filter(is_active=True)
            .values_list("id", flat=True)
        )
        entries = list(DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            domain_content_type=machine_ct, domain_object_id__in=active_ids,
            document_type__tracks_expiry=True,
            expiry_date__isnull=True, issue_date__isnull=True,
        ).select_related("document_type").order_by(
            "document_type__code", "id",
        ))
        total = len(entries)
        self._log(
            "PUNTO 1 (lectura completa) -- MODO: %s -- %d documentos "
            "sin ninguna fecha" % (
                "APLICAR (escribe)" if apply_changes
                else "DRY-RUN (no escribe nada)", total,
            )
        )
        dating = DatingCommand()
        dated = []
        pending = []
        start_time = datetime.now()
        last_beat = time.monotonic()
        for index, entry in enumerate(entries, start=1):
            notes = []
            try:
                text = full_text(entry, max_pages, notes)
            except Exception as exc:
                text = ""
                notes.append("ERROR leyendo: %s" % exc)
            combined = "\n".join(
                part for part in (entry.ocr_text, text) if part
            )
            entry.ocr_text = combined
            updates, source = dating._decide_by_rules(entry)
            if not updates:
                field, value, source = dating._decide(entry)
                if field:
                    updates = {"%s_date" % field: value}
            if not updates:
                updates, source = dating._decide_by_rules(
                    entry, fallback=True,
                )
            if updates:
                dated.append("id=%d %s | %s -> %s (%s)" % (
                    entry.id, entry.document_type.code, original_name(entry),
                    ", ".join("%s=%s" % kv for kv in sorted(updates.items())),
                    source,
                ))
            else:
                tokens = []
                for match in DATE_TOKEN_RE.finditer(combined):
                    context = combined[max(0, match.start() - 60):
                                       match.end() + 40]
                    tokens.append(" ".join(context.split()))
                pending.append((entry, notes, tokens, len(combined)))
            if apply_changes:
                fields = ["ocr_text"]
                for key, value in (updates or {}).items():
                    setattr(entry, key, value)
                    fields.append(key)
                entry.save(update_fields=fields)
            if time.monotonic() - last_beat >= 30 or index == total \
                    or index % 10 == 0:
                last_beat = time.monotonic()
                elapsed = (datetime.now() - start_time).total_seconds()
                eta_seg = (elapsed / index) * (total - index)
                self._log(
                    "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. "
                    "%s) -- fechados=%d, sin_fecha=%d" % (
                        index, total, index * 100 // total if total else 100,
                        int(eta_seg // 60), int(eta_seg % 60),
                        (datetime.now() + timedelta(seconds=eta_seg)
                         ).strftime("%H:%M:%S"),
                        len(dated), len(pending),
                    )
                )
        self._log_plain("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self._log_plain("    fechados: %d" % len(dated))
        self._log_plain("    siguen sin fecha: %d" % len(pending))
        self._log_plain("--- FECHADOS ---")
        for line in dated:
            self._log_plain("    %s" % line)
        self._log_plain("--- SIGUEN SIN FECHA: TODAS LAS FECHAS DEL TEXTO ---")
        for entry, notes, tokens, length in pending:
            self._log_plain("  id=%d %s | %s | %d caracteres | %s" % (
                entry.id, entry.document_type.code, original_name(entry),
                length, "; ".join(notes) or "-",
            ))
            for token in tokens[:25] or ["(ninguna fecha en todo el texto)"]:
                self._log_plain("      %s" % token)
            if not tokens:
                self._log_plain("      arranque: %s" % " ".join(
                    (entry.ocr_text or "")[:400].split()) or "(vacio)")
