# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/check_file_ownership.py
"""
H30 (S127). Files sitting in one person's record that belong to another.

---

H30 (S127). Archivos que están en la ficha de una persona y son de
OTRA, con cotejo exacto de identidad (`ownership_service`, sin Gemini).

Regla de Miguel Ángel (S127): "Si son de persona y es activa a su
persona si no, a empresa y si no es de empresa a la papelera."

Fases (cada una con su línea por archivo y avance con hora de fin):
1. OCR completo (--ocr): los archivos de las fichas que aún no lo
   tienen se leen con texto incrustado / Cloud Vision y se guarda en
   `ocr_text` (una copia idéntica hereda el texto sin volver a leerse).
2. Quién aparece en cada archivo, página a página (número de documento
   o nombre completo).
3. Firmantes: quien aparece en archivos de muchos dueños distintos.
4. Veredicto de cada archivo: del dueño, de otra persona, de varias,
   sin pruebas, sin OCR.

--apply solo mueve los "de otra persona" probados por NÚMERO de
documento; los probados solo por nombre salen como PROBABLE para
revisarlos a mano. Se revisan las fichas de los activos y, de las de
los no activos, solo lo que resulte ser de un activo. Sin --apply no
mueve nada.
"""
import time
import zlib
from collections import defaultdict
from datetime import datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from document_explorer import ownership_service as own
from document_explorer.classification_service import (
    _apply_company_classification, file_entry_manually, trash_dossier_entry,
)
from document_explorer.cloud_vision_service import (
    FULL_OCR_MARKER, format_full_text,
)
from document_explorer.document_audit_service import content_key
from document_explorer.models import DocumentIndexEntry, PersonIdentity


