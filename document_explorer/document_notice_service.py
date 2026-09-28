# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/document_notice_service.py
"""
H30 (S122). Document notices computed from the documentation
requirements (JobPosition) and their notice settings
(RequirementAlertRule), for every active person and machine.

---

H30 (S122). Avisos de documentación calculados a partir de los
requisitos de documentación y de su configuración de avisos, para
todas las personas activas y máquinas activas. Miguel Ángel: "el mismo
requisito de documentación es el que nos sirve para los avisos [...]
además de avisar porque estén caducados habrá que avisar también de
que no los tenemos".

Mismo criterio que `required_documentation_service` (triángulos de
la ficha, S119/S120) para decidir qué documento cuenta: el MÁS MODERNO
de cada tipo obligatorio (caducidad si la tiene, si no emisión), DNI y
NIE excluyentes, y con clases de permiso exigidas el carné solo cuenta
para "falta" y la caducidad la deciden las clases. Las clases usan los
avisos que tenga "Carnet de conducir" en el mismo requisito.

Tres clases de aviso:
- MISSING: tipo obligatorio sin ningún documento (si el requisito
  tiene marcado "Si falta").
- EXPIRED: el documento más moderno ya caducó (si el tipo tiene algún
  aviso de caducidad configurado).
- UPCOMING: la fecha de alguno de sus avisos ya llegó y todavía no ha
  caducado -- el mismo día en que lo mandaría el WhatsApp.

Además `calendar` lista TODAS las fechas de aviso futuras de los
documentos con avisos configurados, para el panel de calendario.
El cálculo es siempre en vivo, sin guardar nada: el aviso desaparece
solo en cuanto se sube el documento que lo resuelve.
"""
import calendar as calendar_module
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.contrib.contenttypes.models import ContentType

BUCKET = "cgs_grupo_alvarez"
IDENTITY_CODES = ("DNI", "NIE")
DRIVING_CARD_CODE = "CARNET_CONDUCIR"

KIND_MISSING = "MISSING"
KIND_EXPIRED = "EXPIRED"
KIND_UPCOMING = "UPCOMING"

DOMAIN_PERSONAL = "personal"
DOMAIN_MACHINE = "maquinaria"


@dataclass
class NoticeStep:
    """
    One configured notice date of a document.

    ---

    Una fecha de aviso configurada de un documento: etiqueta visible
    ("30 días", "3 meses") y fecha en que se dispara.
    """

    label: str
    trigger_date: date


@dataclass
class DocumentNotice:
    """
    One notice (pending or scheduled) for one subject and document.

    ---

    Un aviso de un sujeto (persona o máquina) sobre un documento
    obligatorio. `steps` son todas sus fechas de aviso configuradas;
    `reached_step` la más reciente ya alcanzada (UPCOMING).
    """

    domain: str
    subject_id: int
    subject_label: str
    requirement_name: str
    document_label: str
    document_type_id: object
    kind: str
    expiry_date: date = None
    entry_id: int = None
    steps: list = field(default_factory=list)
    reached_step: NoticeStep = None

    @property
    def days_left(self):
        """
        Days until expiry (negative once expired), or None.

        ---

        Días hasta la caducidad (negativo si ya caducó), o None.
        """
        if self.expiry_date is None:
            return None
        return (self.expiry_date - date.today()).days


@dataclass
class CalendarItem:
    """
    One future notice date for the calendar panel.

    ---

    Una fecha de aviso futura, para el panel de calendario.
    """

    trigger_date: date
    step_label: str
    notice: DocumentNotice


def subtract_months(value, months):
    """
    Same day `months` calendar months earlier (clamped to month end).

    ---

    El mismo día `months` meses naturales antes, ajustado al último
    día del mes si no existe (31/05 menos 3 meses -> 28 o 29/02).
    """
    month_index = value.year * 12 + (value.month - 1) - months
    year, month = divmod(month_index, 12)
    month += 1
    last_day = calendar_module.monthrange(year, month)[1]
    return date(year, month, min(value.day, last_day))


def _custom_step(amount, unit, expiry_date):
    """
    Build the NoticeStep of one custom notice, or None if unset.

    ---

    Construye el NoticeStep de un aviso personalizado, o None si no
    está configurado.
    """
    from document_explorer.models import RequirementAlertRule

    if not amount or not unit:
        return None
    if unit == RequirementAlertRule.UNIT_MONTHS:
        label = "%d %s" % (amount, "mes" if amount == 1 else "meses")
        return NoticeStep(label, subtract_months(expiry_date, amount))
    label = "%d %s" % (amount, "día" if amount == 1 else "días")
    return NoticeStep(label, expiry_date - timedelta(days=amount))


