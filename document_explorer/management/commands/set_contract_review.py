# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/set_contract_review.py
"""
H30 (S122). Apply the visual review of employment contracts: retype
contract extensions to PRORROGA_CONTRATO with their start/end dates,
and date real contracts.

---

H30 (S122). Aplica la revisión visual de contratos: retipa las
prórrogas a `PRORROGA_CONTRATO` con su inicio (`issue_date`) y su
término (`expiry_date`), y fecha los contratos reales (`issue_date`).
Origen: los 33 contratos sin fecha de trabajadores activos, revisados
uno a uno sobre la imagen real (relevo gcs_image) -- 31 eran
comunicaciones de prórroga, no contratos. Decisión de Miguel Ángel:
prórroga como subtipo de contrato, dentro de su periodo y sin contar
como contrato del alta.

Genérico, sin ids en el código: las fechas las decide quien revisa la
imagen y se pasan por argumento:
  --prorrogas id:INICIO:TERMINO[,id:INICIO:TERMINO...]
  --contratos id:FECHA[,id:FECHA...]
(fechas AAAA-MM-DD). Solo actúa sobre documentos vivos de personal que
HOY sean CONTRATO; cualquier otro id aborta sin escribir nada. Realinea
el nombre canónico (solo `name` en BD, nunca GCS) con
`apply_personal_canonical_rename()`. Log con el valor anterior de cada
campo.

DRY-RUN POR DEFECTO; `--apply` escribe. Log propio con flush por línea
(`--log-file`). Idempotente: lo que ya está como se pide no se toca.
"""
from datetime import date, datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from document_explorer.classification_service import (
    apply_personal_canonical_rename,
)
from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog,
)

CONTRACT_CODE = "CONTRATO"
EXTENSION_CODE = "PRORROGA_CONTRATO"


def _parse_items(raw, fields):
    """
    "id:F1[:F2],..." -> {id: (date, ...)}; CommandError if malformed.

    ---

    Lee "id:AAAA-MM-DD[:AAAA-MM-DD],..." con `fields` fechas por id.
    """
    result = {}
    for item in (raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.split(":")
        if len(parts) != fields + 1:
            raise CommandError("Elemento no válido: %r" % item)
        try:
            pk = int(parts[0])
            dates = tuple(date.fromisoformat(p.strip()) for p in parts[1:])
        except ValueError as exc:
            raise CommandError("Elemento no válido: %r" % item) from exc
        if pk in result:
            raise CommandError("Id repetido: %d" % pk)
        result[pk] = dates
    return result


class Command(BaseCommand):
    """
    Apply a reviewed set of contract/extension dates.

    ---

    Aplica fechas y tipos revisados de contratos y prórrogas.
    """

    help = (
        "Retipa prórrogas a PRORROGA_CONTRATO con inicio/término y fecha "
        "contratos, según revisión visual (H30, S122)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--prorrogas", default="")
        parser.add_argument("--contratos", default="")
        parser.add_argument("--log-file", required=True)
        parser.add_argument("--apply", action="store_true")

    def _log(self, message):
        """
        Print and append one line to the log file, flushed.

        ---

        Escribe una línea en pantalla y en el log, con flush.
        """
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        extensions = _parse_items(options["prorrogas"], 2)
        contracts = _parse_items(options["contratos"], 1)
        overlap = set(extensions) & set(contracts)
        if overlap:
            raise CommandError(
                "Ids en las dos listas: %s" % sorted(overlap),
            )
        if not extensions and not contracts:
            raise CommandError(
                "Nada que hacer: --prorrogas y --contratos vacíos.",
            )
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._log_handle = handle
            self._run(extensions, contracts, options["apply"])

    def _run(self, extensions, contracts, apply_changes):
        wanted = set(extensions) | set(contracts)
        self._log(
            "REVISIÓN DE CONTRATOS (%s) -- %d prórroga(s), %d contrato(s)"
            % ("APLICAR" if apply_changes else "DRY-RUN, nada se escribe",
               len(extensions), len(contracts))
        )
        extension_type = DocumentTypeCatalog.objects.filter(
            code=EXTENSION_CODE,
        ).first()
        if extension_type is None:
            self._log("ABORTADO: no existe el tipo %s." % EXTENSION_CODE)
            return
        entries = {
            entry.pk: entry
            for entry in DocumentIndexEntry.objects.filter(
                pk__in=wanted, deleted_at__isnull=True,
                purged_at__isnull=True,
                domain_content_type__model="personidentity",
            ).select_related("document_type")
        }
        missing = sorted(wanted - set(entries))
        if missing:
            self._log(
                "ABORTADO: ids inexistentes, borrados o no de personal: %s"
                % missing
            )
            return
        wrong_type = sorted(
            pk for pk, entry in entries.items()
            if not entry.document_type
            or entry.document_type.code not in (CONTRACT_CODE, EXTENSION_CODE)
        )
        if wrong_type:
            self._log(
                "ABORTADO: ids que no son CONTRATO ni PRORROGA_CONTRATO: %s"
                % wrong_type
            )
            return

        reserved = set()
        stats = {"changed": 0, "unchanged": 0, "renamed": 0}
        for pk in sorted(wanted):
            entry = entries[pk]
            if pk in extensions:
                new_type = extension_type
                new_issue, new_expiry = extensions[pk]
            else:
                new_type = entry.document_type
                (new_issue,) = contracts[pk]
                new_expiry = entry.expiry_date
            before = (entry.document_type.code, entry.issue_date,
                      entry.expiry_date)
            after = (new_type.code, new_issue, new_expiry)
            if before == after:
                stats["unchanged"] += 1
                self._log("SIN CAMBIO id=%d | %s" % (pk, entry.name))
                continue
            old_name = entry.name
            entry.document_type = new_type
            entry.issue_date = new_issue
            entry.expiry_date = new_expiry
            with transaction.atomic():
                if apply_changes:
                    entry.save(update_fields=[
                        "document_type", "issue_date", "expiry_date",
                    ])
                result = apply_personal_canonical_rename(
                    entry, apply_changes=apply_changes,
                    reserved_names=reserved,
                )
            stats["changed"] += 1
            self._log(
                "id=%d tipo %s -> %s | inicio %s -> %s | término %s -> %s"
                % (pk, before[0], after[0], before[1] or "sin fecha",
                   after[1], before[2] or "sin fecha",
                   after[2] or "sin fecha")
            )
            new_name = result.get("new_name")
            if new_name:
                stats["renamed"] += int(new_name != old_name)
                self._log("    nombre: %s -> %s" % (old_name, new_name))
            else:
                self._log(
                    "    nombre sin realinear (%s): %s"
                    % (result.get("reason"), old_name)
                )
        self._log(
            "=== RESUMEN (%s) === cambiados: %d | ya correctos: %d | "
            "nombres realineados: %d"
            % ("APLICADO" if apply_changes else "DRY-RUN", stats["changed"],
               stats["unchanged"], stats["renamed"])
        )
