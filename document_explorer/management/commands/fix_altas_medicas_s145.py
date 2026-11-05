# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/fix_altas_medicas_s145.py
"""
H24 (S145). Nine sick-leave discharge forms filed as sick-leave forms.

---

H24 (S145). Nueve partes médicos de ALTA guardados como parte de BAJA
(PARTE_BAJA_MEDICA). Miguel Ángel: "si tengo una alta médica [...] y
el documento está como baja médica, pues ya lo tenemos mal". Cada uno
se ha mirado a mano en esta sesión (impreso P.9 con "Parte de alta"
marcado y su fecha del alta); los dos con solo "Parte de baja"
marcado (ids 27909 y 36733) se quedan como están y no figuran aquí.

Por cada id: comprueba que sigue vivo y como PARTE_BAJA_MEDICA, pone la
fecha del alta del impreso como issue_date y pasa el tipo a
ALTA_MEDICA con `change_document_type()` -- el mismo cambio de tipo que
hace el panel (nombre canónico, sustituciones). Lo que no cuadre se
salta y se dice.

DRY-RUN POR DEFECTO; `--apply` escribe. Log propio en `--log-file`,
pantalla y archivo a la vez.
"""
import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog
from document_explorer.subject_upload_service import change_document_type

# id -> fecha del alta leída en el propio impreso.
ALTAS = {
    26340: datetime.date(2016, 1, 19),   # Álvarez Gea
    26520: datetime.date(2016, 2, 26),   # Fontalba Serón
    26597: datetime.date(2015, 12, 23),  # Gómez García
    26716: datetime.date(2015, 7, 22),   # José Luis Álvarez Díaz
    38333: datetime.date(2018, 1, 23),   # Fontalba Serón (baja y alta)
    38336: datetime.date(2020, 10, 14),  # Fontalba Serón
    38347: datetime.date(2018, 1, 29),   # García Pinto
    38389: datetime.date(2015, 9, 21),   # Gutiérrez Díaz
    38472: datetime.date(2020, 12, 21),  # Ramos Jiménez
}


class Command(BaseCommand):
    help = "S145: los 9 partes de alta guardados como baja, a ALTA_MEDICA."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def handle(self, *args, **options):
        log_file = open(options["log_file"], "a", encoding="utf-8")

        def _log(text):
            line = "[%s] %s" % (
                datetime.datetime.now().strftime("%H:%M:%S"), text)
            print(line, flush=True)
            log_file.write(line + "\n")
            log_file.flush()

        apply = options["apply"]
        _log("Altas médicas guardadas como baja (S145) -- %s" % (
            "APLICANDO" if apply
            else "SIMULACIÓN (sin --apply no se escribe)"))
        alta = DocumentTypeCatalog.objects.get(code="ALTA_MEDICA")
        done = skipped = 0
        for number, (pk, alta_date) in enumerate(ALTAS.items(), 1):
            entry = DocumentIndexEntry.objects.select_related(
                "document_type").filter(pk=pk).first()
            prefix = "%d/%d id=%d" % (number, len(ALTAS), pk)
            if entry is None or entry.deleted_at is not None:
                _log("%s SALTADO: no existe o está en la papelera" % prefix)
                skipped += 1
                continue
            code = entry.document_type.code if entry.document_type_id else ""
            if code != "PARTE_BAJA_MEDICA":
                _log("%s SALTADO: ya no es PARTE_BAJA_MEDICA (%s)" % (
                    prefix, code or "sin tipo"))
                skipped += 1
                continue
            _log("%s %s | fecha %s -> %s | %s -> ALTA_MEDICA" % (
                prefix, entry.name, entry.issue_date, alta_date, code))
            if apply:
                with transaction.atomic():
                    entry.issue_date = alta_date
                    entry.save(update_fields=["issue_date"])
                    outcome = change_document_type(entry, alta)
                _log("%s HECHO: nombre nuevo %s" % (
                    prefix, outcome["new_name"]))
            done += 1
        log_file.write("\n")
        for text in (
            "RESUMEN",
            "%s: %d" % ("Corregidos" if apply else "Se corregirían", done),
            "Saltados: %d" % skipped,
        ):
            print(text, flush=True)
            log_file.write(text + "\n")
        log_file.close()
