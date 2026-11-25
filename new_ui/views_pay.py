# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_pay.py
"""
Hours and pay ("Horas y pagos") in the new interface.

---

Horas y pagos (S163, 23/11): en Empresa, qué se paga de las horas y los
periodos liquidados; en Personal, la lista de trabajadores con sus
horas e importe del periodo, sus precios y de dónde salen sus horas, y
en la ficha de cada uno el cálculo día a día con la bolsa de horas. El
cálculo está en hr_calendar/pay.py.
"""
import datetime
from decimal import Decimal, InvalidOperation

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from document_explorer.models import PersonIdentity
from hr_calendar import pay
from hr_calendar.models import PayLine, PayPeriod, PayWorker
from new_ui.filters import period_range
from new_ui.lists import person_name
from new_ui.mixins import SuperuserRequiredMixin


def _ok(message):
    return JsonResponse({"ok": True, "message": message})


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


def _company(request):
    return request.user.company_user.company


def _hours(text):
    """Horas escritas (8, 8,5 u 8:30) en minutos; None si vacío."""
    text = (text or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        if ":" in text:
            hours, minutes = text.split(":", 1)
            return int(hours or 0) * 60 + int(minutes or 0)
        return int(round(float(text) * 60))
    except ValueError:
        raise pay.PayError("Escribe las horas, por ejemplo 8 o 7:30.")


def _price(text):
    text = (text or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise pay.PayError("Escribe los precios con números (12,50).")
    if value < 0:
        raise pay.PayError("Un precio no puede ser negativo.")
    return str(value)


def _date(text):
    try:
        return datetime.date.fromisoformat(text or "")
    except ValueError:
        return None


def _as_date(value):
    if value is None or isinstance(value, datetime.date):
        return value
    return _date(str(value)[:10])


def pay_period(params):
    """
    The period of the filter; without one, the pay period in progress.

    ---

    El periodo del filtro; sin periodo, el periodo de pago en curso (del
    21 al 20, el de los periodos de trabajo).
    """
    from new_ui.filters import pay_period_range

    start, end = period_range(params)
    if start is None and end is None:
        return pay_period_range()
    if start is None:
        start = pay_period_range(end)[0]
    if end is None:
        end = pay_period_range(start)[1]
    return start, end


def _minutes_label(minutes):
    if minutes is None:
        return ""
    return "%d:%02d" % divmod(int(minutes), 60)


def _people(company, ids):
    return list(PersonIdentity.objects.filter(
        company=company, pk__in=ids).select_related("company_user"))


def _marked_users(request):
    ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
    people = _people(_company(request), ids)
    if not people:
        raise pay.PayError("Marca primero a los trabajadores.")
    users = [p.company_user for p in people if p.company_user_id]
    if not users:
        raise pay.PayError("Ninguno de los marcados tiene cuenta del "
                           "panel: no fichan ni hacen partes.")
    return users, len(people) - len(users)


def pay_context(section, company):
    """Contexto de las acciones de Horas y pagos (Personal)."""
    if section != "per":
        return {}
    from new_ui.filters import pay_period_range

    return {
        "pay_classes": pay.hour_classes(company),
        "pay_sources": PayWorker.Source.choices,
        "pay_previous": pay_period_range(previous=True),
        "pay_current": pay_period_range(),
    }


# ------------------------------------------------------------- Empresa
def render_settings(request):
    """
    Empresa › Horas y pagos › «Qué se paga».

    ---

    Por cada clase de hora, qué se paga (botones, sin desplegables); el
    tope mensual de horas extra y la jornada de los partes.
    """
    company = _company(request)
    settings = pay.settings_of(company)
    classes = [
        {"key": key, "label": label, "mode": pay.mode_of(settings, key)}
        for key, label in pay.hour_classes(company)]
    return render(request, "new_ui/_pay_settings.html", {
        "classes": classes,
        "modes": pay.MODE_LABELS,
        "cap": _minutes_label(settings.monthly_cap_minutes),
        "parte_day": _minutes_label(settings.parte_day_minutes),
    })


class PaySettingsSaveView(SuperuserRequiredMixin, View):
    """POST: guarda qué se paga, el tope mensual y la jornada de partes."""

    def post(self, request):
        company = _company(request)
        try:
            cap = _hours(request.POST.get("cap"))
            parte_day = _hours(request.POST.get("parte_day"))
        except pay.PayError as exc:
            return _error(str(exc))
        if parte_day is not None and parte_day <= 0:
            return _error("La jornada de los partes tiene que ser mayor "
                          "que cero.")
        modes = {key: request.POST.get("mode_" + key, pay.NONE)
                 for key, _label in pay.hour_classes(company)}
        pay.save_settings(company, modes, cap, parte_day)
        return _ok("Guardado: los cálculos ya salen con esto (los "
                   "periodos liquidados no cambian).")


class PayPeriodActionView(SuperuserRequiredMixin, View):
    """
    POST: undo the marked paid periods (their days can be paid again).

    ---

    POST: deshace los periodos liquidados marcados (sus líneas se
    borran y esos días se vuelven a calcular).
    """

    def post(self, request):
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        periods = list(PayPeriod.objects.filter(
            company=_company(request), pk__in=ids))
        if not periods:
            return _error("Marca primero los periodos.")
        for period in periods:
            pay.undo(period)
        return _ok("%d liquidación(es) deshecha(s): sus periodos de trabajo "
                   "se reabren y esos días se vuelven a calcular."
                   % len(periods))


class PayPeriodSheetView(SuperuserRequiredMixin, View):
    """
    GET: one paid period in the viewer, with its lines per worker.

    ---

    S163 (25/11): una liquidación en el visor: periodo, quién y cuándo,
    el detalle por trabajador (cada clase de hora) con el total, y
    descargar en Excel o deshacerla (5 s).
    """

    def get(self, request, pk):
        from django.http import Http404

        period = PayPeriod.objects.filter(
            company=_company(request), pk=pk).select_related(
            "closed_by__person_identity", "closed_by__user").first()
        if period is None:
            raise Http404
        workers, order, total = {}, [], Decimal("0")
        for line in period.lines.exclude(key="nada").select_related(
                "company_user__person_identity", "company_user__user") \
                .order_by("company_user_id", "key"):
            cu = line.company_user
            if cu.pk not in workers:
                person = getattr(cu, "person_identity", None)
                workers[cu.pk] = {"name": person_name(person) if person
                                  else str(cu), "lines": [],
                                  "amount": Decimal("0")}
                order.append(cu.pk)
            workers[cu.pk]["lines"].append(line)
            workers[cu.pk]["amount"] += line.amount
            total += line.amount
        closer = period.closed_by
        person = getattr(closer, "person_identity", None) if closer else None
        label = "%s – %s" % (period.date_from.strftime("%d/%m/%Y"),
                             period.date_to.strftime("%d/%m/%Y"))
        return render(request, "new_ui/_pay_period.html", {
            "period": period,
            "label": label,
            "closed_by": (person_name(person) if person
                          else (str(closer) if closer else "")),
            "workers": sorted((workers[k] for k in order),
                              key=lambda w: w["name"]),
            "total": total,
        })


class PayPeriodDownloadView(SuperuserRequiredMixin, View):
    """
    POST: the lines of the marked paid periods as an Excel file.

    ---

    POST: las líneas de las liquidaciones marcadas en un Excel (una fila
    por trabajador y clase de hora), para pasarlo a nóminas.
    """

    def post(self, request):
        from openpyxl import Workbook

        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        lines = PayLine.objects.filter(
            period__company=_company(request), period__pk__in=ids,
        ).exclude(key="nada").select_related(
            "period", "company_user__person_identity").order_by(
            "period__date_from", "company_user_id", "key")
        book = Workbook()
        sheet = book.active
        sheet.title = "Horas y pagos"
        sheet.append(["Desde", "Hasta", "Trabajador", "DNI", "Clase de hora",
                      "Horas", "Precio", "Horas en festivo",
                      "Precio festivo", "Importe"])
        for line in lines:
            person = getattr(line.company_user, "person_identity", None)
            name = (person_name(person) if person
                    else str(line.company_user))
            sheet.append([
                line.period.date_from, line.period.date_to, name,
                person.dni if person else "", line.label, float(line.hours),
                float(line.price), float(line.holiday_hours),
                float(line.holiday_price), float(line.amount)])
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument."
                         "spreadsheetml.sheet")
        name = "horas_y_pagos.xlsx"
        response["Content-Disposition"] = (
            'attachment; filename="%s"; filename*=UTF-8\'\'%s' % (name, name))
        book.save(response)
        return response


# ------------------------------------------------------------ Personal
def prepare_people(people):
    """
    Each worker's result of the period (ListDef.prepare).

    ---

    A cada trabajador de la lista, su cálculo del periodo (el que dejó
    la anotación del periodo en la fila) o None sin cuenta del panel.
    """
    groups = {}
    for person in people:
        person.nui_pay = None
        if not person.company_user_id:
            continue
        # En MySQL la fecha anotada llega como texto.
        key = (person.company_user.company_id,
               _as_date(getattr(person, "nui_pay_from", None)),
               _as_date(getattr(person, "nui_pay_to", None)))
        groups.setdefault(key, []).append(person)
    for (_company_id, start, end), members in groups.items():
        if start is None or end is None:
            continue
        company = members[0].company_user.company
        results = pay.compute(company, [p.company_user for p in members],
                              start, end)
        for person in members:
            person.nui_pay = results.get(person.company_user_id)


class PayPricesView(SuperuserRequiredMixin, View):
    """POST: precios por clase de hora de los marcados (solo los escritos)."""

    def post(self, request):
        company = _company(request)
        try:
            users, without = _marked_users(request)
            prices = {}
            for key, _label in pay.hour_classes(company):
                normal = _price(request.POST.get("price_" + key))
                holiday = _price(request.POST.get("holiday_" + key))
                if normal is None and holiday is None:
                    continue
                prices[key] = [normal, holiday]
        except pay.PayError as exc:
            return _error(str(exc))
        if not prices:
            return _error("Escribe al menos un precio.")
        # Lo no escrito de un par se deja como estaba.
        for cu in users:
            worker, _created = PayWorker.objects.get_or_create(
                company_user=cu)
            current = dict(worker.prices or {})
            for key, (normal, holiday) in prices.items():
                old = list(current.get(key) or [None, None]) + [None, None]
                current[key] = [normal if normal is not None else old[0],
                                holiday if holiday is not None else old[1]]
            worker.prices = current
            worker.save(update_fields=["prices", "updated_at"])
        message = "Precios puestos a %d trabajador(es)." % len(users)
        if without:
            message += " %d sin cuenta del panel, sin cambios." % without
        return _ok(message)


class PaySourceView(SuperuserRequiredMixin, View):
    """POST: de dónde salen las horas de los marcados."""

    def post(self, request):
        try:
            users, without = _marked_users(request)
            pay.set_source(users, request.POST.get("source", ""))
        except pay.PayError as exc:
            return _error(str(exc))
        message = "Cambiado a %d trabajador(es)." % len(users)
        if without:
            message += " %d sin cuenta del panel, sin cambios." % without
        return _ok(message)


class PayLiquidateView(SuperuserRequiredMixin, View):
    """POST: liquida el periodo de los marcados (queda bloqueado)."""

    def post(self, request):
        company = _company(request)
        from new_ui.filters import pay_period_range

        date_from, date_to = pay_period_range(
            previous=request.POST.get("which") != "actual")
        try:
            users, without = _marked_users(request)
            period, _count = pay.liquidate(
                company, users, date_from, date_to,
                request.user.company_user)
        except pay.PayError as exc:
            return _error(str(exc))
        total = sum((line.amount for line in period.lines.all()),
                    Decimal("0"))
        message = ("Liquidado del %s al %s: %d trabajador(es), %s €. "
                   "Está en Empresa › Horas y pagos › Liquidaciones." % (
                       period.date_from.strftime("%d/%m/%Y"),
                       period.date_to.strftime("%d/%m/%Y"), len(users),
                       ("%.2f" % total).replace(".", ",")))
        if without:
            message += " %d sin cuenta del panel, fuera." % without
        return _ok(message)


def render_worker(request, person):
    """
    The «Horas y pagos» tab of the open worker: day by day and the bag.

    ---

    La pestaña de la ficha: el cálculo día a día del periodo del filtro
    (de dónde salen las horas, qué se paga y a qué precio), sus precios
    y la bolsa de horas (la misma que en Fichaje › Calendario).
    """
    from new_ui.views_clock import bag_context

    company = _company(request)
    start, end = pay_period(request.GET)
    classes = pay.hour_classes(company)
    labels = dict(classes)
    result = None
    if person.company_user_id:
        result = pay.compute(company, [person.company_user], start,
                             end).get(person.company_user_id)
    days = []
    lines = []
    if result is not None:
        for row in reversed(result.days):
            days.append({
                "day": row["day"], "holiday": row["holiday"],
                "source": "Parte" if row["source"] == pay.PARTE
                else "Fichaje",
                "hours": [(labels.get(k, k), _minutes_label(s // 60))
                          for k, s in row["by_key"].items()],
                "paid": [(labels.get(k, k), _minutes_label(s // 60))
                         for k, s in row["paid"].items()],
                "to_bag": _minutes_label(row["to_bag"] // 60)
                if row["to_bag"] else "",
            })
        for key, label in classes:
            if key not in result.paid:
                continue
            lines.append({
                "label": label, "hours": result.hours(key),
                "price": result.price(key),
                "holiday_hours": result.hours(key, True),
                "holiday_price": result.price(key, True),
                "amount": result.amount(key)})
    prices = (result.prices if result is not None else {}) or {}
    return render(request, "new_ui/_pay_worker.html", {
        "person": person,
        "has_account": person.company_user_id is not None,
        "date_from": start, "date_to": end,
        "result": result,
        "days": days,
        "lines": lines,
        "liquidated": [(a, b) for a, b, _p in
                       (result.liquidated if result else [])],
        "prices": [(label, (prices.get(key) or ["", ""])[0] or "",
                    ((prices.get(key) or ["", ""]) + [""])[1] or "")
                   for key, label in classes],
        "bag": bag_context(person),
        "today": timezone.localdate(),
    })
