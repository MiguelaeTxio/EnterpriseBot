# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/set_document_expiry_dates.py
"""
H30 (S121). Fija la `expiry_date` de documentos concretos a una fecha
REVISADA A MANO sobre la imagen real del documento, y realinea su
nombre canónico (que lleva la fecha dentro) con
`apply_personal_canonical_rename()` -- solo `name` en BD, nunca GCS.

Nació para el punto 4 de la hoja de ruta S121: los 26 documentos
retipados a TACOGRAFO en S120 conservaban la fecha que tenían como
carné de conducir. Revisados uno a uno con el relevo gcs_image, 4 no
coincidían con la fecha 4b (caducidad) de la tarjeta. Genérico a
propósito: sirve para cualquier corrección de fecha decidida sobre la
imagen, sin listas de ids escritas en el código.

--set id:AAAA-MM-DD[,id:AAAA-MM-DD...]: la fecha que se ha leído en el
documento. Nunca se deduce aquí: la decide quien revisa la imagen, y
queda en el log junto con la fecha anterior.

DRY-RUN POR DEFECTO (calcula fecha y nombre nuevos sin escribir);
--apply escribe. Log propio con flush por línea (com-standards 0bis).
Idempotente: un documento que ya tiene la fecha pedida no se toca.
"""

from datetime import date, datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from document_explorer.classification_service import (
    apply_personal_canonical_rename,
)
from document_explorer.models import DocumentIndexEntry


def _parse_set(raw):
    """
    "id:AAAA-MM-DD,..." -> {id: date}; CommandError if malformed.
    ---
    "id:AAAA-MM-DD,..." -> {id: fecha}; CommandError si está mal formado.
    """
    result = {}
    for item in (raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            pk, value = item.split(":", 1)
            result[int(pk)] = date.fromisoformat(value.strip())
        except ValueError as exc:
            raise CommandError(
                "Elemento de --set no válido: %r" % item,
            ) from exc
    if not result:
        raise CommandError("--set vacío: indica al menos un id:AAAA-MM-DD.")
    return result


class Command(BaseCommand):
    help = (
        "Fija la caducidad revisada a mano sobre la imagen real y "
        "realinea el nombre canónico. Dry-run por defecto; --apply "
        "escribe."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--set", required=True,
            help="id:AAAA-MM-DD separados por comas (fecha leída en el "
                 "documento).",
        )
        parser.add_argument("--log-file", required=True)
        parser.add_argument("--apply", action="store_true")

    def _log(self, message):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        self.stdout.write(line)
        self.stdout.flush()
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        wanted = _parse_set(options["set"])
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(wanted, options["apply"])
        finally:
            self._log_handle.close()

    def _run(self, wanted, apply_changes):
        self._log("FECHAS REVISADAS (%s) -- %d documentos" % (
            "APLICAR" if apply_changes else "DRY-RUN, nada se escribe",
            len(wanted),
        ))
        entries = {
            entry.pk: entry
            for entry in DocumentIndexEntry.objects.filter(
                pk__in=wanted, deleted_at__isnull=True,
                purged_at__isnull=True,
            ).select_related("document_type")
        }
        missing = sorted(set(wanted) - set(entries))
        if missing:
            self._log("ABORTADO: ids inexistentes o no vivos: %s" % missing)
            return
        reserved = set()
        stats = {"changed": 0, "unchanged": 0, "renamed": 0, "no_name": 0}
        for pk in sorted(wanted):
            entry = entries[pk]
            new_date = wanted[pk]
            old_date = entry.expiry_date
            if old_date == new_date:
                stats["unchanged"] += 1
                self._log("SIN CAMBIO id=%d ya tiene %s | %s" % (
                    pk, new_date, entry.name,
                ))
                continue
            old_name = entry.name
            entry.expiry_date = new_date
            with transaction.atomic():
                if apply_changes:
                    entry.save(update_fields=["expiry_date"])
                result = apply_personal_canonical_rename(
                    entry, apply_changes=apply_changes,
                    reserved_names=reserved,
                )
            stats["changed"] += 1
            self._log("FECHA id=%d %s: %s -> %s" % (
                pk, entry.document_type.code if entry.document_type else "-",
                old_date or "sin fecha", new_date,
            ))
            if result.get("new_name"):
                stats["renamed"] += int(result["new_name"] != old_name)
                self._log("    nombre: %s -> %s" % (
                    old_name, result["new_name"],
                ))
            else:
                stats["no_name"] += 1
                self._log("    nombre sin realinear (%s): %s" % (
                    result.get("reason"), old_name,
                ))
        self._log("=== RESUMEN (%s) === fechas cambiadas: %d | ya "
                  "correctas: %d | nombres realineados: %d | sin nombre: %d"
                  % ("APPLY" if apply_changes else "DRY-RUN",
                     stats["changed"], stats["unchanged"], stats["renamed"],
                     stats["no_name"]))
