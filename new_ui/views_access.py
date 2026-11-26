# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_access.py
"""
Panel access, base, employer and contract review, new interface (S163).

---

Personal › Acciones en la nueva interfaz (S163), copiado de la antigua
(panel/views_personal_access.py, panel/views_personal_section.py y
PersonalContractReviewedView):
- Dar acceso al panel a los marcados (usuario propuesto, sección, base
  y rol; enlaza el usuario que ya tenga sin enlazar) y reenviar el
  alta en el fichaje.
- Base del usuario del panel y empresa de los marcados.
- Contrato revisado de la persona abierta (correcto, deshacer, anular).
La lógica de cuentas está copiada en new_ui/personal_access.py.
"""
import json
from datetime import date

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from document_explorer.models import PersonIdentity
from ivr_config.models import CompanyUser, Section
from new_ui.docs_core import COMPANY_FILTER_CHOICES
from new_ui.mixins import SuperuserRequiredMixin
from new_ui.personal_access import (
    AccessError, create_access, link_account, pending_account, propose,
    unlinked_account,
)


def _ok(message, **extra):
    return JsonResponse({"ok": True, "message": message, **extra})


def _error(message, status=400):
    return JsonResponse({"ok": False, "message": message}, status=status)


def _people(company, ids):
    wanted = [int(pk) for pk in ids if str(pk).isdigit()]
    return list(PersonIdentity.objects.filter(
        Q(company=company) | Q(company__isnull=True), pk__in=wanted,
    ).select_related("company_user__user").order_by(
        "first_surname", "second_surname", "given_name"))


def _label(person):
    return ("%s %s" % (person.given_name, person.first_surname)).strip()


def access_context(section, company):
    """Bases y empresas para las acciones de Personal."""
    if section != "per":
        return {}
    from budgets.models import Base

    return {
        "nui_bases": list(Base.objects.filter(
            company=company).order_by("name")),
        "nui_employers": [(slug, label) for slug, label, _raws
                          in COMPANY_FILTER_CHOICES
                          if slug != "sin_empresa"],
    }


class AccessPreviewView(SuperuserRequiredMixin, View):
    """
    GET ?ids=1,2,3: the access rows of the marked workers.

    ---

    GET: una fila por marcado con el usuario propuesto (editable), los
    usuarios parecidos que ya existen, su sección, base y rol.
    """

    def get(self, request):
        from budgets.models import Base
        from hr_calendar.clock_settings import current_sections

        company = request.user.company_user.company
        people = _people(company, request.GET.get("ids", "").split(","))
        sections = current_sections([p.pk for p in people])
        rows = propose(people)
        for row in rows:
            section = sections.get(row["person"].pk)
            row["section"] = section
            account = (row["person"].company_user
                       or pending_account(row["person"]))
            row["base"] = account.base if account else None
            row["keep_role"] = ""
            default_role = section.default_role if section else ""
            row["role"] = (account.role if account and account.role
                           else default_role or CompanyUser.ROLE_DRIVER)
        return render(request, "new_ui/_access_rows.html", {
            "rows": rows,
            "sections": Section.objects.filter(
                company=company).order_by("name"),
            "bases": Base.objects.filter(company=company).order_by("name"),
            "worker_roles": list(CompanyUser.ACTIVE_ROLE_CHOICES),
        })


class AccessCreateView(SuperuserRequiredMixin, View):
    """
    POST JSON {"rows": [...]}: create or link the accounts.

    ---

    POST: crea las cuentas (contraseña: las cuatro últimas cifras del
    DNI) o enlaza la que ya tenga sin enlazar; un fallo no para a los
    demás. El aviso dice qué usuario tiene cada uno.
    """

    def post(self, request):
        from budgets.models import Base

        by = request.user.company_user
        company = by.company
        try:
            rows = json.loads(request.body.decode("utf-8")).get("rows", [])
        except (ValueError, AttributeError):
            return _error("Datos no válidos.")
        people = {p.pk: p for p in _people(
            company, [r.get("person") for r in rows])}
        created, errors = [], []
        for row in rows:
            person = people.get(int(row.get("person") or 0))
            if person is None:
                continue
            label = _label(person)
            if row.get("link"):
                account = unlinked_account(person)
                if account is None or str(account.pk) != str(row["link"]):
                    errors.append("%s: ya no se encuentra su usuario" % label)
                    continue
                link_account(person, account)
                created.append("%s → %s (enlazado, su rol no cambia)" % (
                    label, account.user.username))
                continue
            section = Section.objects.filter(
                company=company, pk=row.get("section") or 0).first()
            base = Base.objects.filter(
                company=company, pk=row.get("base") or 0).first()
            try:
                account = create_access(person, row.get("username"),
                                        section, base, row.get("role"), by)
            except AccessError as exc:
                errors.append("%s: %s" % (label, exc))
                continue
            created.append("%s → %s" % (label, account.user.username))
        message = ""
        if created:
            message = "Usuarios creados o enlazados: %s." % "; ".join(created)
        if errors:
            message += " No creados: %s." % "; ".join(errors)
        if not created:
            return _error(message.strip() or "No se ha creado ninguno.")
        return _ok(message.strip())


