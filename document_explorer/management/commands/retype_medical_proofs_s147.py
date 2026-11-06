# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/retype_medical_proofs_s147.py
"""
H24 (S147). Medical attendance proofs to their new document type.

---

H24 (S147). Retipado de los justificantes de asistencia médica al tipo
nuevo JUSTIFICANTE_ASISTENCIA_MEDICA (directriz 4.22, opción 1 de
Miguel Ángel). Barrido hecho en esta sesión sobre todo el texto ya
leído de PERSONAL (frases "justificante de asistencia/consulta/cita",
"ha acudido/asistido a consulta", "ha sido atendido"...): de todo lo
encontrado, solo dos son de verdad un justificante de que el propio
trabajador fue al médico; el resto son dosieres, cursos o altas cuya
primera página no lo es. Sin texto leído no queda ninguno de las
familias de salud o laboral que pueda serlo.

- 36621 (Muñoz Cara): justificante de cita del SAS, "ha acudido a la
  consulta, tratamiento o exploración", tipado en S127 como
  JUSTIFICANTE_LABORAL_AUSENCIA a falta de un tipo mejor.
- 53206 (Muñoz Cara): justificante subido desde Mis solicitudes antes
  de existir el tipo (se guardó como INFORME_MEDICO).

Por cada id: comprueba que sigue vivo y con el tipo esperado y lo pasa
al tipo nuevo con change_document_type() (nombre canónico y
sustituciones, igual que el panel). Lo que no cuadre se salta y se
dice. DRY-RUN POR DEFECTO; `--apply` escribe. Log propio en
`--log-file`, pantalla y archivo a la vez.
"""
import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog
from document_explorer.subject_upload_service import change_document_type

NEW_CODE = "JUSTIFICANTE_ASISTENCIA_MEDICA"
# id -> tipo que tiene que tener ahora.
ENTRIES = {
    36621: "JUSTIFICANTE_LABORAL_AUSENCIA",
    53206: "INFORME_MEDICO",
}


class Command(BaseCommand):
    help = "S147: justificantes de asistencia médica a su tipo nuevo."

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
        _log("Justificantes de asistencia médica (S147) -- %s" % (
            "APLICANDO" if apply
            else "SIMULACIÓN (sin --apply no se escribe)"))
        new_type = DocumentTypeCatalog.objects.get(code=NEW_CODE)
        done = skipped = 0
        for number, (pk, expected) in enumerate(ENTRIES.items(), 1):
            prefix = "%d/%d id=%d" % (number, len(ENTRIES), pk)
            entry = DocumentIndexEntry.objects.select_related(
                "document_type").filter(pk=pk).first()
            if entry is None or entry.deleted_at is not None:
                _log("%s SALTADO: no existe o está en la papelera" % prefix)
                skipped += 1
                continue
            code = entry.document_type.code if entry.document_type_id else ""
            if code != expected:
                _log("%s SALTADO: es %s, no %s" % (
                    prefix, code or "sin tipo", expected))
                skipped += 1
                continue
            if not apply:
                _log("%s %s -> %s (%s)" % (prefix, code, NEW_CODE,
                                           entry.name))
                done += 1
                continue
            with transaction.atomic():
                result = change_document_type(entry, new_type)
            _log("%s HECHO: %s -> %s, ahora %s" % (
                prefix, code, NEW_CODE, result["new_name"]))
            done += 1
        _log("RESUMEN: %d %s, %d saltados." % (
            done, "cambiados" if apply else "a cambiar", skipped))
        log_file.close()
