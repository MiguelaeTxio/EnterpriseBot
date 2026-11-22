# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_notify.py
"""
Ask workers for documents and notify circulars, new interface (S163).

---

Pedir documentos y avisar (circulares) en la nueva interfaz (S163),
copiado de la interfaz antigua (panel/views_doc_requests.py y
PersonalNotification*View de panel/views_documentation_h30.py):
- Pedir documentos por WhatsApp a los marcados (cualquier tipo de
  Personal; uno activo por trabajador y el resto en cola) y cancelar lo
  pedido (todo o los tipos elegidos).
- Cancelar peticiones marcadas en Documentos › Pedir documentos.
- Avisar de una circular a los marcados: por WhatsApp («Leer aquí»,
  queda en Mi buzón) o en correos (.eml, uno por persona, en un ZIP).
Cada aviso enviado deja su acuse (DocumentAcknowledgment), como allí.
"""
import io
import json
import zipfile
from email.message import EmailMessage as StdEmailMessage
from email.utils import make_msgid

from django.contrib.staticfiles.finders import find as find_static
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views import View

from document_explorer.models import (
    DocumentAcknowledgment, DocumentTypeCatalog, PersonIdentity,
    WorkerDocumentRequest,
)
from new_ui.eml_utils import eml_bytes
from new_ui.mixins import SuperuserRequiredMixin


def _ok(message, **extra):
    return JsonResponse({"ok": True, "message": message, **extra})


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


def _people(request):
    company = request.user.company_user.company
    ids = [int(v) for v in request.POST.getlist("selected") if v.isdigit()]
    return list(PersonIdentity.objects.filter(
        Q(company=company) | Q(company__isnull=True), pk__in=ids))


def _label(person):
    return "%s %s" % (person.given_name, person.first_surname)


def notify_context(section):
    """
    Context: Personal types to ask for, and circulars to notify.

    ---

    Personal: los tipos que se pueden pedir (de Personal y de los dos,
    sin subtipos, por familia) y las circulares que se pueden avisar.
    """
    if section != "per":
        return {}
    groups, order = {}, []
    for dt in DocumentTypeCatalog.objects.filter(
        is_active=True, parent_type__isnull=True,
        domain__in=(DocumentTypeCatalog.DOMAIN_PERSONAL,
                    DocumentTypeCatalog.DOMAIN_BOTH),
    ).order_by("family", "label"):
        title = DocumentTypeCatalog.family_label(
            dt.family, for_person=True) if dt.family else "Otros"
        if title not in groups:
            groups[title] = []
            order.append(title)
        groups[title].append((dt.pk, dt.label))
    return {
        "ask_types": [(title, groups[title]) for title in order],
        "nui_circulars": list(DocumentTypeCatalog.objects.filter(
            is_active=True, is_notification_template=True,
        ).order_by("label").values_list("code", "label")),
    }


# -------------------------------------------------------- pedir documentos
class DocRequestSendView(SuperuserRequiredMixin, View):
    """
    POST: ask the marked workers for the chosen documents by WhatsApp.

    ---

    POST: pide por WhatsApp a los marcados los documentos elegidos
    (cualquier tipo); se encolan y se envía el primero de cada uno que
    no tenga ya uno activo. El aviso dice cuántos, cuántos en cola y lo
    descartado o no enviado, con el porqué.
    """

    def post(self, request):
        from document_explorer.worker_request_service import create_requests

        people = _people(request)
        type_ids = [int(v) for v in request.POST.getlist("type_ids")
                    if v.isdigit()]
        types = list(DocumentTypeCatalog.objects.filter(
            pk__in=type_ids, is_active=True))
        if not people or not types:
            return _error("Marca algún trabajador y elige algún documento.")
        summary = create_requests(
            [(p.pk, t.pk) for p in people for t in types],
            request.user.company_user, any_type=True)
        lines = ["Peticiones nuevas: %d; enviadas ahora por WhatsApp: %d."
                 % (summary["queued"], summary["sent"])]
        if summary["queued"] > summary["sent"]:
            lines.append("El resto queda en cola: se pide cuando entregue "
                         "el anterior.")
        lines.extend("No enviado: %s." % e for e in summary["send_errors"])
        lines.extend("Descartado: %s." % e for e in summary["skipped"])
        if not summary["queued"]:
            return _error(" ".join(lines))
        return _ok(" ".join(lines))


def _cancel(requests_qs):
    from document_explorer.worker_request_service import cancel_request

    # Primero la cola y luego los activos: así no se envía un siguiente
    # que también se va a cancelar.
    items = sorted(requests_qs, key=lambda r: (
        r.status == WorkerDocumentRequest.STATUS_SENT, r.pk))
    for item in items:
        cancel_request(item)
    return len(items)


class DocRequestCancelView(SuperuserRequiredMixin, View):
    """
    POST: cancel what the marked workers have been asked for.

    ---

    POST: cancela lo pedido a los marcados: los tipos elegidos o, sin
    ninguno, todo lo que tengan pedido o en cola. Si se cancela el
    activo, se envía el siguiente de su cola.
    """

    def post(self, request):
        people = _people(request)
        if not people:
            return _error("Marca algún trabajador.")
        open_requests = WorkerDocumentRequest.objects.filter(
            person__in=people,
            status__in=WorkerDocumentRequest.OPEN_STATUSES)
        type_ids = [v for v in request.POST.getlist("type_ids")
                    if v.isdigit()]
        if type_ids:
            open_requests = open_requests.filter(document_type_id__in=type_ids)
        count = _cancel(open_requests)
        if not count:
            return _error("No había nada pedido que cancelar.")
        return _ok("Cancelados %d pedidos." % count)


