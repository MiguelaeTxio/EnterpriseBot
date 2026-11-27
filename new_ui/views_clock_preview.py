# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_clock_preview.py
"""
What the worker sees on the phone, for each way of clocking.

---

Cómo ve el trabajador el fichaje en el móvil, en cada forma de fichar
(S149, Miguel Ángel, 27/11: "que nos muestre los fichajes por tipo, los
fichajes sin tipo, lo que es la interfaz del móvil"). Empresa › Fichaje
(«Nuevo y ajustes»): una ventana con la página del fichaje de verdad
(hr_calendar/templates/hr_calendar/clockin.html) en modo vista previa,
antes de entrar y con la jornada abierta, para:
- por tipos (gruistas, chóferes, asistencia);
- botón único (taller);
- botón único con «No he parado para comer» y comentario (Plataformas).
La vista previa no ficha ni toca lo guardado en el navegador.
"""
import datetime

from django.shortcuts import render
from django.utils import timezone
from django.views import View

from new_ui.mixins import SuperuserRequiredMixin

MODES = (
    ("types", "Por tipos",
     "Gruistas, chóferes, asistencia: eligen el tipo al entrar y lo "
     "cambian durante la jornada."),
    ("normal", "Botón único",
     "Taller: entrada y salida con el mismo botón."),
    ("meal", "Botón único con «No he parado para comer»",
     "Plataformas: además, la casilla de comer y un comentario al fichar."),
)
STATES = (("closed", "Antes de entrar"),
          ("open", "Con la jornada abierta"))


class ClockPreviewView(SuperuserRequiredMixin, View):
    """GET: la ventana con los móviles de ejemplo."""

    def get(self, request):
        return render(request, "new_ui/_clock_preview.html", {
            "modes": MODES, "states": STATES,
        })


class ClockPreviewPageView(SuperuserRequiredMixin, View):
    """GET ?mode=&state=: la página del fichaje con un estado de ejemplo."""

    def get(self, request):
        mode = request.GET.get("mode")
        if mode not in dict((m, m) for m, _l, _h in MODES):
            mode = "types"
        state = request.GET.get("state")
        if state not in ("closed", "open"):
            state = "closed"
        from hr_calendar.clockin import APP_VERSION

        response = render(request, "hr_calendar/clockin.html", {
            "app_version": APP_VERSION,
            "preview": {"status": _status(request, mode, state)},
        })
        # Se abre dentro de la ventana del panel.
        response["X-Frame-Options"] = "SAMEORIGIN"
        return response


def _status(request, mode, state):
    """El estado (como /fichaje/estado/) de un trabajador de ejemplo."""
    from hr_calendar.clock_report import MAX_SHIFT_HOURS
    from hr_calendar.clock_settings import active_types
    from hr_calendar.clockin import APP_VERSION

    company = request.user.company_user.company
    by_types = mode == "types"
    types = list(active_types(company)) if by_types else []
    first = next((t for t in types if t.is_default), types[0] if types
                 else None)
    now = timezone.localtime()
    if state == "open":
        at = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if at > now:
            at = now - datetime.timedelta(minutes=30)
        last = {"kind": "IN", "kind_label": "Entrada", "pressed_at": at,
                "type": first}
        next_kind = "OUT"
    else:
        at = (now - datetime.timedelta(days=1)).replace(
            hour=17, minute=30, second=0, microsecond=0)
        last = {"kind": "OUT", "kind_label": "Salida", "pressed_at": at,
                "type": None}
        next_kind = "IN"
    clock_type = last["type"] if last["kind"] != "OUT" else None
    return {
        "own_allowed": False, "own_shifts": [], "own_days": [0, 1, 2, 3, 4],
        "own_until": "", "own_max": 2, "reminders": False,
        "in_reminders": [], "out_reminders": [],
        "in_choices": [], "out_choices": [],
        "app_version": APP_VERSION,
        "name": "TRABAJADOR DE EJEMPLO",
        "company": company.name,
        "last": {
            "id": "vista-previa", "kind": last["kind"],
            "kind_label": last["kind_label"],
            "pressed_at": last["pressed_at"].isoformat(),
            "received_at": last["pressed_at"].isoformat(),
            "delay_seconds": 0, "manual": False,
            "clock_type": clock_type.pk if clock_type else None,
            "clock_type_name": clock_type.name if clock_type else "",
        },
        "next_kind": next_kind,
        "forgotten_after": None, "forgotten": "",
        "max_shift_hours": MAX_SHIFT_HOURS,
        "starts_on": None, "starts_text": "",
        "uses_types": by_types,
        "meal_check": mode in ("types", "meal"),
        "press_notes": mode == "meal",
        "day_end": "17:30",
        "clock_types": [{
            "id": t.pk, "name": t.name, "icon": t.icon,
            "is_default": t.is_default, "role": t.role} for t in types],
        "crane_albaranes": {"show": False, "pending": 0},
    }
