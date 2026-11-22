# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_epis.py
"""
EPIs in the new interface (S163).

---

EPIs en la nueva interfaz (S163), copiado tal cual de
panel/views_documentation_h30.py (EpiTechnicalSheetUploadView,
EpiBatchDeliveryExecuteView, EpiBatchTemplateSaveView/DeleteView),
renombrado, con un aviso por respuesta para Acciones:
- Entregar EPIs a las personas marcadas (o a la abierta): un registro
  por EPI y un documento de entrega por persona en su carpeta, con
  WhatsApp de confirmación.
- Lotes de EPIs (ayuda para marcar varios de golpe): crear, modificar y
  borrar.
- Ficha técnica (o manual) de un EPI del catálogo: subir.
"""
import json
from datetime import date

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views import View

from document_explorer.epi_delivery_document_service import (
    build_epi_delivery_pdf_bytes, resolve_company_fiscal_profile,
)
from document_explorer.index_writer import ensure_folder_chain
from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, EpiDelivery,
    EpiDeliveryBatchTemplate, EpiItemCatalog, PersonIdentity, path_digest,
)
from document_explorer.subject_upload_service import (
    SubjectUploadError, upload_subject_document,
)
from new_ui.docs_core import BUCKET
from new_ui.mixins import SuperuserRequiredMixin as DocsUploadAccessMixin
from spare_parts.gcs_service import upload_bytes
from whatsapp.services import send_epi_delivery_whatsapp_confirmation

EPI_TECHNICAL_SHEETS_ROOT = "_FICHAS_TECNICAS_EPI"


class EpiSheetUploadView(DocsUploadAccessMixin, View):
    """
    H31 (S76, corregido en la misma sesión). POST: sube un manual de
    uso o ficha técnica de UN EPI del catálogo.

    Corrección real: la primera versión de esta vista escribía en un
    campo `EpiItemCatalog.technical_sheet` (FK única) recién creado --
    duplicaba sin saberlo un mecanismo YA EXISTENTE desde H30 S73
    (`DocumentIndexEntry.domain_content_type`/`domain_object_id`
    apuntando a `EpiItemCatalog`, mismo patrón genérico que ya usan
    `PersonIdentity`/`MachineAsset`), que además ya tenía 7 documentos
    reales vinculados (verificado contra BD, S76). El campo nuevo se
    retiró (migración 0065); esta vista ahora escribe sobre el
    mecanismo real. A diferencia de una FK única, este SÍ soporta
    varios documentos por EPI (ficha técnica + declaración de
    conformidad, caso real ya existente) -- cada subida AÑADE un
    documento nuevo, nunca sustituye al anterior (4.12: ni siquiera se
    plantea "sustituir", el archivo real nunca se toca ni se borra).
    """

    def post(self, request, epi_id):
        epi = get_object_or_404(EpiItemCatalog, pk=epi_id)
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Falta el archivo de la ficha técnica.",
                },
                status=400,
            )

        document_type = get_object_or_404(
            DocumentTypeCatalog, code="FICHA_TECNICA_EPI",
        )
        data = uploaded_file.read()
        extension = (
            uploaded_file.name.rsplit(".", 1)[-1].lower()
            if "." in uploaded_file.name else "bin"
        )
        today = timezone.now().date()
        filename = "%s_FICHA_TECNICA_%s_%s.%s" % (
            epi.code,
            today.isoformat(),
            DocumentIndexEntry.objects.count(),
            extension,
        )
        target_folder = "%s/%s" % (EPI_TECHNICAL_SHEETS_ROOT, epi.code)
        ensure_folder_chain(BUCKET, target_folder)
        blob_name = "%s/%s" % (target_folder, filename)
        content_type = (
            "application/pdf"
            if extension == "pdf"
            else "application/octet-stream"
        )
        upload_bytes(BUCKET, blob_name, data, content_type=content_type)

        epi_ct = ContentType.objects.get_for_model(EpiItemCatalog)
        entry = DocumentIndexEntry.objects.create(
            bucket=BUCKET,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            blob_name=blob_name,
            blob_name_hash=path_digest(blob_name),
            parent_path=target_folder,
            parent_path_hash=path_digest(target_folder),
            name=filename,
            size_bytes=len(data),
            content_type=content_type,
            document_type=document_type,
            domain_content_type=epi_ct,
            domain_object_id=epi.pk,
        )
        return JsonResponse(
            {
                "ok": True,
                "technical_sheet": {
                    "id": entry.pk,
                    "url": reverse(
                        "new_ui:document_file", args=[entry.pk]
                    ),
                },
            }
        )


