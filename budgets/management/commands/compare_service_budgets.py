# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/management/commands/compare_service_budgets.py
"""
Compare the estimated budget of the Services tab with the manual one.

---

Compara, servicio a servicio, el presupuesto estimado de la pestaña
Servicios con el que daría el presupuesto manual (el asistente de
presupuestos, ya comprobado a mano), con los mismos datos (H37, S143).
Miguel Ángel: "tenemos que comprobar ese tipo de presupuesto con el
valor que nos sale para comprobar que cuadra".

Por cada servicio valorado, dos presupuestos con el mismo motor
(`services.calculate_budget`), la misma aseguradora, tipo de vehículo,
base, fecha y hora y conceptos de la tarifa de sus tareas:

- Valoración: tal cual la calcula la pestaña Servicios
  (`service_evaluation.estimate_budget`): km del circuito de la matriz
  de rutas, modo Manual, sin peajes, nocturno con el horario de la
  aseguradora o, si no tiene, el de la empresa.
- Manual: como lo guarda el asistente (`views.BudgetWizardView`) con el
  planificador de ruta: recogida y entrega geocodificadas, circuito
  base -> paradas -> base con `calculate_route_multileg`, km redondeados
  a la unidad, peajes de la ruta (modo API) y nocturno solo con el
  horario de la aseguradora (extremos incluidos).

Solo lectura: no guarda nada. Hace llamadas a Google (geocodificación y
rutas). Log propio en pantalla y en archivo a la vez (`--log-file`).
"""
import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from django.core.management.base import BaseCommand

ZERO = Decimal("0.00")


def _code(line):
    """
    Concept code of a line as text (some lines carry the concept).

    ---

    Código del concepto de una línea como texto (las de km llevan el
    propio concepto de la tarifa).
    """
    code = line.concept_code
    return str(getattr(code, "code", code) or "")


