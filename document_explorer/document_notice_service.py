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
from django.db.models import Prefetch, Q

from document_explorer import employment_period_service as periods
from document_explorer.naming_service import is_gerencia

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
    requirement_id: int = None
    # S153: un sujeto puede tener varios requisitos; un tipo que piden
    # dos de ellos da UN aviso, con los dos requisitos aquí.
    # `requirement_id`/`requirement_name` son el primero y la lista
    # legible, para lo que ya los usaba.
    requirement_ids: tuple = ()
    requirement_names: tuple = ()
    subject_company: str = ""
    subject_family: str = ""
    expiry_date: date = None
    entry_id: int = None
    steps: list = field(default_factory=list)
    reached_step: NoticeStep = None
    # H30 (S131): avisos de revisión por horas/km de centros de gasto
    # (fleet.service_plan_service). `service_due` (lectura a la que
    # toca) entra en la clave: una revisión nueva cambia el aviso.
    is_service: bool = False
    service_due: str = ""
    service_text: str = ""

    @property
    def notice_key(self):
        """
        Stable identity of this notice for the delivery log.

        ---

        Identidad estable del aviso para el registro de envíos: cambia
        si cambia la caducidad (documento renovado) o, en los
        próximos, el aviso alcanzado.
        """
        parts = [
            self.domain, str(self.subject_id), str(self.document_type_id),
            self.document_label, self.kind,
            self.expiry_date.isoformat() if self.expiry_date else "",
        ]
        if self.kind == KIND_UPCOMING and self.reached_step is not None:
            parts.append(self.reached_step.label)
        if self.is_service:
            parts.append(self.service_due)
        return "|".join(parts)[:255]

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
    for amount, unit in _custom_pairs(rule):
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
        or any(amount and unit for amount, unit in _custom_pairs(rule))
    )


def _custom_pairs(rule):
    """
    (amount, unit) of every custom notice of a rule.

    ---

    S153. (antelación, unidad) de cada aviso personalizado de una
    regla: los dos campos de una regla normal, o todos los de una
    regla combinada (`MergedAlertRule`).
    """
    pairs = getattr(rule, "custom_pairs", None)
    if pairs is not None:
        return pairs
    return (
        (rule.custom_1_value, rule.custom_1_unit),
        (rule.custom_2_value, rule.custom_2_unit),
    )


@dataclass
class MergedAlertRule:
    """
    Notice settings of one document type required by several
    requirements of the same subject.

    ---

    S153. Configuración de avisos de UN tipo que piden VARIOS
    requisitos del mismo sujeto: cada casilla vale si la marca alguno
    de ellos, y los avisos personalizados son todos los de todos, sin
    repetir. Se avisa una vez por documento, nunca una por requisito.
    """

    document_type: object
    notify_missing: bool = False
    notify_30_days: bool = False
    notify_15_days: bool = False
    notify_7_days: bool = False
    notify_day_before: bool = False
    custom_pairs: tuple = ()


