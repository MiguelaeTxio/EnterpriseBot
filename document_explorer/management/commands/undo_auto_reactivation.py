# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/undo_auto_reactivation.py
"""
H30 (S127). Undo an automatic reactivation done by the H28 pipeline.

---

H30 (S127). Deshace una reactivación AUTOMÁTICA del H28 -- no una baja
nueva (Miguel Ángel: "nada de botón de dar de baja, puesto que nadie ha
pulsado el de alta"). Caso real: Ruiz Portillo, dado de baja el
23/09/2026, fue marcado activo el 03/10/2026 10:03 UTC por
`_activate_person_on_hiring_document` al procesarse su alta antigua.

Solo restaura lo que tocó el pipeline: `is_active_employee=False` y su
documentación de vuelta a la carpeta que le corresponde
(`relocate_if_needed`). La fecha de baja, la de alta y la cuenta del
panel no se tocan. Se niega si la persona no tiene fecha de baja, salvo
con `--sin-cruzar`: persona CREADA y activada por el barrido hacia atrás
(caso Palliotti, creado el 02/10/2026 desde un contrato de 2025), que
vuelve a "sin cruzar" (`None`, como el histórico desde S76) sin fecha de
alta ni de baja inventadas.

Sin --apply solo informa.
"""
from django.core.management.base import BaseCommand

from document_explorer.models import PersonIdentity
from document_explorer.person_folder_service import (
    expected_base_folder, relocate_if_needed,
)


class Command(BaseCommand):
    help = "S127: deshace una reactivación automática. Sin --apply informa."

    def add_arguments(self, parser):
        parser.add_argument("--person", type=int, required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--sin-cruzar", action="store_true")

    def handle(self, *args, **options):
        person = PersonIdentity.objects.get(pk=options["person"])
        self.stdout.write(
            "# [S127] %s %s, %s (pk=%s) -- %s" % (
                person.first_surname, person.second_surname or "",
                person.given_name, person.pk,
                "APLICANDO" if options["apply"] else "MODO PRUEBA"))
        self.stdout.write(
            "   ahora: activo=%s, alta=%s, baja=%s, carpeta=%s" % (
                person.is_active_employee, person.hire_date,
                person.termination_date, person.folder_path))
        new_state = False
        if not person.termination_date:
            if not options["sin_cruzar"]:
                self.stdout.write("   [PARADA] Sin fecha de baja: no es una "
                                  "reactivación que deshacer (usar "
                                  "--sin-cruzar solo para una persona creada "
                                  "por el barrido).")
                return
            new_state = None
        # None ("sin cruzar") vive en INACTIVOS igual que False (S76); se
        # pasa False porque expected_base_folder trata None como "el
        # estado actual de la persona" (la prueba de Palliotti mostraba su
        # carpeta de activos).
        target = expected_base_folder(person, is_active=False)
        self.stdout.write("   queda: activo=%s, misma alta y baja, "
                          "carpeta=%s" % (new_state, target))
        if not options["apply"]:
            return
        person.is_active_employee = new_state
        person.save(update_fields=["is_active_employee", "updated_at"])
        moved, folder, count = relocate_if_needed(person)
        person.refresh_from_db()
        self.stdout.write(
            "   [OK] activo=%s, carpeta=%s, %d documento(s) movidos." % (
                person.is_active_employee, person.folder_path, count))