class EpiDeliveryView(DocsUploadAccessMixin, View):
    """
    H31 (S113). POST: entrega real de EPIs -- sustituye a
    `EpiIndividualDeliveryView` (S74) y `EpiMassDeliveryView` (S75),
    unificadas en una sola vista porque el proceso real de la empresa
    es el mismo en los dos casos (una o varias personas, uno o varios
    EPIs a la vez, nunca uno solo): Miguel Ángel, verbatim -- "se
    confecciona un documento a través de una plantilla [...] vienen
    una serie de EPIs [...] el trabajador firma el documento [...] los
    documentos variarán unos de otros dependiendo de a qué personas
    van dirigidos y dependiendo de la lista de EPIs que se les hace
    entrega."

    `person_ids`: una o varias pks (la ficha individual manda una
    sola; la barra de acción masiva del listado, las del casillero).
    `epi_ids`: una o varias pks de `EpiItemCatalog` -- ya vienen
    resueltas por el frontend, sea cual sea el origen (lote con
    casillas desmarcadas, o EPIs sueltos sin lote). Esta vista no sabe
    ni le importa si hubo una `EpiDeliveryBatchTemplate` de por medio
    -- eso es solo una ayuda de UI para rellenar la lista de EPIs más
    rápido, nunca un dato que se persista en el `EpiDelivery`.

    Por cada persona: un `EpiDelivery(extraction_method=MANUAL)` real
    por EPI entregado (igual que las vistas que sustituye), MÁS un
    documento PDF real generado con la relación exacta de EPIs
    entregados a esa persona en este lote concreto (nunca el mismo
    documento para dos personas distintas, ni con X -- una línea de
    texto por EPI, ver `epi_delivery_document_service`), indexado vía
    `upload_subject_document` (mismo mecanismo que cualquier subida
    real -- carpeta real de la persona, nunca la ruta antigua "DOC.
    PERSONAL/ENTREGA EPIS/{año}" de antes de la reorganización de
    H29) como tipo documental EPIS, y enlazado como `source_entry` de
    TODAS las entregas creadas para esa persona en esta misma llamada
    -- así el botón "Ver" de la pestaña EPIs (ya arreglado esta
    sesión) funciona también con estas.

    Encabezado de empresa resuelto por `CompanyFiscalProfile` contra
    `person.employer_company` -- si no hay perfil que case (variante
    de empresa todavía sin confirmar por Miguel Ángel), el documento
    se genera igual, sin esas 3 líneas, nunca bloqueante.

    WhatsApp de confirmación igual de no bloqueante que las vistas que
    sustituye -- un fallo de WhatsApp o de generación del PDF de una
    persona nunca revierte sus entregas ya comprometidas en BD, ni
    afecta al resto del lote.
    """

    def post(self, request):
        person_ids = request.POST.getlist("person_ids")
        epi_ids = request.POST.getlist("epi_ids")
        delivery_date_str = request.POST.get("delivery_date", "")

        if not person_ids:
            return JsonResponse(
                {"ok": False, "error": "No hay ninguna persona seleccionada."},
                status=400,
            )
        if not epi_ids or not delivery_date_str:
            return JsonResponse(
                {
                    "ok": False,
                    "error": (
                        "Selecciona al menos un EPI y la fecha de entrega."
                    ),
                },
                status=400,
            )
        try:
            year, month, day = (int(x) for x in delivery_date_str.split("-"))
            delivery_date = date(year, month, day)
        except ValueError:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Fecha de entrega con formato inválido.",
                },
                status=400,
            )

        epis = list(
            EpiItemCatalog.objects.filter(pk__in=epi_ids, is_active=True)
            .order_by("family", "label"),
        )
        if not epis:
            return JsonResponse(
                {
                    "ok": False,
                    "error": (
                        "Ninguno de los EPIs seleccionados existe o está "
                        "activo."
                    ),
                },
                status=400,
            )
        epi_labels = [epi.label for epi in epis]
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        try:
            epis_document_type = DocumentTypeCatalog.objects.get(code="EPIS")
        except DocumentTypeCatalog.DoesNotExist:
            return JsonResponse(
                {
                    "ok": False,
                    "error": (
                        "El tipo documental EPIS no existe en el catálogo."
                    ),
                },
                status=400,
            )

        created = []
        errors = []
        whatsapp_sent_count = 0
        documents_generated = 0
        for person_id in person_ids:
            try:
                person = PersonIdentity.objects.get(pk=person_id)
            except (PersonIdentity.DoesNotExist, ValueError):
                errors.append(
                    {"person_id": person_id, "error": "Persona no encontrada."}
                )
                continue

            deliveries = [
                EpiDelivery.objects.create(
                    person=person, epi=epi, delivery_date=delivery_date,
                    extraction_method=EpiDelivery.METHOD_MANUAL,
                )
                for epi in epis
            ]

            company_profile = resolve_company_fiscal_profile(
                person.employer_company
            )
            try:
                pdf_bytes = build_epi_delivery_pdf_bytes(
                    person, epi_labels, delivery_date, company_profile,
                )
                subject_label = "%s %s, %s" % (
                    person.first_surname,
                    person.second_surname,
                    person.given_name,
                )
                upload_result = upload_subject_document(
                    subject=person,
                    domain_content_type=person_ct,
                    document_type=epis_document_type,
                    data=pdf_bytes,
                    original_filename="entrega_epis_%s.pdf"
                    % delivery_date.isoformat(),
                    typed_date=None,
                    subject_label=subject_label,
                    uploaded_by=getattr(request.user, "company_user", None),
                )
                entry = upload_result["entry"]
                EpiDelivery.objects.filter(
                    pk__in=[d.pk for d in deliveries],
                ).update(source_entry=entry)
                documents_generated += 1
            except SubjectUploadError as exc:
                errors.append(
                    {
                        "person_id": person.pk,
                        "error": "Entregas registradas, pero el documento "
                        "no se pudo generar: %s" % exc,
                    }
                )

            for delivery in deliveries:
                if send_epi_delivery_whatsapp_confirmation(delivery):
                    whatsapp_sent_count += 1
            created.append({
                "person_id": person.pk,
                "delivery_ids": [d.pk for d in deliveries],
            })

        return JsonResponse({
            "ok": True,
            "created_count": len(created),
            "documents_generated": documents_generated,
            "whatsapp_sent_count": whatsapp_sent_count,
            "created": created,
            "errors": errors,
        })


