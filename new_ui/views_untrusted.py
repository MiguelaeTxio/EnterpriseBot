# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_untrusted.py
"""
Presses refused for coming from a phone that is not a trusted device.

---

Fichajes rechazados por venir de un móvil sin permiso (S149, Miguel
Ángel, 27/11: un móvil lleva desde el 12/11 intentando fichar sin ser
dispositivo de confianza y no se sabe de quién es). Ventana de
Personal › Fichaje («Nuevo y ajustes»): cuándo, dónde, la llave que
traía y los 4 últimos números del DNI que escribió el trabajador.
Lee hr_calendar.ClockUntrustedPress (lo apunta /fichaje/enviar/).
"""
import datetime

from django.shortcuts import render
from django.utils import timezone
from django.views import View

from new_ui.mixins import SuperuserRequiredMixin


class UntrustedPressesView(SuperuserRequiredMixin, View):
    """GET: la ventana con los últimos 60 días."""

    def get(self, request):
        from hr_calendar.models import ClockUntrustedPress

        since = timezone.now() - datetime.timedelta(days=60)
        items = list(ClockUntrustedPress.objects.filter(
            first_seen__gte=since,
        ).select_related("key_user__user", "dni_person").order_by(
            "-first_seen")[:500])
        return render(request, "new_ui/_untrusted.html", {"items": items})