class DocRequestCancelRowsView(SuperuserRequiredMixin, View):
    """
    POST `selected`: cancel the marked requests (Documentos › Pedir).

    ---

    POST: cancela las peticiones marcadas en Documentos › Pedir
    documentos (solo las que siguen abiertas).
    """

    def post(self, request):
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        count = _cancel(WorkerDocumentRequest.objects.filter(
            pk__in=ids, status__in=WorkerDocumentRequest.OPEN_STATUSES))
        if not count:
            return _error("Ninguna de las marcadas sigue abierta.")
        return _ok("Cancelados %d pedidos." % count)


# ----------------------------------------------------------------- avisar
class NotifyError(Exception):
    """Expected failure of one notification (no content, no e-mail)."""


def notification_eml(person, document_type):
    """
    The `.eml` of one circular for one person. Returns (bytes, name).

    ---

    El `.eml` de una circular para una persona: su contenido con el
    logo incrustado, dirigido a su correo. Lanza NotifyError si la
    circular no tiene contenido o la persona no tiene correo.
    """
    if not (document_type.content_html or "").strip():
        raise NotifyError("La circular «%s» todavía no tiene contenido."
                          % document_type.label)
    recipient = (person.email or "").strip()
    if not recipient:
        raise NotifyError("%s no tiene correo." % _label(person))
    msg = StdEmailMessage()
    msg["Subject"] = "%s -- %s" % (document_type.label, person)
    msg["From"] = "notificaciones@grupoalvarez.local"
    msg["To"] = recipient
    msg.set_content(
        "Notificación para %s: %s.\nEste cliente de correo no muestra "
        "HTML -- abra este mensaje con un cliente compatible."
        % (person, document_type.label))
    logo_cid = make_msgid()
    msg.add_alternative(
        f"""
        <html><body style="font-family: Arial, sans-serif;">
          <p style="margin-bottom:16px;">
            <img src="cid:{logo_cid[1:-1]}" alt="Grupo Álvarez" height="40">
          </p>
          <p>Estimado/a <strong>{person}</strong>,</p>
          {document_type.content_html}
          <p style="margin-top:24px;">Un saludo,<br>Grupo Álvarez</p>
        </body></html>
        """, subtype="html")
    logo_path = find_static("new_ui/img/grupo_alvarez_logo_color.png")
    if logo_path:
        with open(logo_path, "rb") as logo_file:
            msg.get_payload()[1].add_related(
                logo_file.read(), "image", "png", cid=logo_cid)
    name = "notificacion_%s_%s.eml" % (document_type.code.lower(), person.pk)
    return eml_bytes(msg), name


def _circular(request):
    return DocumentTypeCatalog.objects.filter(
        code=request.POST.get("tipo", "").strip(), is_active=True).first()


class NotifyEmailView(SuperuserRequiredMixin, View):
    """
    POST: one `.eml` per marked person with the circular, in a ZIP.

    ---

    POST: un correo (.eml) por persona marcada con la circular, todos en
    un ZIP para descargar; a quien le llega se le deja el acuse. Quien
    no tiene correo queda fuera y se avisa.
    """

    def post(self, request):
        people = _people(request)
        document_type = _circular(request)
        if not people or document_type is None:
            return _error("Marca a alguien y elige la circular.")
        buffer = io.BytesIO()
        created, errors = 0, []
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for person in people:
                try:
                    data, name = notification_eml(person, document_type)
                except NotifyError as exc:
                    errors.append(str(exc))
                    continue
                zf.writestr(name, data)
                DocumentAcknowledgment.objects.create(
                    person=person, document_type=document_type,
                    delivery_date=timezone.localdate(),
                    extraction_method=DocumentAcknowledgment.METHOD_MANUAL)
                created += 1
        if not created:
            return _error("Ningún correo generado: %s" % " ".join(errors))
        message = "%d correo(s) de «%s» en el ZIP." % (
            created, document_type.label)
        if errors:
            message += " Fuera: %s" % " ".join(errors)
        response = HttpResponse(buffer.getvalue(),
                                content_type="application/zip")
        response["Content-Disposition"] = (
            'attachment; filename="notificaciones_%s_%s.zip"' % (
                document_type.code.lower(),
                timezone.localdate().isoformat()))
        response["X-Nui-Message"] = json.dumps(message)
        return response


class NotifyWhatsAppView(SuperuserRequiredMixin, View):
    """
    POST: send one circular by WhatsApp to the marked persons.

    ---

    POST: manda la circular por WhatsApp a los marcados (plantilla con
    «Leer aquí»: le contesta con el texto y la da por leída; también la
    ve en Mi buzón). Solo al teléfono de empresa. Cada envío correcto
    deja su acuse por WhatsApp; si falla, se dice de quién.
    """

    def post(self, request):
        from document_explorer.person_phone_service import mobile_of
        from whatsapp.services import send_circular_notification_whatsapp

        people = _people(request)
        document_type = _circular(request)
        if not people or document_type is None:
            return _error("Marca a alguien y elige la circular.")
        sent, errors = 0, []
        for person in people:
            if not mobile_of(person):
                errors.append("%s: sin teléfono de empresa." % _label(person))
                continue
            ack = DocumentAcknowledgment.objects.create(
                person=person, document_type=document_type,
                delivery_date=timezone.localdate(),
                extraction_method=DocumentAcknowledgment.METHOD_MANUAL,
                channel=DocumentAcknowledgment.CHANNEL_WHATSAPP)
            if send_circular_notification_whatsapp(ack):
                sent += 1
            else:
                ack.delete()
                errors.append("%s: no se ha podido enviar." % _label(person))
        message = "«%s» enviada por WhatsApp a %d persona(s)." % (
            document_type.label, sent)
        if errors:
            message += " No enviada: %s" % " ".join(errors)
        if not sent:
            return _error(message)
        return _ok(message)