class EpiBatchSaveView(DocsUploadAccessMixin, View):
    """
    H31 (S113). POST: crea un lote nuevo (sin `template_pk`) o edita
    uno existente -- nombre y la lista completa de EPIs marcados en
    la propia pestaña EPIs (EpiTabFragmentView). Igual que un puesto de
    trabajo, un lote sí puede guardarse sin ningún EPI marcado todavía
    (se puede seguir perfilando después).
    """

    def post(self, request, template_pk=None):
        if template_pk:
            template = get_object_or_404(
                EpiDeliveryBatchTemplate, pk=template_pk
            )
        else:
            template = EpiDeliveryBatchTemplate()

        name = request.POST.get("name", "").strip()
        if not name:
            return JsonResponse(
                {"ok": False, "error": "Falta el nombre del lote."},
                status=400,
            )

        template.name = name
        try:
            template.save()
        except IntegrityError:
            return JsonResponse(
                {"ok": False, "error": "Ya existe un lote con ese nombre."},
                status=400,
            )
        item_ids = request.POST.getlist("item_ids")
        template.items.set(item_ids)

        return JsonResponse({"ok": True, "id": template.pk})


class EpiBatchDeleteView(DocsUploadAccessMixin, View):
    """
    H31 (S113). POST: borra un lote -- nunca toca ningún `EpiDelivery`
    ya registrado (el lote es solo una ayuda de UI, no se referencia
    desde la entrega real).
    """

    def post(self, request, template_pk):
        template = get_object_or_404(EpiDeliveryBatchTemplate, pk=template_pk)
        template.delete()
        return JsonResponse({"ok": True})


