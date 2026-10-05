# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/ocr_full_text.py
"""
H30 (S127). Full OCR of a person's files into DocumentIndexEntry.ocr_text.

---

H30 (S127). OCR COMPLETO, página a página, de todos los archivos de las
personas auditadas, guardado en `ocr_text` con la marca
`FULL_OCR_MARKER` y una cabecera por página. Texto incrustado del PDF
si lo hay (gratis), Cloud Vision si no (Miguel Ángel aprobó GCV para la
auditoría: rápido, sin la saturación de Gemini, y el texto queda para
siempre). Lo usa después `audit_missing_documents` en vez de mandar
imágenes a Gemini.

- `--person PK` (repetible) o `--audit` (todas las personas con algún
  "Falta" de DNI/NIE, permiso o contrato).
- Archivos: `document_audit_service.candidate_files` (vinculados, su
  carpeta, carpetas antiguas con su nombre y papelera).
- Una copia exacta (misma huella y tamaño) de un archivo ya con OCR
  completo hereda su texto sin llamar a Cloud Vision.
- Ya con OCR completo: se salta. Idempotente y reanudable.

Verbosidad (com-standards 0bis): `--log-file` obligatorio, pantalla y
archivo a la vez con flush, una línea por archivo, latido cada 20 con
ETA y hora de fin.
"""
import time
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from document_explorer import document_notice_service as notices
from document_explorer.classification_service import (
    _LIBREOFFICE_CONVERTIBLE_EXTENSIONS, _convert_to_pdf, _document_text,
)
from document_explorer.cloud_vision_service import (
    FULL_OCR_MARKER, format_full_text, full_text_pages,
)
from document_explorer.document_audit_service import (
    _spreadsheet_text, candidate_files, content_key,
)
from document_explorer.models import DocumentIndexEntry, PersonIdentity
from spare_parts.gcs_service import download_bytes

_TEXT_ONLY = {"docx", "html", "htm", "xml"}


class Command(BaseCommand):
    help = (
        "S127: OCR completo (texto incrustado + Cloud Vision) de los "
        "archivos de las personas auditadas, guardado en ocr_text."
    )

    def add_arguments(self, parser):
        parser.add_argument("--person", type=int, action="append")
        parser.add_argument("--audit", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _say(self, text):
        self.stdout.write(text)
        self.stdout.flush()
        self._log.write(text + "\n")
        self._log.flush()

    def _people(self, options):
        if options["person"]:
            return list(PersonIdentity.objects.filter(
                pk__in=options["person"]))
        if not options["audit"]:
            return []
        pending, _scheduled, _calendar = notices.compute_notices(
            notices.DOMAIN_PERSONAL,
        )
        pks = set()
        for notice in pending:
            label = notice.document_label or ""
            if notice.kind == notices.KIND_MISSING and (
                label in ("DNI", "DNI o NIE") or label.startswith("NIE")
                or label.startswith("Permiso de conducción")
                or label.startswith("Contrato laboral")
            ):
                pks.add(int(notice.notice_key.split("|")[1]))
        return list(PersonIdentity.objects.filter(pk__in=pks))

    def _text_of(self, entry):
        data = download_bytes(entry.bucket, entry.blob_name)
        extension = (
            entry.name.rsplit(".", 1)[-1].lower() if "." in entry.name else ""
        )
        if extension in _TEXT_ONLY:
            return [_document_text(data, extension)], 0
        if extension in ("xlsx", "xlsm"):
            return [_spreadsheet_text(data)], 0
        if extension in _LIBREOFFICE_CONVERTIBLE_EXTENSIONS:
            # S127: los .doc antiguos (Núñez, EnterpriseBot_026) quedaban
            # "sin OCR": a PDF con LibreOffice y el mismo OCR completo.
            converted = _convert_to_pdf(data, extension)
            if converted:
                return full_text_pages("convertido.pdf", converted)
            return [], 0
        return full_text_pages(entry.name, data)

    def handle(self, *args, **options):
        self._log = open(options["log_file"], "a", encoding="utf-8")
        started = time.monotonic()
        people = self._people(options)
        self._say("# [OCR] %d persona(s). Reuniendo archivos..." % len(people))
        files = []
        seen = set()
        for person in people:
            for entry in candidate_files(person):
                if entry.pk not in seen:
                    seen.add(entry.pk)
                    files.append((person, entry))
        total = len(files)
        self._say("# [OCR] %d archivo(s) distintos." % total)
        done_text = {}
        paid_total = skipped = errors = 0
        for position, (person, entry) in enumerate(files, 1):
            close_old_connections()
            key = content_key(entry)
            status = ""
            try:
                if (entry.ocr_text or "").startswith(FULL_OCR_MARKER):
                    skipped += 1
                    status = "ya tenía OCR completo"
                    if key:
                        done_text.setdefault(key, entry.ocr_text)
                elif key and key in done_text:
                    DocumentIndexEntry.objects.filter(pk=entry.pk).update(
                        ocr_text=done_text[key])
                    status = "copia idéntica, texto heredado"
                else:
                    pages, paid = self._text_of(entry)
                    if not pages:
                        status = "formato sin OCR (%s)" % entry.name.rsplit(
                            ".", 1)[-1]
                    else:
                        text = format_full_text(pages)
                        DocumentIndexEntry.objects.filter(
                            pk=entry.pk).update(ocr_text=text)
                        if key:
                            done_text[key] = text
                        paid_total += paid
                        status = "%d pág., %d por Cloud Vision, %d caracteres" % (
                            len(pages), paid, len(text))
            except Exception as exc:
                errors += 1
                status = "ERROR %s" % exc
            self._say("   [%d/%d] %s %s | pk=%s %s -> %s" % (
                position, total, person.first_surname, person.given_name,
                entry.pk, entry.name, status))
            if position % 20 == 0:
                elapsed = time.monotonic() - started
                left = elapsed / position * (total - position)
                self._say(
                    "   ... avance %d/%d (%d%%) -- %d pág. por Cloud Vision "
                    "-- quedan ~%d min, fin estimado a las %s" % (
                        position, total, 100 * position // max(total, 1),
                        paid_total, left // 60,
                        (datetime.now() + timedelta(seconds=left)).strftime(
                            "%H:%M"),
                    )
                )
        self._say(
            "# [OCR] Fin. %d archivo(s); %d ya tenían OCR completo; %d "
            "página(s) leídas por Cloud Vision; %d error(es)." % (
                total, skipped, paid_total, errors)
        )
