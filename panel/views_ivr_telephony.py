# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_ivr_telephony.py
"""
Telephony → Sections in the switchboard (S155).

What the phone switchboard needs from each Section (IVR checkboxes, data
capture set, opening hours) is configured here, apart from the Section
form, which keeps only what defines the section.
---
Telefonía → Secciones en la centralita (S155).

Lo que la centralita necesita de cada sección (casillas IVR, conjunto de
captura, horario de atención) se configura aquí, aparte de la ficha de la
sección, que se queda con lo que define la sección. Miguel Ángel: "lo que
es referente ya al flujo IVR, captura de datos, etcétera, eso se debe
definir en la parte de telefonía".
"""

from django.contrib import messages as django_messages
from django.db.models import Q
from django.shortcuts import redirect
from django.utils.timezone import now
from django.views.generic import UpdateView

from ivr_config.models import (
    DataCaptureSet,
    PresenceStatus,
    Section,
    SectionContact,
    WorkdaySchedule,
)
from panel.forms import SectionTelephonyForm
from panel.mixins import AdminRoleRequiredMixin

WEEKDAY_SHORT = ["L", "M", "X", "J", "V", "S", "D"]


def _transfer_contacts(section) -> list:
    """
    Returns the section contacts in transfer order.
    ---
    Devuelve los contactos de la sección en el orden en que la centralita
    les pasa la llamada (prioridad y nombre, como _execute_transfer), con
    los que no tienen teléfono al final.
    """
    rows = list(
        SectionContact.objects.filter(section=section)
        .select_related("contact")
        .order_by("priority", "contact__name")
    )
    return (
        [r for r in rows if r.contact.phone_number]
        + [r for r in rows if not r.contact.phone_number]
    )


def _legacy_slots_summary(section) -> str:
    """
    Old SectionSchedule slots grouped by days, or "".
    ---
    Franjas antiguas (SectionSchedule) agrupadas por días
    ("L M X J V 07:00–15:00"), o "" si no tiene.
    """
    slots = {}
    for sched in section.schedules.all():
        key = (sched.time_open, sched.time_close)
        slots.setdefault(key, set()).add(sched.weekday)
    if not slots:
        return ""
    parts = []
    for (t_open, t_close), days in sorted(slots.items()):
        day_text = " ".join(
            WEEKDAY_SHORT[d] for d in sorted(days) if 0 <= d < 7)
        parts.append(f"{day_text} {t_open:%H:%M}–{t_close:%H:%M}")
    return " · ".join(parts)


def _opening_hours_summary(section) -> str:
    """
    Short text with the opening hours of the section.
    ---
    Texto corto con el horario de atención: "24 h", el horario de jornada
    elegido, las franjas antiguas mientras no haya uno elegido, o "Sin
    horario".
    """
    if section.is_24h:
        return "24 h"
    if section.attention_schedule_id:
        return section.attention_schedule.label
    legacy = _legacy_slots_summary(section)
    return f"{legacy} (franjas antiguas)" if legacy else "Sin horario"


def section_ivr_status(section) -> dict:
    """
    Whether the switchboard offers the section, and why not.
    ---
    Si la centralita ofrece la sección y, si no, por qué. Mismos criterios
    que ivr_config.services (sección activa, casilla de transferencia y
    flujo IVR activo). Los avisos son cosas que no la sacan de la
    centralita pero harán que falle o que la dé por cerrada.
    """
    reasons = []
    if not section.is_active:
        reasons.append("Sección inactiva.")
    if not section.ivr_transfer_enabled:
        reasons.append("Casilla de la centralita sin marcar.")
    if not section.call_flow_id or not section.call_flow.is_active:
        reasons.append("Sin flujo IVR activo.")
    contacts = _transfer_contacts(section)
    with_phone = [r for r in contacts if r.contact.phone_number]
    warnings = []
    if not reasons:
        if not with_phone:
            warnings.append(
                "Ningún contacto con teléfono: no podrá pasar la llamada.")
        if (not section.is_24h and not section.attention_schedule_id
                and not section.schedules.exists()):
            warnings.append(
                "Sin horario de atención: la dará siempre por cerrada.")
    return {
        "in_ivr": not reasons,
        "reasons": reasons,
        "warnings": warnings,
        "contacts": contacts,
        "contacts_with_phone": len(with_phone),
        "hours": _opening_hours_summary(section),
        "legacy_slots": (
            "" if section.attention_schedule_id
            else _legacy_slots_summary(section)),
    }


def _get_own_presence(request):
    """
    Returns the current active PresenceStatus of the authenticated user.
    ---
    Retorna el PresenceStatus activo actual del usuario autenticado.
    """
    return PresenceStatus.objects.filter(
        company_user=request.user.company_user,
        starts_at__lte=now(),
    ).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=now())
    ).order_by("-starts_at").first()


class IvrSectionUpdateView(AdminRoleRequiredMixin, UpdateView):
    """
    Edits what the switchboard needs from one section.
    ---
    Edita lo que la centralita necesita de una sección: casillas IVR,
    conjunto de captura y horario de atención (uno de los horarios de
    jornada). Al guardar, la señal de
    Section regenera su flujo IVR.
    """

    model = Section
    form_class = SectionTelephonyForm
    template_name = "panel/ivr_sections/form.html"

    def get_queryset(self):
        """
        Sections of the user's company.
        ---
        Secciones de la empresa del usuario.
        """
        return Section.objects.filter(
            company=self.request.user.company_user.company)

    def get_form(self, form_class=None):
        """
        Restricts the data capture sets to the user's company.
        ---
        Restringe los conjuntos de captura a la empresa del usuario.
        """
        form = super().get_form(form_class)
        field = form.fields["data_capture_set"]
        field.queryset = DataCaptureSet.objects.filter(
            company=self.request.user.company_user.company
        ).order_by("name")
        field.required = False
        field.empty_label = "— Ninguno —"
        field = form.fields["attention_schedule"]
        field.queryset = WorkdaySchedule.objects.filter(
            company=self.request.user.company_user.company
        ).order_by("label")
        field.required = False
        field.empty_label = "— Sin horario —"
        return form

    def form_valid(self, form):
        """
        Saves the section; Section post_save regenerates its CallFlow.
        ---
        Guarda la sección; el post_save de Section regenera su flujo IVR.
        """
        self.object = form.save()
        django_messages.success(
            self.request,
            f"Centralita de '{self.object.name}' guardada correctamente.")
        return redirect("panel:ivr_section_list")

    def get_context_data(self, **kwargs):
        """
        Adds the switchboard status and the transfer contacts.
        ---
        Añade el estado en la centralita y los contactos a los que se pasa
        la llamada.
        """
        context = super().get_context_data(**kwargs)
        context["ivr_status"] = section_ivr_status(self.object)
        context["company"] = self.request.user.company_user.company
        context["company_user"] = self.request.user.company_user
        context["own_presence"] = _get_own_presence(self.request)
        context["active_nav"] = "ivr_sections"
        return context
