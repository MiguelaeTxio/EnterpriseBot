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
  --modificaciones id:EFECTOS[,...]   (S122, segunda tanda)
  --altas id:FECHA[,...]              (S122, segunda tanda)
  --renombrar id[,id...]              (S122, segunda tanda)
(fechas AAAA-MM-DD). Prórrogas, contratos y modificaciones solo sobre
documentos vivos de personal que HOY sean CONTRATO o uno de sus
subtipos; altas solo sobre documentos que HOY sean ALTA; --renombrar
solo realinea el nombre canónico de documentos cuya fecha ya es
correcta (contratos cuyo nombre llevaba la fecha de nacimiento o la de
relleno 01/01/2021). Cualquier otro id aborta sin escribir nada. Realinea
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
MODIFICATION_CODE = "MODIFICACION_CONTRATO"
ALTA_CODE = "ALTA"
CONTRACT_FAMILY_CODES = (CONTRACT_CODE, EXTENSION_CODE, MODIFICATION_CODE)


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
        parser.add_argument("--modificaciones", default="")
        parser.add_argument("--altas", default="")
        parser.add_argument("--renombrar", default="")
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
        modifications = _parse_items(options["modificaciones"], 1)
        altas = _parse_items(options["altas"], 1)
        try:
            renames = {
                int(item) for item in options["renombrar"].split(",")
                if item.strip()
            }
        except ValueError as exc:
            raise CommandError("--renombrar: ids no válidos.") from exc
        lists = [
            set(extensions), set(contracts), set(modifications),
            set(altas), renames,
        ]
        seen = set()
        for ids in lists:
            if seen & ids:
                raise CommandError(
                    "Ids en más de una lista: %s" % sorted(seen & ids),
                )
            seen |= ids
        if not seen:
            raise CommandError("Nada que hacer: todas las listas vacías.")
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._log_handle = handle
            self._run(
                extensions, contracts, modifications, altas, renames,
                options["apply"],
            )

    def _run(self, extensions, contracts, modifications, altas, renames,
             apply_changes):
        wanted = (
            set(extensions) | set(contracts) | set(modifications)
            | set(altas) | renames
        )
        self._log(
            "REVISIÓN DE CONTRATOS (%s) -- %d prórroga(s), %d contrato(s), "
            "%d modificación(es), %d alta(s), %d solo nombre"
            % ("APLICAR" if apply_changes else "DRY-RUN, nada se escribe",
               len(extensions), len(contracts), len(modifications),
               len(altas), len(renames))
        )
        types = {
            t.code: t for t in DocumentTypeCatalog.objects.filter(
                code__in=(EXTENSION_CODE, MODIFICATION_CODE),
            )
        }
        for code in (EXTENSION_CODE, MODIFICATION_CODE):
            if code not in types:
                self._log("ABORTADO: no existe el tipo %s." % code)
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
        def _code(pk):
            entry = entries[pk]
            return entry.document_type.code if entry.document_type else None

        wrong_type = sorted(
            pk for pk in entries
            if (pk in altas and _code(pk) != ALTA_CODE)
            or (pk not in altas and _code(pk) not in CONTRACT_FAMILY_CODES)
        )
        if wrong_type:
            self._log(
                "ABORTADO: ids de un tipo que no corresponde a su lista "
                "(altas: ALTA; resto: CONTRATO o sus subtipos): %s"
                % wrong_type
            )
            return

        reserved = set()
        stats = {"changed": 0, "unchanged": 0, "renamed": 0}
        for pk in sorted(wanted):
            entry = entries[pk]
            if pk in renames:
                self._rename_only(entry, apply_changes, reserved, stats)
                continue
            new_type = entry.document_type
            new_expiry = entry.expiry_date
            if pk in extensions:
                new_type = types[EXTENSION_CODE]
                new_issue, new_expiry = extensions[pk]
            elif pk in modifications:
                new_type = types[MODIFICATION_CODE]
                (new_issue,) = modifications[pk]
                new_expiry = None
            elif pk in altas:
                (new_issue,) = altas[pk]
            else:
                (new_issue,) = contracts[pk]
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

    def _rename_only(self, entry, apply_changes, reserved, stats):
        """
        Realign the canonical name of an already-correct document.

        ---

        Solo realinea el nombre canónico (tipo y fecha ya correctos en
        BD, nombre con la fecha de nacimiento o la de relleno).
        """
        old_name = entry.name
        with transaction.atomic():
            result = apply_personal_canonical_rename(
                entry, apply_changes=apply_changes, reserved_names=reserved,
            )
        new_name = result.get("new_name")
        if new_name and new_name != old_name:
            stats["renamed"] += 1
            stats["changed"] += 1
            self._log(
                "SOLO NOMBRE id=%d (%s %s): %s -> %s"
                % (entry.pk, entry.document_type.code, entry.issue_date,
                   old_name, new_name)
            )
        else:
            stats["unchanged"] += 1
            self._log(
                "SOLO NOMBRE id=%d sin cambio (%s): %s"
                % (entry.pk, result.get("reason") or "ya alineado", old_name)
            )
