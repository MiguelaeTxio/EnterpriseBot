# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_personal_access.py
"""
"Dar acceso al fichaje" in the Personal tab (H24, S141).

---

"Dar acceso al fichaje" en la pestaña Personal (H24, S141): el
supervisor crea las cuentas de los marcados (panel/personal_access.py)
viendo el usuario propuesto y los que ya existen, y elige sección,
base y puesto. Mismos roles que crear usuarios (SupervisorAccessMixin).
"""
import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from document_explorer.models import PersonIdentity
from ivr_config.models import CompanyUser, Section
from panel.mixins import SupervisorAccessMixin
from panel.personal_access import AccessError, create_access, propose


def _people(company, ids):
    from django.db.models import Q

    wanted = [int(pk) for pk in ids if str(pk).isdigit()]
    return list(PersonIdentity.objects.filter(
        Q(company=company) | Q(company__isnull=True), pk__in=wanted,
    ).select_related("company_user__user").order_by(
        "first_surname", "second_surname", "given_name",
    ))


class PersonalAccessPreviewView(SupervisorAccessMixin, View):
    """
    GET ?ids=1,2,3: the access modal body for the marked workers.
    ---
    GET ?ids=1,2,3: el cuerpo del modal de alta en el panel de los
    marcados: usuario propuesto (editable), usuarios parecidos que ya
    existen, sección (la vigente), base y puesto.
    """

    def get(self, request):
        from budgets.models import Base
        from hr_calendar.clock_settings import current_sections

        company = request.user.company_user.company
        people = _people(company, request.GET.get("ids", "").split(","))
        sections = current_sections([p.pk for p in people])
        rows = propose(people)
        worker_roles = [
            (value, label) for value, label in CompanyUser.ROLE_CHOICES
            if value in CompanyUser.WORKER_ROLES
        ]
        for row in rows:
            section = sections.get(row["person"].pk)
            row["section"] = section
            account = row["person"].company_user
            row["base_id"] = account.base_id if account else None
            default_role = section.default_role if section else ""
            row["role"] = (
                account.role if account and account.role
                in CompanyUser.WORKER_ROLES else default_role
                if default_role in CompanyUser.WORKER_ROLES
                else CompanyUser.ROLE_DRIVER
            )
        return render(request, "panel/documentation_h30/_access_rows.html", {
            "rows": rows,
            "sections": Section.objects.filter(
                company=company, is_active=True,
            ).order_by("name"),
            "bases": Base.objects.filter(company=company).order_by("name"),
            "worker_roles": worker_roles,
        })


class PersonalAccessCreateView(SupervisorAccessMixin, View):
    """
    POST (JSON {"rows": [{person, username, section, base, role}]}).
    ---
    POST: crea las cuentas. Devuelve, por trabajador, el usuario creado
    o el motivo por el que no se ha podido; un fallo no para a los demás.
    """

    def post(self, request):
        from budgets.models import Base

        by = request.user.company_user
        company = by.company
        try:
            rows = json.loads(request.body.decode("utf-8")).get("rows", [])
        except (ValueError, AttributeError):
            return JsonResponse({"ok": False, "error": "Datos no válidos."},
                                status=400)
        people = {
            p.pk: p for p in _people(
                company, [r.get("person") for r in rows],
            )
        }
        created, errors = [], []
        for row in rows:
            person = people.get(int(row.get("person") or 0))
            if person is None:
                continue
            label = ("%s %s" % (person.given_name,
                                person.first_surname)).strip()
            section = Section.objects.filter(
                company=company, pk=row.get("section") or 0,
            ).first()
            base = Base.objects.filter(
                company=company, pk=row.get("base") or 0,
            ).first()
            try:
                account = create_access(
                    person, row.get("username"), section, base,
                    row.get("role"), by,
                )
            except AccessError as exc:
                errors.append("%s: %s" % (label, exc))
                continue
            created.append({"name": label,
                            "username": account.user.username})
        return JsonResponse({"ok": bool(created), "created": created,
                             "errors": errors})


class PersonalAccessResendView(SupervisorAccessMixin, View):
    """
    POST person_ids: send the clock-in onboarding again to the marked.
    ---
    POST person_ids: "Reenviar el alta" (H24, S144), desde Personal y
    desde Fichajes. A cada marcado le vuelve a enviar por WhatsApp la
    circular "Alta en el fichaje" y, si sale, le pone otra vez la
    contraseña de las cuatro últimas cifras del DNI y le quita los
    dispositivos de confianza (panel/personal_access.py,
    resend_onboarding). Devuelve los enviados y, por persona, el motivo
    de los que no.
    """

    def post(self, request):
        from panel.personal_access import resend_onboarding

        company = request.user.company_user.company
        people = _people(company, request.POST.getlist("person_ids"))
        if not people:
            return JsonResponse(
                {"ok": False, "error": "Marca antes a alguien."},
                status=400)
        sent, errors = [], []
        for person in people:
            label = ("%s %s" % (person.given_name,
                                person.first_surname)).strip()
            ok, reason = resend_onboarding(person)
            if ok:
                sent.append(label)
            else:
                errors.append("%s: %s" % (label, reason))
        return JsonResponse({"ok": bool(sent), "sent": len(sent),
                             "errors": errors})
