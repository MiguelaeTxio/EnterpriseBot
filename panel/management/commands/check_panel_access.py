# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/management/commands/check_panel_access.py
"""
Check what some users get when they open some panel pages.

---

S163 (26/11): comprueba, como si entrara cada persona, qué le devuelve
el panel en unas páginas (código y a dónde le manda). Cada petición va
dentro de una transacción que se deshace: no deja rastro (ni historial
de «Volver» ni filtros guardados). Escribe en pantalla y en --log-file.
"""
from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.test import Client
from django.urls import NoReverseMatch, reverse

PAGES = [
    "panel:dashboard", "panel:operator_dashboard",
    "panel:documentation_hub", "panel:fleet_list",
    "workorder_spare_parts:warehouse_list",
    "workorder_spare_parts:catalog_list",
    "spare_parts:delivery_note_upload", "hr_calendar:calendar",
    "hr_calendar:vacation_period_list", "panel:work_order_admin_history",
    "analytics:analytics_lab", "panel:user_list", "panel:section_list",
    "budgets:wizard", "crane_albaranes:hub", "panel:payslip_page",
    "document_explorer:explorer", "panel:breakdown_ticket_list",
    "new_ui:home", "new_ui:home?s=per", "new_ui:home?s=doc",
    "new_ui:home?s=cdg", "new_ui:home?s=permisos",
    "new_ui:list?s=doc&t=nominas", "new_ui:list?s=doc&t=seguros",
    "new_ui:list?s=per&t=fichajes",
]
USERS = [
    "alejandro_sergio", "jeronimo", "yolanda.bandera", "Carolina",
    "MARIA", "carlos.nunez", "Alberto Álvarez", "Pepe.Alvarez",
    "paloma", "juan.vazquez",
]


class Command(BaseCommand):
    """Check panel access per user. --- Comprueba accesos."""

    help = "Comprueba qué ve cada persona en unas páginas del panel."

    def add_arguments(self, parser):
        parser.add_argument("--users", default="")
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
        names = ([n.strip() for n in options["users"].split(",") if n.strip()]
                 or USERS)
        host = next((h for h in settings.ALLOWED_HOSTS
                     if h and not h.startswith(".") and h != "*"),
                    "localhost")
        extra = [n for n in ("CRANE_OPERATOR", "WORKSHOP")]
        users = list(User.objects.filter(username__in=names))
        for role in extra:
            sample = User.objects.filter(
                company_user__role=role, company_user__is_active=True,
                is_superuser=False).first()
            if sample:
                users.append(sample)
        for user in users:
            cu = getattr(user, "company_user", None)
            self._log("== %s (%s)" % (
                user.username, cu.get_role_display() if cu else "-"))
            for name in PAGES:
                name, _sep, query = name.partition("?")
                try:
                    page = reverse(name) + ("?" + query if query else "")
                except NoReverseMatch:
                    self._log("  %-45s (no existe)" % name)
                    continue
                with transaction.atomic():
                    client = Client(HTTP_HOST=host)
                    client.force_login(user)
                    try:
                        response = client.get(page, secure=True)
                        where = response.get("Location", "")
                        self._log("  %-45s %s %s" % (
                            page, response.status_code, where))
                    except Exception as exc:  # noqa: BLE001
                        self._log("  %-45s ERROR %s" % (page, exc))
                    transaction.set_rollback(True)
        self._log("Fin.")
