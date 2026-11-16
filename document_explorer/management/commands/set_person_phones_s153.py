# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/set_person_phones_s153.py
"""
S153. Load workers' company and personal phones from a list.

---

S153. Mete los teléfonos de empresa y particular de una lista de
trabajadores (Miguel Ángel: "Hay que meter los teléfonos de Huelva").
Los datos NO van en git: el archivo lo escribe el Comando S en SWAP,
una línea por trabajador:

    APELLIDO1 APELLIDO2, NOMBRE;TELÉFONO EMPRESA;TELÉFONO PARTICULAR

El nombre se busca en las fichas de Personal: primer apellido, segundo
apellido (admite abreviaturas como DGUEZ) y nombre; solo si hay
exactamente una ficha que encaja. El de empresa va a `phone` (al que se
mandan los mensajes) y el particular a `phone_secondary` (si es el
mismo número, el particular queda vacío). Sin --apply solo informa.
Log propio con pantalla y archivo a la vez (com-standards 0bis).
"""
import re

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    """
    Set phones from a SWAP list (dry run by default).
    ---
    Mete los teléfonos de una lista de SWAP.
    """

    help = "Teléfonos de empresa y particular desde una lista (S153)."

    def add_arguments(self, parser):
        parser.add_argument("--data-file", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, text):
        stamp = timezone.localtime().strftime("%H:%M:%S")
        line = "[%s] %s" % (stamp, text)
        print(line, flush=True)
        self._out.write(line + "\n")
        self._out.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as out:
            self._out = out
            self._run(options["data_file"], options["apply"])

    def _find(self, people, written):
        from hr_calendar.albaran_check import _abbreviates, _plain

        def ordered(text):
            return [w for w in re.split(r"\s+", " ".join(
                sorted(_plain(text), key=text.upper().find))) if w]

        surnames, _sep, given = written.partition(",")
        words = ordered(surnames)
        given_words = ordered(given)

        def ok(person):
            first = _plain(person.first_surname)
            second = _plain(person.second_surname)
            own_given = _plain(person.given_name)
            if not words or not given_words or not first:
                return False
            if not any(_abbreviates(words[0], f) for f in first):
                return False
            if len(words) > 1 and second and not any(
                    _abbreviates(words[1], s) for s in second):
                return False
            return any(_abbreviates(given_words[0], o) for o in own_given)

        return [p for p in people if ok(p)]

    def _run(self, data_file, apply_changes):
        from document_explorer.models import PersonIdentity
        from document_explorer.person_phone_service import normalize_mobile

        self._log("Teléfonos desde %s (%s)" % (
            data_file, "APLICANDO" if apply_changes
            else "simulación, sin cambios"))
        people = list(PersonIdentity.objects.all())
        done = problems = 0
        with open(data_file, encoding="utf-8") as handle:
            rows = [line.strip() for line in handle if line.strip()]
        for row in rows:
            parts = [p.strip() for p in row.split(";")]
            if len(parts) != 3:
                self._log("Línea mal formada: %s" % row)
                problems += 1
                continue
            name, work, own = parts
            work_n, own_n = normalize_mobile(work), normalize_mobile(own)
            found = self._find(people, name)
            if len(found) != 1:
                what = ("no encontrado" if not found else
                        "varias fichas: " + ", ".join(
                            "#%d" % p.pk for p in found))
                self._log("%s: %s" % (name, what))
                problems += 1
                continue
            person = found[0]
            second = own_n if own_n and own_n != work_n else ""
            self._log("%s -> ficha #%d (%s %s, %s): empresa %s -> %s; "
                      "particular %s -> %s" % (
                          name, person.pk, person.first_surname,
                          person.second_surname, person.given_name,
                          person.phone or "-", work_n or "-",
                          person.phone_secondary or "-", second or "-"))
            if apply_changes:
                person.phone = work_n or person.phone
                person.phone_secondary = second
                person.save(update_fields=["phone", "phone_secondary"])
            done += 1
        self._log("Resumen: %d %s, %d con problemas." % (
            done, "actualizadas" if apply_changes else "se actualizarían",
            problems))
