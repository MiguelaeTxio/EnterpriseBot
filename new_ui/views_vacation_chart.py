# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_vacation_chart.py
"""
Load the cranes' vacation chart (VACACIONES.xlsx), new interface (S165).

---

Carga del cuadrante de vacaciones de los gruistas (VACACIONES.xlsx: una
hoja por año, una X por día) en Empresa › Vacaciones (S165, invasora
H11). «Comprobar» solo cuenta; «Cargar» registra los periodos. La
lógica es de hr_calendar.vacation_sheet_import; el Excel no se guarda.
"""
import logging

from django.http import JsonResponse
from django.views import View

from new_ui.mixins import SuperuserRequiredMixin

logger = logging.getLogger(__name__)
SHOWN = 8


class VacationChartUploadView(SuperuserRequiredMixin, View):
    """
    POST `planilla` + `action` (check | load): the vacation chart.

    ---

    POST: comprueba (`check`) o carga (`load`) el cuadrante de
    vacaciones y dice cuántos periodos, de cuántos trabajadores, cuántos
    días ya estaban y qué nombres no se reconocen (se asignan en
    Tráfico › Nombres y se vuelve a cargar).
    """

    def post(self, request):
        from hr_calendar.vacation_sheet_import import import_chart

        upload = request.FILES.get("planilla")
        if upload is None:
            return JsonResponse({"ok": False, "message": "Elige el Excel "
                                 "del cuadrante."}, status=400)
        dry_run = request.POST.get("action") != "load"
        cu = request.user.company_user
        try:
            summary = import_chart(cu.company, upload, created_by=cu,
                                   dry_run=dry_run)
        except ValueError as exc:
            return JsonResponse({"ok": False, "message": str(exc)},
                                status=400)
        except Exception as exc:  # noqa: BLE001 -- Excel ilegible
            logger.exception("# [new_ui VACACIONES] Cuadrante no leído")
            return JsonResponse({"ok": False, "message": "No se ha podido "
                                 "leer el Excel: %s" % exc}, status=400)
        verb = "Se registrarían" if dry_run else "Registrados"
        parts = ["%s %d periodo(s) de vacaciones (%d día(s)) de %d "
                 "trabajador(es)." % (verb, summary["periods"],
                                      summary["days"], summary["people"])]
        if summary["past"]:
            parts.append("%d ya pasados: sin tarea de aviso." %
                         summary["past"])
        if summary["already"]:
            parts.append("%d día(s) ya estaban registrados." %
                         summary["already"])
        if summary["unknown"]:
            parts.append("Sin reconocer: %s%s. Di quién es cada uno en "
                         "Tráfico › Planning › Nombres (la misma lista de "
                         "nombres sirve para el planning de grúas y para "
                         "este cuadrante) y vuelve a comprobar." % (
                             ", ".join(summary["unknown"][:SHOWN]),
                             " y %d más" % (len(summary["unknown"]) - SHOWN)
                             if len(summary["unknown"]) > SHOWN else ""))
        if summary["errors"]:
            parts.append("Con error: %s." % "; ".join(
                summary["errors"][:SHOWN]))
        if summary["problems"]:
            parts.append(" ".join(summary["problems"][:SHOWN]))
        logger.info("# [new_ui VACACIONES] %s %s el cuadrante: %d periodos",
                    cu, "comprueba" if dry_run else "carga",
                    summary["periods"])
        return JsonResponse({"ok": True, "message": " ".join(parts)})
