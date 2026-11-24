# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/safety_notice_service.py
"""
Notices of fire extinguishers and first-aid kits.

---

Avisos de los extintores y botiquines (S163, 24/11, Miguel Ángel): sus
tres fechas (caducidad, próxima revisión y retimbrado) entran en los
avisos de Centros de gasto como las revisiones: vencida (la fecha ya
pasó) o próxima (en los próximos WARN_DAYS días). Van como avisos de
«revisión» (is_service) para que el WhatsApp diario de los
supervisores los mande con la misma plantilla. Los retirados no avisan.
"""
from datetime import date, timedelta

from django.db.models import Q

WARN_DAYS = 30
BASE_CODES = ("EXTINTOR", "BOTIQUIN")
SAFETY_REQUIREMENT_NAME = "Extintores y botiquines"
DATES = (
    ("expiry_date", "caducidad", "Caduca", "Caducó"),
    ("review_date", "revisión", "Toca revisarlo", "Tocaba revisarlo"),
    ("retimbrado_date", "retimbrado", "Toca retimbrarlo",
     "Tocaba retimbrarlo"),
)


def safety_q(prefix=""):
    """
    Q of the deliveries that are a fire extinguisher or a first-aid kit.

    ---

    Las entregas que son de seguridad (extintor o botiquín) por su EPI.
    """
    return (Q(**{prefix + "epi__label__icontains": "extint"})
            | Q(**{prefix + "epi__label__icontains": "botiqu"})
            | Q(**{prefix + "epi__family__icontains": "extint"})
            | Q(**{prefix + "epi__family__icontains": "botiqu"})
            | Q(**{prefix + "epi__code__in": BASE_CODES}))


def item_label(delivery):
    """«Extintor nº 123» (o sin número)."""
    label = delivery.epi.label
    if delivery.serial_number:
        label += " nº %s" % delivery.serial_number
    return label


def compute_safety_notices(today=None):
    """
    Pending notices of the safety items' dates.

    ---

    Un aviso por fecha vencida o que vence en WARN_DAYS días de cada
    extintor o botiquín en uso de un centro de gasto activo.
    """
    from document_explorer.document_notice_service import (
        DOMAIN_MACHINE, KIND_EXPIRED, KIND_UPCOMING, DocumentNotice,
        _subject_label,
    )
    from document_explorer.models import EpiDelivery

    today = today or date.today()
    limit = today + timedelta(days=WARN_DAYS)
    near = Q()
    for field, _w, _a, _b in DATES:
        near |= Q(**{field + "__lte": limit})
    rows = EpiDelivery.objects.filter(
        safety_q(), near, retired_at__isnull=True,
        destination_machine__is_active=True,
    ).select_related("epi", "destination_machine")
    notices = []
    for row in rows:
        machine = row.destination_machine
        for field, word, future, past in DATES:
            when = getattr(row, field)
            if when is None or when > limit:
                continue
            expired = when < today
            days = abs((when - today).days)
            text = "%s el %s (%s)" % (
                past if expired else future, when.strftime("%d/%m/%Y"),
                ("hace %d días" % days) if expired else (
                    "hoy" if days == 0 else "en %d días" % days))
            notices.append(DocumentNotice(
                domain=DOMAIN_MACHINE,
                subject_id=machine.pk,
                subject_label=_subject_label(machine, DOMAIN_MACHINE),
                requirement_name=SAFETY_REQUIREMENT_NAME,
                document_label="%s (%s)" % (item_label(row), word),
                document_type_id=None,
                kind=KIND_EXPIRED if expired else KIND_UPCOMING,
                subject_company=machine.company_code or "",
                subject_family=machine.family or "",
                is_service=True,
                service_due=when.isoformat(),
                service_text=text,
                safety_delivery_id=row.pk,
            ))
    return notices
