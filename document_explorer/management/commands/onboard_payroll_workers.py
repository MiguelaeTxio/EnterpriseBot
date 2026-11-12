# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/onboard_payroll_workers.py
"""
S153 (H31, sesión invasora). Load the payroll lists of the group
companies: worker files, panel accounts, employer changes and
selection groups, from a JSON data file kept outside git.

---

S153 (H31, sesión invasora). Carga los listados de nóminas de las
empresas del grupo (Miguel Ángel: "todos estos usuarios van a recibir
sus nóminas a través de la aplicación"): fichas que faltan, alta en el
panel, cambios de empresa, perfil fiscal de una empresa nueva y grupos
de selección. Los datos personales (DNI, nombres, fechas) llegan en un
JSON que vive solo en el servidor, nunca en git (com-standards).

Hace lo mismo que el panel, con sus mismas funciones:
- ficha nueva: igual que el alta por formulario (carpeta ACTIVOS/
  {EMPRESA}, sección desde la fecha de alta, carpeta local);
- ficha de baja: reactivación con la fecha de alta del listado;
- cambio de empresa: igual que "Cambiar empresa" de Personal (traslado
  de su documentación y de su carpeta local);
- usuario: personal_access.create_access (nombre.apellido, contraseña
  las cuatro últimas cifras del DNI); quien ya tiene usuario lo
  conserva; "link_user_id" vincula la ficha a un usuario existente.
- grupos: los crea si no existen (creados por `by_username`, así son
  "Generales") y añade las personas. "auto_group": trabajadores activos
  de las empresas indicadas que no estén en ningún grupo; a los que
  tienen usuario de trabajador se les pone la base indicada.

Sin --apply solo informa de lo que haría. Idempotente: relanzarlo no
duplica nada. --log-file obligatorio (pantalla y archivo a la vez).
"""
import datetime
import json

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from budgets.models import Base
from document_explorer import local_download_service, naming_service
from document_explorer.index_writer import ensure_folder_chain
from document_explorer.models import (
    CompanyFiscalProfile,
    PersonGroupTemplate,
    PersonIdentity,
)
from ivr_config.models import CompanyUser, Section

BUCKET = local_download_service.BUCKET


