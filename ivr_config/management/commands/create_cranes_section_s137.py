# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/management/commands/create_cranes_section_s137.py
"""
H30 (S137). Creates the "Grúas" section (crane operators of mobile
cranes and truck cranes) and moves Antonio Javier Mérida there, as a
crane operator.

---

H30 (S137). Miguel Ángel: Antonio Javier Mérida no es de Elevación;
al darse de alta por WhatsApp eligió Elevación pensando en "elevación
de cargas". No había sección para los de grúas móviles y brazos, así
que se crea "Grúas". Miguel Ángel: son gruistas, no chóferes ("casi
siempre van a estar trabajando con la pluma"; chófer queda para
Asistencia), así que su rol por defecto es el nuevo GRUISTA
(CRANE_OPERATOR). Familias de flota MÓVILES y AUTOCARGANTES, sin
transferencia de llamadas del IVR. Su contacto sale de Elevación y
entra en Grúas, y su usuario pasa de operario de taller a gruista.

Idempotente: si la sección ya existe no se crea otra, y lo que ya está
hecho no se repite. Sin `--apply` solo informa.
"""
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from ivr_config.models import CompanyUser, Section, SectionContact

SECTION_NAME = "Grúas"
SECTION_DESCRIPTION = (
    "Gruistas: grúas móviles (A) y camiones grúa o brazos autocargantes "
    "(B)."
)
FLEET_FAMILIES = ["MÓVILES", "AUTOCARGANTES"]
WORKER_DNI = "74858722R"
OLD_SECTION_NAME = "Elevación"


class Command(BaseCommand):
    """
    Create the Grúas section and move Antonio Javier Mérida to it.

    ---

    Crea la sección Grúas y pasa a ella a Antonio Javier Mérida.
    """

    help = (
        "Crea la sección Grúas (gruistas) y pasa a ella a Antonio Javier "
        "Mérida como gruista (H30, S137). Sin --apply solo informa."
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
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._handle = handle
            apply = options["apply"]
            self._log("Inicio: sección Grúas -- %s." % (
                "APLICAR" if apply else "SOLO INFORME"))
            with transaction.atomic():
                self._run(apply)
            self._log("Fin.")

    def _run(self, apply):
        worker = CompanyUser.objects.filter(dni=WORKER_DNI).select_related(
            "user", "company").first()
        if worker is None:
            self._log("No hay usuario con DNI %s: no se hace nada."
                      % WORKER_DNI)
            return
        company = worker.company
        self._log("1/4 Trabajador: %s %s (usuario %s), rol %s." % (
            worker.user.first_name, worker.user.last_name,
            worker.user.username, worker.get_role_display()))
        section = Section.objects.filter(
            company=company, name=SECTION_NAME).first()
        if section is None:
            self._log("2/4 Sección %s: se crea (rol gruista, familias %s)."
                      % (SECTION_NAME, ", ".join(FLEET_FAMILIES)))
            if apply:
                section = Section.objects.create(
                    company=company, name=SECTION_NAME,
                    description=SECTION_DESCRIPTION,
                    fleet_families=FLEET_FAMILIES,
                    default_role=Section.DEFAULT_ROLE_CRANE_OPERATOR,
                    ivr_transfer_enabled=False,
                )
        else:
            self._log("2/4 Sección %s: ya existe (id %d)."
                      % (SECTION_NAME, section.pk))
        links = SectionContact.objects.filter(
            contact__company_user=worker).select_related(
            "section", "contact")
        self._log("3/4 Secciones ahora: %s." % (
            ", ".join(link.section.name for link in links) or "ninguna"))
        for link in links:
            if link.section.name != OLD_SECTION_NAME:
                continue
            target = section
            already = target is not None and SectionContact.objects.filter(
                section=target, contact=link.contact).exists()
            self._log("    Contacto %d: sale de %s%s." % (
                link.contact.pk, OLD_SECTION_NAME,
                "" if already else " y entra en %s" % SECTION_NAME))
            if apply:
                if already:
                    link.delete()
                else:
                    link.section = target
                    link.save(update_fields=["section"])
        if worker.role != CompanyUser.ROLE_CRANE_OPERATOR:
            self._log("4/4 Rol: %s -> Gruista." % worker.get_role_display())
            if apply:
                worker.role = CompanyUser.ROLE_CRANE_OPERATOR
                worker.save(update_fields=["role"])
        else:
            self._log("4/4 Rol: ya es gruista.")