class Command(BaseCommand):
    """
    Side by side: estimated budget and manual budget of each service.

    ---

    Presupuesto estimado y presupuesto manual de cada servicio, línea a
    línea, con la diferencia y de dónde sale.
    """

    help = (
        "Compara el presupuesto estimado de la pestaña Servicios con el "
        "del presupuesto manual, con los mismos datos (H37, S143). No "
        "guarda nada."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--ids",
            default="",
            help="Solo estos servicios valorados (ids separados por comas).",
        )
        parser.add_argument(
            "--log-file",
            required=True,
            help="Ruta del log propio (pantalla y archivo a la vez).",
        )

    def _log(self, message):
        """
        Print and append one line to the log file, flushed.

        ---

        Escribe una línea en pantalla y en el log, con flush.
        """
        line = "[%s] %s" % (dt.datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def _plain(self, message):
        """
        Print and append one line without the time.

        ---

        Escribe una línea sin hora (tablas y resumen).
        """
        print(message, flush=True)
        self._log_handle.write(message + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._log_handle = handle
            ids = [
                int(part) for part in options["ids"].split(",")
                if part.strip().isdigit()
            ]
            self._run(ids)

    def _run(self, ids):
        """
        Compare every valued service (or the given ones).

        ---

        Compara cada servicio valorado (o los indicados).
        """
        from budgets.models import AssistanceTaskTime, ServiceEvaluation

        evaluations = ServiceEvaluation.objects.filter(
            status=ServiceEvaluation.STATUS_DONE,
        ).select_related(
            "company", "insurer", "vehicle_type", "base",
        ).order_by("pk")
        if ids:
            evaluations = evaluations.filter(pk__in=ids)
        evaluations = list(evaluations)
        self._log("Servicios valorados a comparar: %d." % len(evaluations))
        summary = []
        task_times = {}
        for number, evaluation in enumerate(evaluations, start=1):
            company = evaluation.company
            if company.pk not in task_times:
                task_times[company.pk] = AssistanceTaskTime.for_company(
                    company,
                )
            self._log("--- %d/%d · servicio %d (%s) ---" % (
                number, len(evaluations), evaluation.pk,
                evaluation.file_name,
            ))
            try:
                summary.append(
                    self._compare(evaluation, task_times[company.pk]),
                )
            except Exception as exc:  # noqa: BLE001 -- se sigue con otro
                self._log("ERROR en el servicio %d: %s: %s" % (
                    evaluation.pk, type(exc).__name__, exc,
                ))
                summary.append((evaluation.pk, None, None, "error"))
        self._plain("")
        self._plain("RESUMEN (sin IVA)")
        self._plain("%-9s %12s %12s %10s  %s" % (
            "Servicio", "Valoración", "Manual", "Diferencia", "Motivo",
        ))
        for pk, estimated, manual, reason in summary:
            diff = (
                manual - estimated
                if estimated is not None and manual is not None else None
            )
            self._plain("%-9s %12s %12s %10s  %s" % (
                pk, _eur(estimated), _eur(manual), _eur(diff), reason,
            ))

    def _compare(self, evaluation, task_times):
        """
        Both budgets of one service, logged; returns its summary row.

        ---

        Los dos presupuestos de un servicio, al log; devuelve su fila
        del resumen (pk, valoración, manual, motivos).
        """
        from budgets.service_evaluation import (
            _has_service_date,
            _service_moment,
            estimate_budget,
            restore_data,
        )
        from budgets.services import calculate_budget

        data = restore_data(evaluation.data)
        when = _service_moment(data, evaluation.created_at)
        self._log("Aseguradora: %s · tipo: %s · base: %s · %s%s" % (
            evaluation.insurer.name if evaluation.insurer else "—",
            evaluation.vehicle_type.name if evaluation.vehicle_type else "—",
            evaluation.base.name if evaluation.base else "—",
            when.strftime("%d/%m/%Y %H:%M"),
            "" if _has_service_date(data) else " (hora de subida)",
        ))
        if (
            evaluation.insurer is None or evaluation.vehicle_type is None
            or evaluation.base is None or evaluation.km is None
        ):
            self._log("Sin aseguradora, tipo, base o km: no se compara.")
            return (evaluation.pk, None, None, "faltan datos")

        notes = []
        estimated = estimate_budget(
            evaluation, when, notes, data=data, task_times=task_times,
        )
        estimated_lines = calculate_budget(estimated)

        manual, route = self._manual_budget(
            evaluation, data, when, task_times,
        )
        if manual is None:
            self._log("Presupuesto manual no calculado: %s" % route)
            return (
                evaluation.pk, estimated.total_amount, None,
                "ruta manual: %s" % route,
            )
        manual_lines = calculate_budget(manual)

        self._log("Km: valoración %s · manual %s (Google %s)" % (
            estimated.km_total, manual.km_total, route["distance_km"],
        ))
        self._log(
            "Nocturno: valoración %s · manual %s · nocturno o festivo: "
            "valoración %s · manual %s" % (
                _yes(estimated.is_night), _yes(manual.is_night),
                _yes(estimated.is_night_or_holiday),
                _yes(manual.is_night_or_holiday),
            ),
        )
        from budgets.service_evaluation import _calendar_year
        from budgets.services import _is_holiday, _resolve_night_schedule

        schedule = _resolve_night_schedule(evaluation.insurer)
        company = evaluation.company
        self._log(
            "Horario nocturno de la aseguradora: %s · de la empresa: %s-%s "
            "· festivo en %s: %s (calendario de %s)" % (
                "%s %s-%s" % (
                    schedule.name, schedule.night_start, schedule.night_end,
                ) if schedule else "ninguno",
                company.night_start, company.night_end,
                evaluation.base.name,
                _yes(_is_holiday(when.date(), evaluation.base)),
                _calendar_year(evaluation.base) or "—",
            ),
        )
        self._log("Peajes de la ruta manual: %s €" % (
            route.get("route_toll_budget_cost") or ZERO,
        ))
        if notes:
            self._log("Conceptos de las tareas: %s" % " ".join(notes))
        self._lines("Valoración", estimated_lines, estimated.total_amount)
        self._lines("Manual", manual_lines, manual.total_amount)
        reasons = _reasons(estimated, manual, estimated_lines, manual_lines)
        self._log("Diferencia (manual - valoración): %s € · %s" % (
            _eur(manual.total_amount - estimated.total_amount),
            reasons or "cuadra",
        ))
        return (
            evaluation.pk, estimated.total_amount, manual.total_amount,
            reasons or "cuadra",
        )

    def _manual_budget(self, evaluation, data, when, task_times):
        """
        The Budget the manual wizard would save for the service.

        ---

        El presupuesto que guardaría el asistente manual con el
        planificador de ruta, con los mismos datos. Devuelve (budget,
        ruta) o (None, motivo).
        """
        import os

        from budgets.dispatch_vehicle import ON_SITE_KINDS, job_for
        from budgets.models import Budget
        from budgets.service_evaluation import (
            _apply_task_concepts,
            service_addresses,
        )
        from budgets.service_geocode import geocode
        from budgets.services import (
            _resolve_night_schedule,
            calculate_route_multileg,
        )

        pickup, delivery = service_addresses(data)
        job = job_for(data) or {"trabajos": ["tow_light"]}
        kinds = job["trabajos"]
        on_site = bool(kinds) and all(k in ON_SITE_KINDS for k in kinds)
        stops = [("Recogida", pickup)]
        if delivery and not on_site:
            stops.append(("Entrega", delivery))
        waypoints = []
        for label, address in stops:
            point = geocode(address)
            if point is None:
                return None, "no se geocodifica «%s»" % address
            self._log("%s: %s -> %s, %s" % (
                label, address, point[0], point[1],
            ))
            waypoints.append({
                "lat": float(point[0]), "lng": float(point[1]),
                "label": label, "address": address,
                "is_base_return": False,
            })
        # The wizard joins date and time without zone (BudgetWaypointView).
        # El asistente une fecha y hora sin zona horaria.
        service_datetime = dt.datetime.combine(
            when.date(), when.time().replace(microsecond=0),
        )
        route = calculate_route_multileg(
            base=evaluation.base,
            waypoints=waypoints,
            service_datetime=service_datetime,
            api_key=os.environ.get("GOOGLE_MAPS_API_KEY", ""),
            company=evaluation.company,
        )
        if route.get("error"):
            return None, route["error"]
        km_phase1 = int(Decimal(str(route["distance_km"])).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP,
        ))
        # BudgetWizardView: only the insurer's night schedule, inclusive.
        # Solo el horario nocturno de la aseguradora, extremos incluidos.
        is_night = False
        schedule = _resolve_night_schedule(evaluation.insurer)
        moment = service_datetime.time()
        if schedule is not None:
            start, end = schedule.night_start, schedule.night_end
            if start <= end:
                is_night = start <= moment <= end
            else:
                is_night = moment >= start or moment <= end
        budget = Budget(
            company=evaluation.company,
            insurer=evaluation.insurer,
            vehicle_type=evaluation.vehicle_type,
            base=evaluation.base,
            service_date=when.date(),
            service_time=moment,
            km_phase1=km_phase1,
            is_night=is_night,
            route_calculation_mode=Budget.ROUTE_MODE_API,
            route_distance_km=route["distance_km"],
            route_toll_budget_cost=route.get("route_toll_budget_cost"),
            encoded_polyline=route.get("encoded_polyline") or None,
            apply_iva=False,
        )
        _apply_task_concepts(budget, data, task_times, [])
        return budget, route

    def _lines(self, title, lines, total):
        """
        Log the lines of one budget.

        ---

        Escribe las líneas de un presupuesto.
        """
        self._plain("  %s:" % title)
        for line in lines:
            if line.is_informational:
                continue
            self._plain("    %-14s %-34s %9s x %9s = %9s" % (
                _code(line), line.concept_label[:34], line.units,
                line.unit_price, line.subtotal,
            ))
        self._plain("    %-14s %-34s %33s" % ("TOTAL", "sin IVA", total))


def _eur(value):
    """
    Amount with two decimals, or a dash.

    ---

    Importe con dos decimales, o un guion.
    """
    return "—" if value is None else "%.2f" % value


def _yes(value):
    """
    "sí" or "no".

    ---

    "sí" o "no".
    """
    return "sí" if value else "no"


def _reasons(estimated, manual, estimated_lines, manual_lines):
    """
    What differs between the two budgets, in words.

    ---

    Qué cambia entre los dos presupuestos: km, nocturno o festivo,
    peajes y conceptos que solo lleva uno.
    """
    reasons = []
    if estimated.km_total != manual.km_total:
        reasons.append("km %s / %s" % (estimated.km_total, manual.km_total))
    if estimated.is_night_or_holiday != manual.is_night_or_holiday:
        reasons.append("nocturno o festivo")
    tolls = sum(
        (line.subtotal for line in manual_lines
         if _code(line).startswith("TOLL")
         and not line.is_informational),
        ZERO,
    )
    if tolls:
        reasons.append("peajes %s" % tolls)
    codes_estimated = {_code(line) for line in estimated_lines}
    codes_manual = {_code(line) for line in manual_lines}
    only = sorted(
        code for code in codes_manual ^ codes_estimated
        if not code.startswith("TOLL")
    )
    if only:
        reasons.append("conceptos distintos: %s" % ", ".join(only))
    return "; ".join(reasons)