class Command(BaseCommand):
    """
    Load payroll lists (files, accounts, groups) from a JSON file.
    ---
    Carga los listados de nóminas (fichas, usuarios, grupos) desde un
    JSON del servidor.
    """

    help = "S153: fichas, usuarios y grupos de los listados de nóminas."

    def add_arguments(self, parser):
        parser.add_argument("--data", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------

    def _log(self, message):
        """
        Print and append one timestamped line to the log, flushed.
        ---
        Escribe una línea con hora en pantalla y en el log, con flush.
        """
        line = "[%s] %s" % (
            datetime.datetime.now().strftime("%H:%M:%S"), message,
        )
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def _log_plain(self, message):
        """
        Same as _log, without the time (final summary).
        ---
        Igual que _log, sin la hora (resumen final).
        """
        print(message, flush=True)
        self._log_handle.write(message + "\n")
        self._log_handle.flush()

    def _progress(self, done, total):
        elapsed = (datetime.datetime.now() - self._start).total_seconds()
        eta = (elapsed / done) * (total - done) if done else 0
        end = datetime.datetime.now() + datetime.timedelta(seconds=eta)
        self._log("Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s)"
                  % (done, total, done * 100 // total, int(eta // 60),
                     int(eta % 60), end.strftime("%H:%M:%S")))

    # ------------------------------------------------------------------
    # Main
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        self._start = datetime.datetime.now()
        self.apply = options["apply"]
        with open(options["data"], encoding="utf-8") as handle:
            data = json.load(handle)
        self.by = CompanyUser.objects.select_related("user").filter(
            user__username=data["by_username"]).first()
        if self.by is None:
            raise CommandError("No existe %s" % data["by_username"])
        self.person_ct = ContentType.objects.get_for_model(PersonIdentity)
        self.summary = []
        self.errors = []
        self._log("Modo: %s" % ("APLICAR" if self.apply else "SIMULACIÓN"))

        workers = data.get("workers", [])
        changes = data.get("employer_changes", [])
        total = len(workers) + len(changes)
        done = 0
        for spec in workers:
            done += 1
            self._log("(%d/%d) %s %s, %s" % (
                done, total, spec["first_surname"],
                spec.get("second_surname", ""), spec["given_name"]))
            try:
                self._worker(spec)
            except (ValidationError, ValueError) as exc:
                self._error("%s: %s" % (spec["dni"], exc))
            self._progress(done, total)
        for spec in changes:
            done += 1
            self._log("(%d/%d) Cambio de empresa %s -> %s" % (
                done, total, spec["dni"], spec["employer"]))
            self._employer_change(spec)
            self._progress(done, total)

        for spec in data.get("fiscal_profiles", []):
            self._fiscal_profile(spec)
        for spec in data.get("groups", []):
            self._group(spec)
        if data.get("auto_group"):
            self._auto_group(data["auto_group"])

        self._log_plain("")
        self._log_plain("=== RESUMEN (%s) ===" % (
            "aplicado" if self.apply else "simulación, nada guardado"))
        for number, line in enumerate(self.summary, 1):
            self._log_plain("%d. %s" % (number, line))
        self._log_plain("")
        self._log_plain("Errores: %d" % len(self.errors))
        for number, line in enumerate(self.errors, 1):
            self._log_plain("%d. %s" % (number, line))
        self._log_handle.close()

    def _note(self, message):
        self.summary.append(message)
        self._log("  " + message)

    def _error(self, message):
        self.errors.append(message)
        self._log("  ERROR " + message)

    # ------------------------------------------------------------------
    # Workers
    # ------------------------------------------------------------------

    @staticmethod
    def _date(raw):
        return datetime.date.fromisoformat(raw) if raw else None

    def _worker(self, spec):
        person = PersonIdentity.objects.filter(dni=spec["dni"]).first()
        section = Section.objects.filter(pk=spec["section_id"]).first()
        if section is None:
            raise ValueError("no existe la sección %s" % spec["section_id"])
        label = "%s %s, %s" % (spec["first_surname"],
                               spec.get("second_surname", ""),
                               spec["given_name"])
        if person is None:
            self._note("%s: ficha nueva (%s, sección %s)" % (
                label, spec["employer"], section.name))
            if self.apply:
                person = self._create_person(spec, section)
        elif not person.is_active_employee:
            self._note("%s: ficha %s de baja -> activa (%s)" % (
                label, person.pk, spec["employer"]))
            if self.apply:
                self._reactivate(person, spec, section)
        else:
            if (person.employer_company or "") != spec["employer"]:
                self._note("%s: empresa '%s' -> '%s'" % (
                    label, person.employer_company, spec["employer"]))
                if self.apply:
                    self._set_employer(person, spec["employer"])
            else:
                self._log("  ya activa en %s" % spec["employer"])
        if person is not None and self.apply:
            self._fill_blanks(person, spec)
        self._account(person, spec, section, label)

    def _create_person(self, spec, section):
        from document_explorer.person_facts_service import refresh_person
        from hr_calendar.balance import assign_section

        hire = self._date(spec.get("hire")) or datetime.date.today()
        folder_path = "%s/%s" % (
            naming_service.build_person_category_root(
                spec["first_surname"], spec.get("second_surname", ""),
                spec["employer"], True,
            ),
            naming_service.build_person_folder_name(
                spec["first_surname"], spec.get("second_surname", ""),
                spec["given_name"],
            ),
        )
        person = PersonIdentity(
            company=self.by.company,
            dni=spec["dni"],
            first_surname=spec["first_surname"],
            second_surname=spec.get("second_surname", ""),
            given_name=spec["given_name"],
            is_active_employee=True,
            employer_company=spec["employer"],
            ss_affiliation_number=spec.get("ss", ""),
            birth_date=self._date(spec.get("birth")),
            hire_date=hire,
            folder_path=folder_path,
        )
        person.full_clean()
        with transaction.atomic():
            person.save()
            ensure_folder_chain(BUCKET, folder_path)
            assign_section([person], section, hire, self.by)
        refresh_person(person)
        local_download_service.create_for_person(
            person, self.by, always=True)
        self._log("  ficha %s creada en %s" % (person.pk, folder_path))
        return person

    def _reactivate(self, person, spec, section):
        from hr_calendar.balance import assign_section
        from panel.views_documentation_h30 import _reactivate_person

        hire = self._date(spec.get("hire")) or datetime.date.today()
        previous_local = local_download_service.snapshot_paths(person)
        if (person.employer_company or "") != spec["employer"]:
            person.employer_company = spec["employer"]
            person.save(update_fields=["employer_company", "updated_at"])
        _reactivate_person(person, hire, self.person_ct, self.by,
                           local_sync=False)
        person.refresh_from_db()
        assign_section([person], section, hire, self.by)
        ensure_folder_chain(BUCKET, person.folder_path)
        local_download_service.create_for_person(
            person, self.by, previous_local)
        self._log("  reactivada en %s" % person.folder_path)

    def _set_employer(self, person, employer):
        from document_explorer.person_folder_service import (
            relocate_if_needed,
        )

        previous_local = local_download_service.snapshot_paths(person)
        person.employer_company = employer
        person.save(update_fields=["employer_company", "updated_at"])
        relocated, folder, count = relocate_if_needed(person)
        if relocated:
            local_download_service.create_for_person(
                person, self.by, previous_local)
            self._log("  documentación trasladada a %s (%d archivos)"
                      % (folder, count))

    def _fill_blanks(self, person, spec):
        """
        Fill only the empty fields (never overwrite a known value).
        ---
        Rellena solo lo que está vacío en la ficha.
        """
        changed = []
        values = {
            "ss_affiliation_number": spec.get("ss", ""),
            "birth_date": self._date(spec.get("birth")),
        }
        for field, value in values.items():
            if value and not getattr(person, field):
                setattr(person, field, value)
                changed.append(field)
        if changed:
            person.save(update_fields=changed + ["updated_at"])

    def _employer_change(self, spec):
        person = PersonIdentity.objects.filter(dni=spec["dni"]).first()
        if person is None:
            self._error("%s: no hay ficha" % spec["dni"])
            return
        if (person.employer_company or "") == spec["employer"]:
            self._log("  ya tiene esa empresa")
            return
        self._note("%s %s: empresa '%s' -> '%s'" % (
            person.first_surname, person.given_name,
            person.employer_company, spec["employer"]))
        if self.apply:
            self._set_employer(person, spec["employer"])

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    def _account(self, person, spec, section, label):
        from panel import personal_access

        if spec.get("link_user_id"):
            self._link(person, spec, label)
            return
        account = spec.get("account")
        if not account:
            return
        if person is not None and personal_access.has_account(person):
            self._log("  conserva su usuario %s"
                      % person.company_user.user.username)
            return
        acc_section = Section.objects.filter(
            pk=account.get("section_id", section.pk)).first()
        base = Base.objects.filter(pk=account["base_id"]).first() if (
            account.get("base_id")) else None
        if person is None:
            # Simulación de una ficha nueva: el nombre que tendría.
            person = PersonIdentity(
                dni=spec["dni"], first_surname=spec["first_surname"],
                second_surname=spec.get("second_surname", ""),
                given_name=spec["given_name"],
            )
        username = self._free_username(person)
        if not username:
            self._error("%s: sin nombre de usuario libre" % label)
            return
        self._note("%s: usuario %s (%s, base %s, sección %s)" % (
            label, username, account["role"],
            base.name if base else "-", acc_section.name))
        if self.apply:
            try:
                personal_access.create_access(
                    person, username, acc_section, base, account["role"],
                    self.by)
            except personal_access.AccessError as exc:
                self._error("%s: %s" % (label, exc))

    @staticmethod
    def _free_username(person):
        from panel.personal_access import username_options

        for option in username_options(person):
            if option and not User.objects.filter(
                    username__iexact=option).exists():
                return option
        return ""

    def _link(self, person, spec, label):
        account = CompanyUser.objects.select_related("user").filter(
            pk=spec["link_user_id"]).first()
        if account is None:
            self._error("%s: no existe el usuario %s"
                        % (label, spec["link_user_id"]))
            return
        if person is not None and person.company_user_id == account.pk:
            self._log("  ya vinculada a %s" % account.user.username)
            return
        other = PersonIdentity.objects.filter(company_user=account).first()
        if other is not None:
            self._error("%s: %s ya es de la ficha %s"
                        % (label, account.user.username, other.pk))
            return
        self._note("%s: se vincula a su usuario %s (%s)" % (
            label, account.user.username, account.role))
        if self.apply:
            with transaction.atomic():
                person.company_user = account
                person.save(update_fields=["company_user", "updated_at"])
                if not account.dni:
                    account.dni = person.dni
                    account.save(update_fields=["dni"])

    # ------------------------------------------------------------------
    # Fiscal profile and groups
    # ------------------------------------------------------------------

    def _fiscal_profile(self, spec):
        profile = CompanyFiscalProfile.objects.filter(
            tax_id=spec["tax_id"]).first()
        admin = PersonIdentity.objects.filter(
            dni=spec.get("administrator_dni", "")).first()
        if profile is None:
            self._note("Perfil fiscal nuevo: %s (%s)" % (
                spec["legal_name"], spec["tax_id"]))
            if self.apply:
                CompanyFiscalProfile.objects.create(
                    legal_name=spec["legal_name"], tax_id=spec["tax_id"],
                    name_aliases="\n".join(spec.get("aliases", [])),
                    administrator=admin,
                )
        elif admin is not None and profile.administrator_id is None:
            self._note("Perfil fiscal %s: administrador %s %s" % (
                profile.legal_name, admin.first_surname, admin.given_name))
            if self.apply:
                profile.administrator = admin
                profile.save(update_fields=["administrator", "updated_at"])
        else:
            self._log("Perfil fiscal %s ya existe" % profile.legal_name)

    def _group_node(self, path):
        """
        The group at `path` (list of names), created when missing.
        ---
        El grupo de la ruta (lista de nombres); se crea si falta. En
        simulación devuelve None si no existe todavía.
        """
        parent = None
        for name in path:
            node = PersonGroupTemplate.objects.filter(
                name=name, parent=parent).first()
            if node is None:
                self._note("Grupo nuevo: %s" % " › ".join(
                    path[:path.index(name) + 1]))
                if not self.apply:
                    return None
                node = PersonGroupTemplate.objects.create(
                    name=name, parent=parent, created_by=self.by)
            parent = node
        return parent

    def _group(self, spec):
        group = self._group_node(spec["path"])
        people = list(PersonIdentity.objects.filter(dni__in=spec["dnis"]))
        missing = set(spec["dnis"]) - {p.dni for p in people}
        if missing and self.apply:
            self._error("%s: %d persona(s) sin ficha"
                        % (" › ".join(spec["path"]), len(missing)))
        current = set(group.members.values_list("pk", flat=True)) if (
            group) else set()
        new = [p for p in people if p.pk not in current]
        self._note("%s: +%d persona(s)%s" % (
            " › ".join(spec["path"]), len(new) + (
                len(missing) if not self.apply else 0),
            "" if spec["dnis"] else " (vacío)"))
        if self.apply and new:
            group.members.add(*new)

    def _auto_group(self, spec):
        """
        Active workers of the given employers with no group at all.
        ---
        Trabajadores activos de esas empresas que no están en ningún
        grupo. Quien tiene un usuario que no es de trabajador
        (administración, supervisión...) no es operario: se informa y
        se deja fuera.
        """
        group = self._group_node(spec["path"])
        base = Base.objects.get(pk=spec["base_id"])
        people = PersonIdentity.objects.filter(
            is_active_employee=True, employer_company__in=spec["employers"],
            group_templates__isnull=True,
        ).select_related("company_user").order_by(
            "first_surname", "second_surname")
        added, based = [], 0
        for person in people:
            account = person.company_user
            name = "%s %s, %s" % (person.first_surname,
                                  person.second_surname, person.given_name)
            if account is not None and (
                    account.role not in CompanyUser.WORKER_ROLES):
                self._note("%s: fuera (usuario %s, rol %s)" % (
                    " › ".join(spec["path"]), account.user.username,
                    account.role))
                continue
            added.append(person)
            if account is not None and account.base_id != base.pk:
                based += 1
                if self.apply:
                    account.base = base
                    account.save(update_fields=["base"])
            self._log("  %s -> %s" % (name, " › ".join(spec["path"])))
        self._note("%s: +%d persona(s); base %s a %d usuario(s)" % (
            " › ".join(spec["path"]), len(added), base.name, based))
        if self.apply and added:
            group.members.add(*added)