class Command(BaseCommand):
    help = (
        "S127: archivos de una ficha que son de otra persona (cotejo "
        "exacto, sin Gemini). Sin --apply solo informa."
    )

    def add_arguments(self, parser):
        parser.add_argument("--log-file", required=True)
        parser.add_argument("--ocr", action="store_true")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--shard", type=int, default=0,
            help="Con --ocr y --shards: esta consola hace solo la parte N "
                 "(desde 1) del OCR y termina, sin veredictos.",
        )
        parser.add_argument("--shards", type=int, default=0)
        parser.add_argument(
            "--exclude", type=int, action="append", default=[],
            help="pk de archivo que --apply no toca (pendiente de decidir).",
        )

    def _say(self, text, stamp=True):
        line = ("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), text)
                if stamp else text)
        self.stdout.write(line)
        self.stdout.flush()
        self._log.write(line + "\n")
        self._log.flush()

    def _progress(self, label, done, total, started, extra=""):
        elapsed = time.monotonic() - started
        left = elapsed / done * (total - done) if done else 0
        self._say("%s: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s)%s" % (
            label, done, total, 100 * done // max(total, 1),
            left // 60, left % 60,
            (datetime.now() + timedelta(seconds=left)).strftime("%H:%M:%S"),
            " -- %s" % extra if extra else ""))

    def handle(self, *args, **options):
        self._log = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options)
        finally:
            self._log.close()

    def _files(self):
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        return list(DocumentIndexEntry.objects.filter(
            domain_content_type=person_ct,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).select_related("document_type").order_by("domain_object_id", "id"))

    def _ocr(self, files):
        from document_explorer.management.commands.ocr_full_text import (
            Command as OcrCommand,
        )

        reader = OcrCommand()
        pending = [
            entry for entry in files
            if not (entry.ocr_text or "").startswith(FULL_OCR_MARKER)
        ]
        known = {
            content_key(entry): entry.ocr_text for entry in files
            if content_key(entry)
            and (entry.ocr_text or "").startswith(FULL_OCR_MARKER)
        }
        self._say("# Fase 1 -- OCR completo de %d archivo(s) que no lo "
                  "tenían." % len(pending))
        started = time.monotonic()
        paid_total = errors = 0
        for position, entry in enumerate(pending, 1):
            close_old_connections()
            key = content_key(entry)
            try:
                if key and key in known:
                    entry.ocr_text = known[key]
                    status = "copia idéntica, texto heredado"
                else:
                    pages, paid = reader._text_of(entry)
                    if not pages:
                        status = "formato sin OCR"
                        entry.ocr_text = entry.ocr_text or ""
                    else:
                        entry.ocr_text = format_full_text(pages)
                        if key:
                            known[key] = entry.ocr_text
                        paid_total += paid
                        status = "%d pág., %d por Cloud Vision" % (
                            len(pages), paid)
                DocumentIndexEntry.objects.filter(pk=entry.pk).update(
                    ocr_text=entry.ocr_text)
            except Exception as exc:
                errors += 1
                status = "ERROR %s" % exc
            self._say("   OCR %d/%d pk=%s %s -> %s" % (
                position, len(pending), entry.pk, entry.name, status))
            if position % 25 == 0:
                self._progress("OCR", position, len(pending), started,
                               "%d pág. por Cloud Vision, %d error(es)"
                               % (paid_total, errors))
        self._say("# Fase 1 terminada: %d página(s) por Cloud Vision, %d "
                  "error(es)." % (paid_total, errors))

    def _run(self, options):
        apply = options["apply"]
        self._say("# [S127] Archivos de otra persona -- %s" % (
            "APLICANDO" if apply else "MODO PRUEBA (sin --apply)"))
        people = own.roster()
        by_pk = {person.pk: person for person in people}
        files = self._files()
        self._say("# %d persona(s) en el registro, %d archivo(s) en "
                  "fichas." % (len(people), len(files)))
        if options["ocr"]:
            shards = options["shards"]
            if shards:
                shard = options["shard"]
                # Reparto por contenido: las copias idénticas caen en la
                # misma consola y se leen una sola vez.
                files = [
                    entry for entry in files
                    if zlib.crc32(
                        (content_key(entry) or str(entry.pk)).encode()
                    ) % shards == shard - 1
                ]
                self._say("# Parte %d de %d: %d archivo(s)." % (
                    shard, shards, len(files)))
                self._ocr(files)
                self._say("# Parte %d de %d terminada. Los veredictos se "
                          "sacan con una pasada sin --shards cuando "
                          "terminen todas." % (shard, shards))
                return
            self._ocr(files)

        self._say("# Fase 2 -- quién aparece en cada archivo.")
        started = time.monotonic()
        found_by_file = {}
        appearances = defaultdict(set)
        for position, entry in enumerate(files, 1):
            found = own.people_in(entry, people)
            found_by_file[entry.pk] = found
            for pk in found or ():
                appearances[pk].add(entry.domain_object_id)
            if position % 250 == 0:
                self._progress("Cotejo", position, len(files), started)
        signers = own.signatories(appearances)
        self._say("# Fase 3 -- firmantes (salen en archivos de %d o más "
                  "dueños): %s" % (
                      own.SIGNATORY_MIN_OWNERS,
                      "; ".join(by_pk[pk].label() for pk in sorted(signers))
                      or "ninguno"))

        self._say("# Fase 4 -- veredictos.")
        counts = defaultdict(int)
        moved = 0
        for entry in files:
            owner = by_pk.get(entry.domain_object_id)
            if owner is None:
                continue
            result, other, evidence = own.verdict(
                entry, owner, found_by_file[entry.pk], by_pk, signers,
            )
            if result == own.OTHER and not owner.active and not other.active:
                continue
            if not owner.active and result != own.OTHER:
                continue
            counts[result] += 1
            if result not in (own.OTHER, own.SEVERAL):
                continue
            code = entry.document_type.code if entry.document_type else ""
            head = "pk=%s [%s] %s/%s | ficha de %s" % (
                entry.pk, code or "sin tipo", entry.parent_path, entry.name,
                owner.label())
            if result == own.SEVERAL:
                self._say("   VARIAS PERSONAS %s | %s" % (head, evidence),
                          stamp=False)
                continue
            proven = "por nº" in evidence
            action = self._plan(entry, other)
            self._say("   %s %s | es de %s (%s) -> %s" % (
                "DE OTRA PERSONA" if proven else "PROBABLE (solo nombre)",
                head, other.label(), evidence, action), stamp=False)
            if entry.pk in options["exclude"]:
                self._say("      -> apartado (--exclude), no se toca",
                          stamp=False)
                continue
            if apply and proven and action and not action.startswith("NO"):
                moved += self._apply(entry, other, code)
        self._say("# Resumen: %s." % ", ".join(
            "%s %d" % (key, value) for key, value in sorted(counts.items())),
            stamp=False)
        if apply:
            self._say("# Movidos: %d." % moved, stamp=False)

    @staticmethod
    def _plan(entry, other):
        document_type = entry.document_type
        if other.active:
            if document_type is None:
                return "NO: sin tipo (revisar a mano)"
            return "a la ficha de %s" % other.identity.given_name
        if document_type is not None and document_type.domain == "COMPANY":
            return "a DOC. EMPRESA"
        return "a la papelera (persona no activa)"

    def _apply(self, entry, other, code):
        date = entry.issue_date or entry.expiry_date
        hint = date.isoformat() if date else ""
        if other.active:
            outcome = file_entry_manually(
                entry, other.identity, code, date_hint=hint,
                apply_changes=True,
            )
            ok = not outcome["reason"]
        elif entry.document_type and entry.document_type.domain == "COMPANY":
            ok = bool(_apply_company_classification(
                entry, {"document_type_code": code, "date_hint": hint},
            ).get("classified"))
        else:
            ok = trash_dossier_entry(entry)
        self._say("      -> %s" % ("[OK]" if ok else "[NO SE PUDO]"),
                  stamp=False)
        return 1 if ok else 0
