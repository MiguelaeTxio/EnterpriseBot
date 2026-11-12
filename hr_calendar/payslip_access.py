# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/payslip_access.py
"""
H24 (S153). Who may see, download and send each payslip batch.

---

Quién ve, descarga y envía cada entrega de nóminas (S153). Miguel
Ángel: "Jerónimo carga, pudiendo enviarlas él mismo o enviándoselas a
un jefe de departamento [...] que ya se encargaría de enviarlas él y de
poder descargarlas para hacer uso de ellas, para subir a plataformas
[...] Tendrá acceso única y exclusivamente Alejandro a todas sin
necesidad de darle permiso en cada carga de carpeta y Jerónimo en cada
carga de carpeta será el que dé el acceso a esa carga para el
supervisor correspondiente".

- Sube entregas quien tiene uno de los roles de nóminas
  (`panel.views_payslips.PAYSLIP_ROLES`).
- Una entrega la ven, descargan y envían: quien la subió, los usuarios
  a los que se la compartió (`PayslipBatchShare`) y quien tiene
  `CompanyUser.payslip_full_access` (Alejandro). Nadie más, tampoco un
  administrador.
- Compartir (dar o quitar acceso) solo quien la subió o quien tiene
  acceso a todas.
- Las nóminas ya archivadas en la ficha del trabajador (confidenciales)
  las abren además los mismos usuarios que ven su entrega
  (`can_open_payslip_entry`, lo usa document_explorer.confidential).
- No son efímeras: la entrega, sus nóminas y sus PDF se quedan en el
  sistema para buscarlas por mes y descargarlas cuando haga falta.
"""
import logging
import os

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

SHARED_TEMPLATE = "payslip_batch_shared"


def has_full_access(company_user):
    """
    True if the user sees every payslip batch.
    ---
    True si el usuario ve todas las entregas (Alejandro).
    """
    return bool(company_user is not None
                and getattr(company_user, "payslip_full_access", False))


def visible_batches(company_user):
    """
    The batches this user may see, download and send.
    ---
    Las entregas que este usuario ve, descarga y envía: las que subió,
    las que le compartieron o, con acceso a todas, todas las de su
    empresa.
    """
    from hr_calendar.models import PayslipBatch

    if company_user is None:
        return PayslipBatch.objects.none()
    batches = PayslipBatch.objects.filter(company=company_user.company)
    if has_full_access(company_user):
        return batches
    return batches.filter(
        Q(created_by=company_user)
        | Q(shares__company_user=company_user),
    ).distinct()


def has_any_batch(company_user):
    """
    True if some batch was shared with this user (or all are visible).
    ---
    True si tiene acceso a todas o le han compartido alguna entrega
    (para dejarle entrar en Nóminas aunque su rol no suba nóminas).
    """
    from hr_calendar.models import PayslipBatchShare

    if company_user is None:
        return False
    return has_full_access(company_user) or PayslipBatchShare.objects.filter(
        company_user=company_user).exists()


def can_share(batch, company_user):
    """
    True if this user may give or remove access to the batch.
    ---
    True si puede dar o quitar acceso a la entrega: quien la subió o
    quien tiene acceso a todas.
    """
    return company_user is not None and (
        batch.created_by_id == company_user.pk
        or has_full_access(company_user))


def can_open_payslip_entry(entry, company_user):
    """
    True if the archived payslip belongs to a batch this user sees.
    ---
    True si la nómina archivada (documento confidencial) es de una
    entrega que este usuario ve.
    """
    from hr_calendar.models import PayslipItem

    if company_user is None:
        return False
    if has_full_access(company_user):
        return PayslipItem.objects.filter(
            entry=entry, batch__company=company_user.company).exists()
    return PayslipItem.objects.filter(entry=entry).filter(
        Q(batch__created_by=company_user)
        | Q(batch__shares__company_user=company_user),
    ).exists()