class AccessResendView(SuperuserRequiredMixin, View):
    """
    POST `selected`: send the clock-in onboarding again.

    ---

    POST: «Reenviar el alta» a los marcados: la circular «Alta en el
    fichaje» por WhatsApp y, si sale, otra vez la contraseña de las
    cuatro últimas cifras del DNI (salvo `keep_password`) y fuera los
    dispositivos de confianza.
    """

    def post(self, request):
        from new_ui.personal_access import resend_onboarding

        company = request.user.company_user.company
        people = _people(company, request.POST.getlist("selected"))
        if not people:
            return _error("Marca antes a alguien.")
        sent, errors = [], []
        for person in people:
            ok, reason = resend_onboarding(
                person,
                keep_password=request.POST.get("keep_password") == "1")
            if ok:
                sent.append(_label(person))
            else:
                errors.append("%s: %s" % (_label(person), reason))
        message = "Alta reenviada a %d." % len(sent)
        if errors:
            message += " No enviada: %s." % "; ".join(errors)
        if not sent:
            return _error(message)
        return _ok(message)


class MassBaseView(SuperuserRequiredMixin, View):
    """
    POST: base of the marked workers' panel accounts (empty: none).

    ---

    POST: pone la base (o la quita) al usuario del panel de los
    marcados; quien no tiene usuario se salta y se dice.
    """

    def post(self, request):
        from budgets.models import Base

        company = request.user.company_user.company
        people = _people(company, request.POST.getlist("selected"))
        if not people:
            return _error("Marca algún trabajador.")
        raw = request.POST.get("base_id", "")
        base = None
        if raw:
            base = Base.objects.filter(
                pk=raw if raw.isdigit() else 0, company=company).first()
            if base is None:
                return _error("No existe esa base.")
        accounts = [p.company_user_id for p in people if p.company_user_id]
        without = [_label(p) for p in people if not p.company_user_id]
        count = CompanyUser.objects.filter(
            pk__in=accounts, company=company).update(base=base)
        message = ("Base %s puesta a %d trabajador(es)." % (base.name, count)
                   if base else "Base quitada a %d trabajador(es)." % count)
        if without:
            message += " Sin usuario del panel (no se les pone): %s." % (
                ", ".join(without[:10])
                + (" y %d más" % (len(without) - 10)
                   if len(without) > 10 else ""))
        return _ok(message)


class MassEmployerView(SuperuserRequiredMixin, View):
    """
    POST: employer company of the marked workers.

    ---

    POST: pone a los marcados esa empresa (texto canónico); si están
    activos, su documentación pasa a ACTIVOS/{EMPRESA}/ (solo índice) y
    también en local.
    """

    def post(self, request):
        from document_explorer import local_download_service
        from document_explorer.person_folder_service import (
            relocate_if_needed,
        )

        choices = {slug: (label, raws[0])
                   for slug, label, raws in COMPANY_FILTER_CHOICES}
        slug = request.POST.get("employer", "")
        if slug not in choices:
            return _error("Elige la empresa.")
        label, text = choices[slug]
        company = request.user.company_user.company
        people = _people(company, request.POST.getlist("selected"))
        if not people:
            return _error("Marca algún trabajador.")
        changed = moved = 0
        for person in people:
            if (person.employer_company or "") == text:
                continue
            person.employer_company = text
            person.save(update_fields=["employer_company", "updated_at"])
            changed += 1
            if person.is_active_employee:
                previous_local = local_download_service.snapshot_paths(person)
                relocated, _folder, _count = relocate_if_needed(person)
                moved += int(relocated)
                if relocated:
                    local_download_service.create_for_person(
                        person, request.user.company_user, previous_local)
        message = "%s para %d trabajador(es)" % (label, changed)
        if changed < len(people):
            message += " (%d ya la tenían)" % (len(people) - changed)
        if moved:
            message += "; documentación de %d trasladada a su carpeta" % moved
        return _ok(message + ".")


class ContractReviewView(SuperuserRequiredMixin, View):
    """
    POST `action`: review / restore / clear the current contract review.

    ---

    POST: revisión del contrato vigente de una persona: «Correcto» (el
    aviso de antigüedad cuenta desde hoy; devuelve la revisión anterior
    para deshacer), «Deshacer» (deja la anterior) o «Anular revisión».
    """

    def post(self, request, pk):
        person = PersonIdentity.objects.filter(pk=pk).first()
        if person is None:
            return _error("La persona no existe.", 404)
        action = request.POST.get("action", "review")
        previous = {
            "previous_date": (person.contract_reviewed_at.isoformat()
                              if person.contract_reviewed_at else ""),
            "previous_by": person.contract_reviewed_by_id or "",
        }
        if action == "review":
            person.contract_reviewed_at = date.today()
            person.contract_reviewed_by = request.user.company_user
            message = "Contrato revisado hoy."
        elif action == "restore":
            raw_date = request.POST.get("previous_date", "")
            raw_by = request.POST.get("previous_by", "")
            try:
                person.contract_reviewed_at = (
                    date.fromisoformat(raw_date) if raw_date else None)
            except ValueError:
                return _error("Fecha anterior no válida.")
            person.contract_reviewed_by = (
                CompanyUser.objects.filter(
                    pk=int(raw_by),
                    company=request.user.company_user.company).first()
                if str(raw_by).isdigit() else None)
            message = "Revisión anterior restaurada."
        elif action == "clear":
            person.contract_reviewed_at = None
            person.contract_reviewed_by = None
            message = "Revisión anulada: el aviso vuelve a contar desde " \
                      "la fecha del contrato."
        else:
            return _error("Acción no válida.")
        person.save(update_fields=[
            "contract_reviewed_at", "contract_reviewed_by", "updated_at"])
        return _ok(message, **previous)