def notice_steps(rule, expiry_date):
    """
    All configured notice dates of a rule for one expiry date.

    ---

    Todas las fechas de aviso que configura `rule` para una fecha de
    caducidad, de la más temprana a la más tardía.
    """
    steps = []
    fixed = (
        (rule.notify_30_days, 30, "30 días"),
        (rule.notify_15_days, 15, "15 días"),
        (rule.notify_7_days, 7, "7 días"),
        (rule.notify_day_before, 1, "Día anterior"),
    )
    for enabled, days, label in fixed:
        if enabled:
            steps.append(
                NoticeStep(label, expiry_date - timedelta(days=days)),
            )
    for amount, unit in (
        (rule.custom_1_value, rule.custom_1_unit),
        (rule.custom_2_value, rule.custom_2_unit),
    ):
        step = _custom_step(amount, unit, expiry_date)
        if step is not None:
            steps.append(step)
    steps.sort(key=lambda step: step.trigger_date)
    return steps


def has_expiry_notice(rule):
    """
    True if the rule has at least one expiry notice configured.

    ---

    True si la regla tiene al menos un aviso de caducidad.
    """
    return bool(
        rule.notify_30_days or rule.notify_15_days or rule.notify_7_days
        or rule.notify_day_before
        or (rule.custom_1_value and rule.custom_1_unit)
        or (rule.custom_2_value and rule.custom_2_unit)
    )


def _expiry_notice(base, rule, expiry_date, entry_id, today):
    """
    EXPIRED or UPCOMING notice (or scheduled-only) for one expiry date.

    ---

    Aviso de caducidad para una fecha: EXPIRED si ya pasó, UPCOMING si
    alguna de sus fechas de aviso ya llegó, o None-kind (solo
    calendario) si todas están en el futuro. Devuelve None si la regla
    no tiene avisos de caducidad.
    """
    if not has_expiry_notice(rule):
        return None
    steps = notice_steps(rule, expiry_date)
    notice = DocumentNotice(
        expiry_date=expiry_date, entry_id=entry_id, steps=steps, **base
    )
    if expiry_date < today:
        notice.kind = KIND_EXPIRED
        return notice
    reached = [step for step in steps if step.trigger_date <= today]
    if reached:
        notice.kind = KIND_UPCOMING
        notice.reached_step = reached[-1]
    return notice


def _subject_label(subject, domain):
    """
    Readable subject label.

    ---

    Nombre legible del sujeto: "APELLIDOS, Nombre" o "CÓDIGO -- modelo".
    """
    if domain == DOMAIN_PERSONAL:
        surnames = " ".join(
            part for part in (subject.first_surname, subject.second_surname)
            if part
        )
        return "%s, %s" % (surnames, subject.given_name)
    return "%s -- %s" % (subject.code, subject.brand_model or "")


def _latest(entries):
    """
    Most recent entry (expiry, else issue date; tie by pk).

    ---

    Documento más moderno (caducidad, si no emisión; desempate pk),
    mismo criterio que la ficha.
    """
    return max(
        entries,
        key=lambda entry: (
            entry.expiry_date or entry.issue_date or date.min, entry.pk,
        ),
    )