def share_candidates(company, exclude=None):
    """
    Active users a batch can be shared with (supervisors).
    ---
    Usuarios activos a los que se puede compartir una entrega: los de
    rol de supervisión o administración (jefes de departamento).
    """
    from ivr_config.models import CompanyUser

    roles = (
        CompanyUser.ROLE_ADMIN, CompanyUser.ROLE_ADMIN_SUPERVISOR,
        CompanyUser.ROLE_SUPERVISOR, CompanyUser.ROLE_DOCS_SUPERVISOR,
        CompanyUser.ROLE_ASSIST_SUPERVISOR, CompanyUser.ROLE_WORKSHOPBOSS,
        CompanyUser.ROLE_OFFICE,
    )
    users = CompanyUser.objects.filter(
        company=company, is_active=True, role__in=roles,
    ).select_related("user").order_by("user__first_name", "user__username")
    if exclude is not None:
        users = users.exclude(pk=exclude.pk)
    return list(users)


def user_label(company_user):
    """
    Readable name of a panel user.
    ---
    Nombre legible de un usuario del panel.
    """
    user = company_user.user
    return user.get_full_name() or user.username


def set_shares(batch, users, by):
    """
    Gives access to exactly these users; notifies the new ones if the
    batch is already read. Returns (added, removed) counts.
    ---
    Deja con acceso a la entrega exactamente a estos usuarios. A los
    nuevos se les avisa por WhatsApp si la entrega ya está leída (si
    no, se les avisa al terminar la lectura).
    """
    from hr_calendar.models import PayslipBatch, PayslipBatchShare

    wanted = {user.pk: user for user in users
              if user.pk != batch.created_by_id}
    current = {share.company_user_id: share
               for share in batch.shares.all()}
    removed = [pk for pk in current if pk not in wanted]
    batch.shares.filter(company_user_id__in=removed).delete()
    added = []
    for pk, user in wanted.items():
        if pk not in current:
            added.append(PayslipBatchShare.objects.create(
                batch=batch, company_user=user, granted_by=by))
    if batch.status not in (PayslipBatch.Status.UPLOADING,
                            PayslipBatch.Status.READING,
                            PayslipBatch.Status.CANCELLED):
        for share in added:
            notify_share(share)
    return len(added), len(removed)


def notify_share(share):
    """
    WhatsApp to a user the batch was shared with.
    ---
    Avisa por WhatsApp a quien se le ha compartido la entrega, con el
    enlace al listado. Si no se puede (sin móvil, plantilla sin aprobar
    y fuera de la ventana de 24 h, error de Twilio), queda anotado en
    el acceso y se ve en la pantalla.
    """
    from fleet.refuel_questions import template_approved
    from whatsapp.services import _build_twilio_client
    from whatsapp.window_service import send_notification, window_open

    from document_explorer.models import PersonIdentity
    from hr_calendar import payslip_delivery as pd

    batch = share.batch
    user = share.company_user
    phone = pd._user_phone(user)
    template = pd._template(batch.company, SHARED_TEMPLATE)
    count = batch.items.count()
    uploader = (user_label(batch.created_by) if batch.created_by_id
                else "la empresa")
    text = ("Hola %s. %s le ha dado acceso a una entrega de %d nominas. "
            "Puede revisarlas, descargarlas y enviarlas en el panel: "
            "%s/panel/nominas/?batch=%d"
            % (pd._first_name(user, PersonIdentity.objects.filter(
                company_user=user).first()), uploader, count,
               settings.PLATFORM_BASE_URL, batch.pk))
    error = ""
    if not phone:
        error = "Sin móvil en su ficha ni en su cuenta."
    elif not window_open(batch.company, phone) and (
            template is None or not template_approved(template.content_sid)):
        error = ("La plantilla de WhatsApp %s aún no está aprobada por "
                 "Meta." % SHARED_TEMPLATE)
    if not error:
        try:
            send_notification(
                _build_twilio_client(),
                os.environ.get("TWILIO_WHATSAPP_SENDER", ""),
                batch.company, phone,
                template.content_sid if template else None,
                {"1": pd._first_name(user, PersonIdentity.objects.filter(
                    company_user=user).first()),
                 "2": str(count), "3": "?batch=%d" % batch.pk,
                 "4": uploader},
                text=text,
            )
        except Exception as exc:  # Twilio: se anota y se ve en pantalla.
            error = ("No se ha podido enviar el aviso: %s" % exc)[:255]
    if error:
        share.notify_error = error[:255]
        share.save(update_fields=["notify_error"])
        logger.warning("[nominas] aviso del acceso %s: %s", share.pk, error)
        return False
    share.notified_at = timezone.now()
    share.notify_error = ""
    share.save(update_fields=["notified_at", "notify_error"])
    return True