def merge_rules(rules):
    """
    One rule for several rules of the same document type.

    ---

    S153. Una sola regla para las de varios requisitos sobre el mismo
    tipo (ver MergedAlertRule). Con una sola, la devuelve tal cual.
    """
    if len(rules) == 1:
        return rules[0]
    pairs = []
    for rule in rules:
        for amount, unit in _custom_pairs(rule):
            if amount and unit and (amount, unit) not in pairs:
                pairs.append((amount, unit))
    return MergedAlertRule(
        document_type=rules[0].document_type,
        notify_missing=any(rule.notify_missing for rule in rules),
        notify_30_days=any(rule.notify_30_days for rule in rules),
        notify_15_days=any(rule.notify_15_days for rule in rules),
        notify_7_days=any(rule.notify_7_days for rule in rules),
        notify_day_before=any(rule.notify_day_before for rule in rules),
        custom_pairs=tuple(pairs),
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


def compute_notices(domain, include_service=False):
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

    Con `include_service` (S131), en centros de gasto se añaden a
    `pending` los avisos de revisión por horas/km
    (`fleet.service_plan_service`), que no dependen del requisito de
    documentación ni de sus avisos.
    """
    pending, scheduled, calendar_items = _compute_document_notices(domain)
    if include_service and domain == DOMAIN_MACHINE:
        from fleet.service_plan_service import compute_service_notices

        pending.extend(compute_service_notices())
        pending.sort(key=_pending_sort_key)
    return pending, scheduled, calendar_items


def _compute_document_notices(domain):
    """
    Document notices of one domain (see compute_notices).

    ---

    Avisos de documentación de un dominio (ver compute_notices).
    """
    from document_explorer.models import (
        DocumentIndexEntry, DocumentTypeCatalog, DrivingLicenceGrant,
        JobPosition,
        PersonIdentity, RequirementAlertRule,
    )
    from fleet.models import MachineAsset

    today = date.today()
    # S153: varios requisitos por sujeto; un requisito desactivado no
    # avisa (S128).
    active_requirements = Prefetch(
        "document_requirements",
        queryset=JobPosition.objects.filter(is_active=True).order_by(
            "name",
        ),
    )
    if domain == DOMAIN_PERSONAL:
        subjects = list(
            PersonIdentity.objects.filter(
                is_active_employee=True,
                document_requirements__is_active=True,
            ).distinct().prefetch_related(active_requirements),
        )
        subject_model = PersonIdentity
    else:
        from document_explorer.models import MachineAlertRule

        # S148: también las máquinas con avisos propios
        # (MachineAlertRule), aunque no tengan requisito.
        own_ids = set(MachineAlertRule.objects.values_list(
            "machine_id", flat=True))
        subjects = list(
            MachineAsset.objects.filter(is_active=True).filter(
                Q(document_requirements__is_active=True)
                | Q(pk__in=own_ids),
            ).distinct().prefetch_related(active_requirements),
        )
        subject_model = MachineAsset
    requirements_of = {
        s.pk: list(s.document_requirements.all()) for s in subjects
    }

    pending, scheduled, calendar_items = [], [], []
    if not subjects:
        return pending, scheduled, calendar_items

    requirement_ids = {
        req.pk for reqs in requirements_of.values() for req in reqs}
    rules = {}
    for rule in RequirementAlertRule.objects.filter(
        job_position_id__in=requirement_ids,
    ).select_related("document_type"):
        rules.setdefault(rule.job_position_id, {})[
            rule.document_type_id
        ] = rule
    # S148: avisos propios de cada máquina; sustituyen a los del
    # requisito para ese tipo.
    own_rules = {}
    if domain != DOMAIN_PERSONAL:
        from document_explorer.models import MachineAlertRule

        for rule in MachineAlertRule.objects.filter(
            machine_id__in=[s.pk for s in subjects],
        ).select_related("document_type"):
            own_rules.setdefault(rule.machine_id, {})[
                rule.document_type_id
            ] = rule
    if not rules and not own_rules:
        return pending, scheduled, calendar_items

    categories_of = {}
    for requirement in JobPosition.objects.filter(
        pk__in=requirement_ids,
    ).prefetch_related("required_driving_categories"):
        categories_of[requirement.pk] = list(
            requirement.required_driving_categories.all(),
        )

    type_ids = {
        type_id for by_type in list(rules.values())
        + list(own_rules.values()) for type_id in by_type
    }
    # S127: subrogaciones y conversiones también cubren el alta.
    cover_ids = set(DocumentTypeCatalog.objects.filter(
        code__in=periods.CONTRACT_COVER_CODES,
    ).exclude(code=periods.CONTRACT_CODE).values_list("pk", flat=True))
    type_ids |= cover_ids
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

    # H30 (S122): altas en la Seguridad Social de cada persona, para
    # exigir un contrato por periodo (employment_period_service).
    altas_by_subject = {}
    if domain == DOMAIN_PERSONAL:
        for entry in DocumentIndexEntry.objects.filter(
            bucket=BUCKET,
            domain_content_type=content_type,
            domain_object_id__in=[s.pk for s in subjects],
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
            document_type__code=periods.ALTA_CODE,
        ):
            altas_by_subject.setdefault(entry.domain_object_id, []).append(
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
        requirements = requirements_of[subject.pk]
        # S153: reglas de todos sus requisitos, juntas por tipo (un
        # aviso por documento, con los requisitos que lo piden).
        rules_by_type, sources_by_type = {}, {}
        for requirement in requirements:
            for type_id, rule in rules.get(requirement.pk, {}).items():
                rules_by_type.setdefault(type_id, []).append(rule)
                sources_by_type.setdefault(type_id, []).append(requirement)
        subject_rules = {
            type_id: merge_rules(group)
            for type_id, group in rules_by_type.items()
        }
        # S148: los avisos propios de la máquina sustituyen a los de
        # sus requisitos para ese tipo.
        for type_id, rule in own_rules.get(subject.pk, {}).items():
            subject_rules[type_id] = rule
            sources_by_type[type_id] = []
        if not subject_rules:
            continue
        entries = entries_by_subject.get(subject.pk, [])
        by_type = {}
        for entry in entries:
            by_type.setdefault(entry.document_type_id, []).append(entry)
        present_codes = {entry.document_type.code for entry in entries}
        has_identity = bool(set(IDENTITY_CODES) & present_codes)
        identity_notified = False
        categories_by_pk = {}
        for requirement in requirements:
            for category in categories_of.get(requirement.pk, []):
                categories_by_pk[category.pk] = category
        categories = sorted(
            categories_by_pk.values(),
            key=lambda category: (category.display_order, category.pk),
        )
        label = _subject_label(subject, domain)
        # H30 (S122): datos del sujeto que usan los ámbitos de avisos
        # de cada supervisor (notice_recipients).
        if domain == DOMAIN_PERSONAL:
            subject_company = subject.employer_company or ""
            subject_family = ""
        else:
            subject_company = subject.company_code or ""
            subject_family = subject.family or ""

        for type_id, rule in subject_rules.items():
            doc_type = rule.document_type
            sources = sources_by_type.get(type_id, [])
            base = {
                "domain": domain,
                "subject_id": subject.pk,
                "subject_label": label,
                "requirement_name": (
                    ", ".join(req.name for req in sources)
                    or "Avisos de la máquina"),
                "requirement_id": sources[0].pk if sources else None,
                "requirement_ids": tuple(req.pk for req in sources),
                "requirement_names": tuple(req.name for req in sources),
                "subject_company": subject_company,
                "subject_family": subject_family,
                "document_label": doc_type.label,
                "document_type_id": type_id,
                "kind": None,
            }
            docs = by_type.get(type_id, [])
            if doc_type.code == periods.CONTRACT_CODE and is_gerencia(
                subject.first_surname, subject.second_surname,
            ):
                # S127 (Miguel Ángel): los socios y administradores de la
                # familia propietaria (ACTIVOS/GERENCIA) no tienen
                # contrato laboral -- exentos.
                continue
            if (
                doc_type.code == periods.CONTRACT_CODE
                and altas_by_subject.get(subject.pk)
            ):
                # H30 (S122): con altas registradas, un contrato POR
                # periodo de contratación, no "tiene o no tiene".
                if rule.notify_missing:
                    covers = docs + [
                        entry for cover_id in cover_ids
                        for entry in by_type.get(cover_id, [])
                    ]
                    pending.extend(_missing_contract_notices(
                        base, altas_by_subject[subject.pk], covers,
                    ))
                continue
            if not docs:
                if doc_type.code in IDENTITY_CODES and has_identity:
                    continue
                if doc_type.code in IDENTITY_CODES:
                    # S127: sin DNI ni NIE salían DOS avisos ("Falta DNI"
                    # y "Falta NIE") para un solo documento que falta.
                    # Uno solo, "DNI o NIE", con el tipo del primero.
                    if identity_notified:
                        continue
                    identity_notified = True
                    base["document_label"] = "DNI o NIE"
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


def _missing_contract_notices(base, altas, contracts):
    """
    One MISSING notice per employment period without a contract.

    ---

    Un aviso de "falta" por cada periodo de contratación (alta) sin
    contrato emparejado a ±15 días -- "Contrato laboral (alta del
    dd/mm/aaaa)".
    """
    built, _undated = periods.build_periods(altas, contracts, [])
    notices_out = []
    # S127 (Miguel Ángel, opción b): solo se pide el contrato del periodo
    # ACTUAL (la última alta); los periodos antiguos ya no avisan -- eran
    # ~30 avisos de contratos de hace años que no se van a conseguir.
    for period in built[-1:]:
        if period.has_contract:
            continue
        period_base = dict(base)
        period_base["document_label"] = "%s (alta del %s)" % (
            base["document_label"], period.start_date.strftime("%d/%m/%Y"),
        )
        notice = DocumentNotice(**period_base)
        notice.kind = KIND_MISSING
        notice.entry_id = period.altas[0].pk
        notices_out.append(notice)
    return notices_out


def _driving_class_notices(base, rule, cards, categories, grants_by_card,
                           today, pending, scheduled, calendar_items):
    """
    Notices of the required driving licence classes of one subject.

    ---

    Avisos de las clases de permiso exigidas de un sujeto, leídas del
    carné más reciente CON matriz (mismo criterio que la ficha), con
    la configuración de avisos de "Carnet de conducir".
    """
    from document_explorer.required_documentation_service import (
        latest_driving_card,
    )

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