def compute_notices(domain):
    """
    Compute (pending, scheduled, calendar) for one domain.

    ---

    Calcula los avisos de un dominio (`DOMAIN_PERSONAL` o
    `DOMAIN_MACHINE`) para todos sus sujetos activos con requisito:

    - `pending`: MISSING, EXPIRED y UPCOMING (lo que el WhatsApp
      mandaría hoy o ya mandó).
    - `scheduled`: documentos con avisos configurados que todavía no
      han alcanzado ninguna fecha de aviso.
    - `calendar`: todas las fechas de aviso futuras (> hoy), ordenadas.
    """
    from document_explorer.models import (
        DocumentIndexEntry, DrivingLicenceGrant, JobPosition,
        PersonIdentity, RequirementAlertRule,
    )
    from document_explorer.required_documentation_service import (
        latest_driving_card,
    )
    from fleet.models import MachineAsset

    today = date.today()
    if domain == DOMAIN_PERSONAL:
        subjects = list(
            PersonIdentity.objects.filter(
                is_active_employee=True, job_position__isnull=False,
            ).select_related("job_position"),
        )
        requirement_of = {s.pk: s.job_position for s in subjects}
        subject_model = PersonIdentity
    else:
        subjects = list(
            MachineAsset.objects.filter(
                is_active=True, document_requirement__isnull=False,
            ).select_related("document_requirement"),
        )
        requirement_of = {s.pk: s.document_requirement for s in subjects}
        subject_model = MachineAsset

    pending, scheduled, calendar_items = [], [], []
    if not subjects:
        return pending, scheduled, calendar_items

    requirement_ids = {req.pk for req in requirement_of.values()}
    rules = {}
    for rule in RequirementAlertRule.objects.filter(
        job_position_id__in=requirement_ids,
    ).select_related("document_type"):
        rules.setdefault(rule.job_position_id, {})[
            rule.document_type_id
        ] = rule
    if not rules:
        return pending, scheduled, calendar_items

    categories_of = {}
    for requirement in JobPosition.objects.filter(
        pk__in=requirement_ids,
    ).prefetch_related("required_driving_categories"):
        categories_of[requirement.pk] = list(
            requirement.required_driving_categories.all(),
        )

    type_ids = {
        type_id for by_type in rules.values() for type_id in by_type
    }
    content_type = ContentType.objects.get_for_model(subject_model)
    entries_by_subject = {}
    for entry in DocumentIndexEntry.objects.filter(
        bucket=BUCKET,
        domain_content_type=content_type,
        domain_object_id__in=[s.pk for s in subjects],
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True,
        purged_at__isnull=True,
        document_type_id__in=type_ids,
    ).select_related("document_type"):
        entries_by_subject.setdefault(entry.domain_object_id, []).append(
            entry,
        )

    card_ids = [
        entry.pk for group in entries_by_subject.values() for entry in group
        if entry.document_type.code == DRIVING_CARD_CODE
    ]
    grants_by_card = {}
    for grant in DrivingLicenceGrant.objects.filter(
        entry_id__in=card_ids,
    ).select_related("category"):
        grants_by_card.setdefault(grant.entry_id, []).append(grant)

    for subject in subjects:
        requirement = requirement_of[subject.pk]
        subject_rules = rules.get(requirement.pk)
        if not subject_rules:
            continue
        entries = entries_by_subject.get(subject.pk, [])
        by_type = {}
        for entry in entries:
            by_type.setdefault(entry.document_type_id, []).append(entry)
        present_codes = {entry.document_type.code for entry in entries}
        has_identity = bool(set(IDENTITY_CODES) & present_codes)
        categories = categories_of.get(requirement.pk, [])
        label = _subject_label(subject, domain)

        for type_id, rule in subject_rules.items():
            doc_type = rule.document_type
            base = {
                "domain": domain,
                "subject_id": subject.pk,
                "subject_label": label,
                "requirement_name": requirement.name,
                "document_label": doc_type.label,
                "document_type_id": type_id,
                "kind": None,
            }
            docs = by_type.get(type_id, [])
            if not docs:
                if doc_type.code in IDENTITY_CODES and has_identity:
                    continue
                if rule.notify_missing:
                    notice = DocumentNotice(**base)
                    notice.kind = KIND_MISSING
                    pending.append(notice)
                continue

            if doc_type.code == DRIVING_CARD_CODE and categories:
                _driving_class_notices(
                    base, rule, docs, categories, grants_by_card, today,
                    pending, scheduled, calendar_items,
                )
                continue
            if not doc_type.tracks_expiry:
                continue
            latest = _latest(docs)
            if latest.expiry_date is None:
                continue
            notice = _expiry_notice(
                base, rule, latest.expiry_date, latest.pk, today,
            )
            _file_notice(notice, today, pending, scheduled, calendar_items)

    pending.sort(key=_pending_sort_key)
    scheduled.sort(key=lambda n: (n.steps[0].trigger_date, n.subject_label))
    calendar_items.sort(
        key=lambda item: (item.trigger_date, item.notice.subject_label),
    )
    return pending, scheduled, calendar_items


def _driving_class_notices(base, rule, cards, categories, grants_by_card,
                           today, pending, scheduled, calendar_items):
    """
    Notices of the required driving licence classes of one subject.

    ---

    Avisos de las clases de permiso exigidas de un sujeto, leídas del
    carné más reciente CON matriz (mismo criterio que la ficha), con
    la configuración de avisos de "Carnet de conducir".
    """
    cards_with_grants = frozenset(
        entry.pk for entry in cards if entry.pk in grants_by_card
    )
    card = latest_driving_card(cards, cards_with_grants)
    grants = {
        grant.category.code: grant
        for grant in grants_by_card.get(card.pk, [])
    } if card is not None else {}
    for category in categories:
        class_base = dict(base)
        class_base["document_label"] = (
            "Permiso de conducción %s" % category.code
        )
        grant = grants.get(category.code)
        if grant is None:
            if rule.notify_missing:
                notice = DocumentNotice(**class_base)
                notice.kind = KIND_MISSING
                notice.entry_id = card.pk if card is not None else None
                pending.append(notice)
            continue
        if grant.expiry_date is None:
            continue
        notice = _expiry_notice(
            class_base, rule, grant.expiry_date, card.pk, today,
        )
        _file_notice(notice, today, pending, scheduled, calendar_items)


def _file_notice(notice, today, pending, scheduled, calendar_items):
    """
    Put one expiry notice into its panel(s).

    ---

    Coloca un aviso de caducidad en su panel: pendiente (EXPIRED o
    UPCOMING) o programado; y sus fechas futuras en el calendario.
    """
    if notice is None:
        return
    if notice.kind in (KIND_EXPIRED, KIND_UPCOMING):
        pending.append(notice)
    else:
        scheduled.append(notice)
    if notice.kind != KIND_EXPIRED:
        for step in notice.steps:
            if step.trigger_date > today:
                calendar_items.append(
                    CalendarItem(step.trigger_date, step.label, notice),
                )


def _pending_sort_key(notice):
    """
    Most urgent first: expired, then upcoming by expiry, then missing.

    ---

    Lo más urgente primero: caducados (el más antiguo arriba), luego
    próximos por fecha de caducidad, luego faltantes.
    """
    order = {KIND_EXPIRED: 0, KIND_UPCOMING: 1, KIND_MISSING: 2}
    return (
        order[notice.kind],
        notice.expiry_date or date.max,
        notice.subject_label,
        notice.document_label,
    )
