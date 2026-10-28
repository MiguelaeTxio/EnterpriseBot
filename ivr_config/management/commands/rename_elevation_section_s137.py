# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/management/commands/rename_elevation_section_s137.py
"""
H30 (S137). Renames the "Elevación" section to "Plataformas".

---

H30 (S137). Miguel Ángel: la sección "Elevación" pasa a llamarse
"Plataformas". Antonio Javier Mérida (gruista) se dio de alta en ella
pensando en "elevación de cargas"; la sección es la del alquiler de
plataformas elevadoras, y ahora que existe "Grúas" el nombre tiene que
dejarlo claro en el alta por WhatsApp. Solo cambia el nombre: los
contactos, el rol por defecto, el horario y el flujo IVR siguen igual.
Escribe en el log la descripción actual, por si también la nombra.

Idempotente. Sin `--apply` solo informa.
"""
from datetime import datetime

from django.core.management.base import BaseCommand

from ivr_config.models import Section

OLD_NAME = "Elevación"
NEW_NAME = "Plataformas"


class Command(BaseCommand):
    """
    Rename the Elevación section to Plataformas.

    ---

    Cambia el nombre de la sección Elevación a Plataformas.
    """

    help = (
        "Cambia el nombre de la sección Elevación a Plataformas (H30, "
        "S137). Sin --apply solo informa."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--log-file", required=True,
            help="Ruta del log propio (pantalla y archivo a la vez).",
        )

    def _log(self, message):
        """
        Print and append one line to the log file, flushed.

        ---

        Escribe una línea en pantalla y en el log, con flush.
        """
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._handle.write(line + "\n")
        self._handle.flush()

    def handle(self, *args, **options):
        apply = options["apply"]
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._handle = handle
            self._log("Inicio: %s -> %s -- %s." % (
                OLD_NAME, NEW_NAME, "APLICAR" if apply else "SOLO INFORME"))
            sections = Section.objects.filter(name=OLD_NAME)
            if not sections.exists():
                self._log("No hay ninguna sección %s (¿ya renombrada?). "
                          "Con el nombre nuevo: %d." % (
                              OLD_NAME, Section.objects.filter(
                                  name=NEW_NAME).count()))
            for position, section in enumerate(sections, start=1):
                self._log("%d. Sección %d: %s, %d contactos, rol por "
                          "defecto %s." % (
                              position, section.pk, section.name,
                              section.contacts.count(),
                              section.get_default_role_display()))
                self._log("   Descripción: %s" % (
                    section.description or "(vacía)"))
                if apply:
                    section.name = NEW_NAME
                    section.save(update_fields=["name", "updated_at"])
                    self._log("   Renombrada a %s." % NEW_NAME)
            self._log("Fin.")