# ------------------------------------------------- avisos para Acciones
def _payload(response):
    try:
        return json.loads(response.content or b"{}")
    except ValueError:
        return {}


def _say(response, message):
    data = _payload(response)
    data["message"] = message
    return JsonResponse(data, status=response.status_code)


class NuiEpiDeliveryView(EpiDeliveryView):
    """Entrega de EPIs a los marcados (o a la persona abierta)."""

    def post(self, request):
        request.POST = request.POST.copy()
        people = [v for v in (request.POST.getlist("selected")
                              or request.POST.getlist("person_ids"))
                  if v.isdigit()]
        request.POST.setlist("person_ids", people)
        response = super().post(request)
        data = _payload(response)
        if not data.get("ok"):
            return _say(response, data.get("error") or "Error.")
        message = ("EPIs entregados a %d persona(s); documentos de entrega: "
                   "%d; WhatsApp enviados: %d." % (
                       data["created_count"], data["documents_generated"],
                       data["whatsapp_sent_count"]))
        if data.get("errors"):
            message += " Avisos: %s." % "; ".join(
                e["error"] for e in data["errors"])
        return _say(response, message)


class NuiEpiBatchSaveView(EpiBatchSaveView):
    """Guardar un lote (`batch_pk` vacío: nuevo)."""

    def post(self, request):
        raw = request.POST.get("batch_pk", "")
        response = super().post(request, int(raw) if raw.isdigit() else None)
        data = _payload(response)
        if not data.get("ok"):
            return _say(response, data.get("error") or "Error.")
        return _say(response, "Lote «%s» guardado." % request.POST.get(
            "name", "").strip())


class NuiEpiBatchDeleteView(EpiBatchDeleteView):
    """Borrar el lote elegido."""

    def post(self, request):
        raw = request.POST.get("batch_pk", "")
        if not raw.isdigit():
            return JsonResponse({"ok": False,
                                 "message": "Elige el lote a borrar."},
                                status=400)
        name = EpiDeliveryBatchTemplate.objects.filter(
            pk=raw).values_list("name", flat=True).first() or ""
        response = super().post(request, int(raw))
        return _say(response, "Lote «%s» borrado (las entregas hechas no "
                              "se tocan)." % name)


class NuiEpiSheetUploadView(EpiSheetUploadView):
    """Ficha técnica del EPI marcado (uno)."""

    def post(self, request):
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        if len(ids) != 1:
            return JsonResponse({"ok": False, "message": (
                "Marca un solo EPI en el listado.")}, status=400)
        response = super().post(request, int(ids[0]))
        data = _payload(response)
        if not data.get("ok"):
            return _say(response, data.get("error") or "Error.")
        return _say(response, "Ficha técnica subida.")


def epis_context(section):
    """EPIs y lotes para las acciones de Personal."""
    if section != "per":
        return {}
    groups, order = {}, []
    for epi in EpiItemCatalog.objects.filter(is_active=True).order_by(
            "family", "label"):
        if epi.family not in groups:
            groups[epi.family] = []
            order.append(epi.family)
        groups[epi.family].append((epi.pk, epi.label))
    batches = [
        {"pk": b.pk, "name": b.name,
         "items": ",".join(str(pk) for pk in b.items.values_list(
             "pk", flat=True))}
        for b in EpiDeliveryBatchTemplate.objects.order_by("name")
    ]
    return {
        "epi_groups": [(family, groups[family]) for family in order],
        "epi_batches": batches,
        "nui_today": timezone.localdate().isoformat(),
    }
