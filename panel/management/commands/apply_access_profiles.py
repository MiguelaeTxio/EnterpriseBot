# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/management/commands/apply_access_profiles.py
"""
Apply the agreed access profiles (panel/access_profiles.py).

---

Aplica los perfiles de acceso acordados (S163, panel/access_profiles.py).

--grants  crea los perfiles de permisos (grupos de usuarios), con sus
          puestos por defecto, sus personas y sus permisos, y los
          accesos propios. No cambia el puesto de nadie.
--people  hace superadministrador a Alejandro y desactiva el usuario
          de pruebas.
Sin --apply solo dice lo que haría. Escribe en pantalla y en
--log-file a la vez.
"""
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ivr_config.models import CompanyUser
from new_ui.catalog import PANEL_KEY, all_view_keys
from new_ui.models import UiViewGrant
from new_ui.permissions import set_grant
from panel import access_profiles as profiles


class Command(BaseCommand):
    """Apply the access profiles. --- Aplica los perfiles de acceso."""

    help = "Aplica los perfiles de acceso acordados (S163)."

    def add_arguments(self, parser):
        parser.add_argument("--grants", action="store_true")
        parser.add_argument("--people", action="store_true")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", default="")

    def _log(self, text):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), text)
        print(line, flush=True)
        if self.log:
            self.log.write(line + "\n")
            self.log.flush()

    def handle(self, *args, **options):
        self.log = (open(options["log_file"], "a", encoding="utf-8")
                    if options["log_file"] else None)
        if not (options["grants"] or options["people"]):
            raise CommandError("Indica --grants y/o --people.")
        apply = options["apply"]
        self._log("Modo: %s" % ("APLICAR" if apply else "solo mirar"))
        owner = CompanyUser.objects.select_related(
            "company", "user").get(pk=1)
        company = owner.company
        valid = {key for key, _l, _d in all_view_keys()}
        with transaction.atomic():
            if options["grants"]:
                self._grants(company, owner, valid, apply)
            if options["people"]:
                self._people(company, apply)
            if not apply:
                transaction.set_rollback(True)
        self._log("Fin.")

    def _user(self, company, pk, username):
        found = CompanyUser.objects.select_related("user").filter(
            company=company, user__username=username)
        if pk is not None:
            found = found.filter(pk=pk)
        cu = found.first()
        if cu is None:
            self._log("  !! %s (pk %s) no coincide: se salta" % (
                username, pk))
            return None
        return cu

    def _set(self, company, owner, valid, key, level, apply, label,
             **subject):
        if key not in valid:
            self._log("  !! clave desconocida %s: se salta" % key)
            return
        current = UiViewGrant.objects.filter(
            company=company, view_key=key,
            role="",
            company_user=subject.get("company_user"),
            user_group=subject.get("user_group")).first()
        if current and current.level == level:
            return
        self._log("  %s · %s: %s -> %s" % (
            label, key, current.level if current else "(nada)", level))
        if apply:
            set_grant(company, key, level, owner, **subject)

    def _grants(self, company, owner, valid, apply):
        from new_ui.models import UiUserGroup

        for name, profile in profiles.PROFILES.items():
            self._log("== Perfil %s" % name)
            group = UiUserGroup.objects.filter(
                company=company, name=name).first()
            if group is None:
                self._log("  se crea el perfil")
                group = UiUserGroup.objects.create(
                    company=company, name=name, created_by=owner)
            if group.default_roles != profile["default_roles"]:
                self._log("  puestos por defecto: %s -> %s" % (
                    group.default_roles, profile["default_roles"]))
                group.default_roles = profile["default_roles"]
                group.save(update_fields=["default_roles"])
            for pk, username in profile["members"]:
                cu = self._user(company, pk, username)
                if cu and not group.members.filter(pk=cu.pk).exists():
                    self._log("  entra %s (puesto %s)" % (username, cu.role))
                    group.members.add(cu)
            for slug, level in profile["areas"].items():
                key = PANEL_KEY if slug == "*" else "%s.%s" % (
                    PANEL_KEY, slug)
                self._set(company, owner, valid, key, level, apply,
                          name, user_group=group)
            for key, level in profile["new_ui"].items():
                self._set(company, owner, valid, key, level, apply,
                          name, user_group=group)
        self._log("== Accesos propios")
        for (pk, username), keys in profiles.USER_GRANTS.items():
            cu = self._user(company, pk, username)
            for key, level in (keys.items() if cu else ()):
                self._set(company, owner, valid, key, level, apply,
                          username, company_user=cu)

    def _people(self, company, apply):
        self._log("== Superadministrador")
        for pk, username in profiles.SUPERADMINS:
            cu = self._user(company, pk, username)
            if cu is None:
                continue
            user = cu.user
            self._log("  %s: superusuario %s -> True, staff %s -> False" % (
                username, user.is_superuser, user.is_staff))
            if apply:
                user.is_superuser = True
                user.is_staff = False
                user.save(update_fields=["is_superuser", "is_staff"])
        self._log("== Desactivar")
        for pk, username in profiles.DEACTIVATE:
            cu = self._user(company, pk, username)
            if cu is None:
                continue
            self._log("  %s: activo %s -> False" % (username, cu.is_active))
            if apply:
                cu.is_active = False
                cu.save(update_fields=["is_active"])
                cu.user.is_active = False
                cu.user.save(update_fields=["is_active"])
