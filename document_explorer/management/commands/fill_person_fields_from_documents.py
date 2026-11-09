# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/fill_person_fields_from_documents.py
"""
H24 (S145). Fill the personnel file of active workers from the text
already read from their own documents.

---

H24 (S145). Rellena la ficha del personal activo con lo que dicen sus
propios documentos. Miguel Ángel: "no aparece con fecha de alta, no
sale su dirección [...] Tenemos una gran cantidad de datos que no
tenemos en base de datos, pero que vienen en los documentos. De hecho,
el alta mismo de la empresa viene en su contrato".

Solo lee `ocr_text` ya guardado (nada de Gemini ni OCR nuevo) y las
fechas ya registradas de los documentos de la persona:

- Nº de afiliación: el NSS de 12 cifras que más se repite entre IDC,
  contrato, comunicación de contrato y alta.
- Fecha de alta: el "ALTA" del IDC más reciente de su empresa (si no,
  el más reciente); sin IDC, el inicio del último contrato.
- Fecha de nacimiento: la del IDC.
- Domicilio, población y provincia: el bloque DOMICILIO del DNI/NIE más
  reciente; solo si la provincia es una provincia real.
- Caducidad del DNI/NIE, del permiso de conducir y del reconocimiento
  médico: la más reciente de sus documentos ya fechados.

Qué escribe con `--apply` (DRY-RUN POR DEFECTO):
- Campos vacíos: los rellena.
- Nº de afiliación con 11 cifras (el código de cuenta de cotización de
  la empresa, no el del trabajador): lo corrige.
- Caducidades con un documento más reciente: las actualiza.
Lo demás (fecha de alta o de nacimiento distinta de la de la ficha,
domicilio dudoso) solo se lista como REVISAR, nunca se pisa.

Sin datos personales en el código (com-actions-relay §0): todo sale de
la BD en el servidor. Log propio en `--log-file`, pantalla y archivo.
"""
import collections
import datetime

from django.core.management.base import BaseCommand

from document_explorer.models import PersonIdentity
from document_explorer.person_facts_service import (
    LABELS, found_facts, person_entries, proposals,
)


class Command(BaseCommand):
    help = "S145: rellena la ficha del personal activo con sus documentos."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)
        parser.add_argument(
            "--skip", nargs="*", default=[],
            help="id:campo que no se escriben (revisados a mano y "
                 "descartados), p. ej. 190:address_street")

    def handle(self, *args, **options):
        log_file = open(options["log_file"], "a", encoding="utf-8")

        def _log(text):
            line = "[%s] %s" % (
                datetime.datetime.now().strftime("%H:%M:%S"), text)
            print(line, flush=True)
            log_file.write(line + "\n")
            log_file.flush()

        def _plain(text):
            print(text, flush=True)
            log_file.write(text + "\n")

        apply = options["apply"]
        skip = set(options["skip"])
        _log("Ficha del personal activo desde sus documentos (S145) -- %s"
             % ("APLICANDO" if apply
                else "SIMULACIÓN (sin --apply no se escribe)"))
        people = list(PersonIdentity.objects.filter(
            is_active_employee=True).order_by(
                "first_surname", "second_surname", "given_name"))
        entries = list(person_entries(p.pk for p in people))
        found = found_facts(entries)
        _log("%d personas activas, %d documentos leídos" % (
            len(people), len(entries)))
        totals = collections.Counter()
        for number, person in enumerate(people, 1):
            props = proposals(person, found[person.pk])
            if not props:
                continue
            name = "%s %s, %s" % (
                person.first_surname, person.second_surname,
                person.given_name)
            _log("%d/%d %s (id=%d)" % (number, len(people), name, person.pk))
            to_write = []
            for field, current, value, source, action in props:
                if "%d:%s" % (person.pk, field) in skip:
                    action = "DESCARTADO"
                totals[action] += 1
                _plain("    %-10s %s: %s -> %s  [%s]" % (
                    action, LABELS[field], current or "(vacío)", value,
                    source))
                if action not in ("REVISAR", "DESCARTADO"):
                    setattr(person, field, value)
                    to_write.append(field)
            if apply and to_write:
                person.save(update_fields=to_write)
        log_file.write("\n")
        _plain("RESUMEN")
        for action in ("rellenar", "corregir", "actualizar", "REVISAR",
                       "DESCARTADO"):
            _plain("%s: %d" % (action, totals[action]))
        _plain("Escrito en la BD: %s" % ("sí" if apply else "no"))
        log_file.close()
