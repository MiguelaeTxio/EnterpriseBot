# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_documentation.py
"""
Vista exclusiva de "Documentación" (H23/H25), separada por completo de
Historial de Máquina y de Centros de gasto -- corrección explícita de
Miguel Ángel en S024 tras una propuesta mal planteada por el modelo en
la misma sesión (ver ENTERPRISEBOT_ATTACHED_MILESTONE_V23.md,
"Corrección de rumbo -- vista de documentación completamente aparte").

Acceso: ÚNICA Y EXCLUSIVAMENTE ADMIN y DOCS_SUPERVISOR, en las DOS
pestañas (Maquinaria y Personal), sin excepción -- DocsUploadAccessMixin
en todas las vistas de este archivo, sin variantes de acceso ampliado.

Alcance funcional (S024, completo): subir documentación (carpeta con
detección automática), vincular manualmente "sin asignar", ver
vigente/archivada (calculado dinámicamente por fechas), borrar
vigente Y archivada (con cuenta atrás de 5s), modificar vigente,
descarga directa por documento (icono, enlace GCS firmado), CRUD de
alertas por documento + panel general, CRUD de plantillas de email,
generación de dossier PDF bajo demanda. (S025) diálogo de sustitución
sustituido por sustitución silenciosa + historial visible -- ver
SubstitutionLogFragmentView.

Cuatro vistas HTMX-friendly, mismo patrón que panel/fleet/list.html
(filtro en vivo hx-get + hx-trigger="input changed delay:300ms"):

  DocumentationHubView              -- GET: página completa (las dos
                                        pestañas con su listado inicial
                                        sin filtro).
  DocumentationMachineListFragmentView  -- GET (HTMX): fragmento del
                                        acordeón de máquinas, filtrado
                                        por búsqueda.
  DocumentationPersonalListFragmentView -- GET (HTMX): fragmento del
                                        acordeón de trabajadores,
                                        filtrado por búsqueda.
  DocumentationMachineDetailFragmentView   -- GET (HTMX): contenido
                                        vigente/archivado de UNA
                                        máquina, cargado perezosamente
                                        al desplegar su accordion-item
                                        (propuesta aprobada en S024).
  DocumentationPersonalDetailFragmentView  -- GET (HTMX): igual, para
                                        UN trabajador.

Vigencia calculada al vuelo con document_management.vigencia_service
(agnóstico de dominio, ver ese módulo) -- NO depende de un campo
is_archived persistido: MachineDocument todavía no tiene ese campo (S021
lo dejó "cerrado" pero nunca se llegó a construir en el modelo -- gap
real detectado al escribir esta vista, ver nota más abajo).
PersonalDocument sí lo tiene (S024) pero tampoco se usa aquí todavía --
se deja para cuando exista una acción real de archivado manual; por
ahora vigente/archivado se computa igual en los dos dominios, por
consistencia.

⚠ GAP DETECTADO EN ESTA SESIÓN (fuera de alcance de este hito, pero
real): MachineDocument.is_archived nunca se implementó pese a que el
anexo H23 (S021, "Decisiones cerradas en S021", punto 2) lo daba por
"pendiente de añadir al modelo". No bloquea esta vista (vigencia_service
calcula vigente/archivado dinámicamente sin necesitar ese campo), pero
si en el futuro se necesita archivado MANUAL persistido (no solo
calculado) para MachineDocument iguial que ya existe en PersonalDocument,
haría falta esa migración -- anotado aquí para no perderlo, se
corregirá cuando toque construir el borrado/archivado manual de esta
misma vista.
"""
import json
import logging
import uuid
from datetime import timedelta

from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.timezone import now
from django.views import View

from ai_services.document_vision_service import parse_iso_date

from document_ingestion.deduplication_service import (
    compute_content_hash,
    find_duplicate,
)
from document_ingestion.entity_matching_service import match_machine_asset_by_filename
from document_ingestion.models import IngestedFile, LearnedDocumentTypeKeyword
from document_ingestion.preflight_discard_service import evaluate_batch
from document_ingestion.tasks import retry_unassigned_routing, route_ingested_files
from document_management.alert_service import (
    DEFAULT_EXPIRY_ALERT_OFFSETS_DAYS,
    send_alert_now,
)
from document_management.models import DocumentAlert, DocumentSubstitutionLog, EmailTemplate
from document_management.pdf_merge_service import EmptyDocumentListError, merge_pdfs
from document_management.vigencia_service import DocumentSnapshot, is_current
from fleet.models import MachineAsset
from ivr_config.models import CompanyUser
from machine_documents.document_classification_service import MANUAL_DOCUMENT_TYPE
from machine_documents.markdown_service import (
    MarkdownConversionError,
    convert_document_to_markdown,
)
from machine_documents.models import MachineDocument
from panel.mixins import DocsUploadAccessMixin, SuperuserRequiredMixin
from personal_documents.models import PersonalDocument
from spare_parts.gcs_service import (
    MACHINE_DOCUMENTS_BUCKET,
    PERSONNEL_DOCUMENTS_BUCKET,
    delete_file,
    download_bytes,
    generate_signed_url,
    upload_bytes,
)

logger = logging.getLogger(__name__)


def _split_current_archived(documents, effective_expiry_attr="expiry_date"):
    """
    Agrupa `documents` (lista de instancias MachineDocument o
    PersonalDocument, YA filtradas a una sola máquina/trabajador y a
    status CLASSIFIED) en (vigentes, archivados), aplicando
    vigencia_service.is_current() por cada document_type por separado
    -- dos documentos de tipos distintos nunca compiten entre sí por
    vigencia (ver vigencia_service, criterio cerrado en H23 S021).

    `effective_expiry_attr` deja elegir qué atributo usar como
    "expiry_date" para vigencia_service -- PersonalDocument necesita
    caer a computed_expiry_date cuando expiry_date está vacío (ver
    PersonalDocument.computed_expiry_date, decisión S022/S024);
    MachineDocument no tiene ese campo, así que siempre usa
    expiry_date tal cual.
    ---
    Groups `documents` (list of MachineDocument or PersonalDocument
    instances, ALREADY filtered to a single machine/worker and to
    status CLASSIFIED) into (current, archived), applying
    vigencia_service.is_current() separately per document_type -- two
    documents of different types never compete against each other for
    currency (see vigencia_service, criterion closed in H23 S021).
    """
    by_type: dict[str, list] = {}
    for doc in documents:
        by_type.setdefault(doc.document_type, []).append(doc)

    current_docs = []
    archived_docs = []

    for _doc_type, docs_of_type in by_type.items():
        snapshots = {}
        for doc in docs_of_type:
            effective_expiry = getattr(doc, effective_expiry_attr, None)
            if (
                effective_expiry is None
                and effective_expiry_attr != "expiry_date"
            ):
                effective_expiry = doc.expiry_date
            snapshots[doc.pk] = DocumentSnapshot(
                identifier=doc.pk,
                expiry_date=effective_expiry,
                issue_date=doc.issue_date,
            )

        for doc in docs_of_type:
            candidate = snapshots[doc.pk]
            siblings = [
                snap for pk, snap in snapshots.items() if pk != doc.pk
            ]
            if is_current(candidate, siblings):
                current_docs.append(doc)
            else:
                archived_docs.append(doc)

    return current_docs, archived_docs


def _resolve_download_url(document, bucket_name: str) -> str:
    """
    Resuelve la URL de descarga (firmada, GCS) de un documento
    CLASSIFIED, o cadena vacía si todavía no tiene gcs_blob_name (en
    cola de procesamiento, o falló la subida a GCS). NUNCA persiste la
    URL -- se genera al vuelo en cada petición (mismo criterio que
    spare_parts.gcs_service.generate_signed_url en el resto del
    proyecto).
    ---
    Resolves the download (signed, GCS) URL of a CLASSIFIED document,
    or an empty string if it doesn't have a gcs_blob_name yet (still
    queued, or the GCS upload failed). NEVER persisted -- generated on
    the fly on every request (same criterion as
    spare_parts.gcs_service.generate_signed_url elsewhere in the
    project).
    """
    return _resolve_blob_download_url(document.gcs_blob_name, bucket_name)


def _resolve_blob_download_url(blob_name: str, bucket_name: str) -> str:
    """
    Igual que _resolve_download_url, pero a partir de un blob_name
    cualquiera en vez de document.gcs_blob_name -- extraída (S025)
    para reutilizarla también con document.markdown_blob_name (botón
    "Descargar Markdown", MachinePageView). Cadena vacía si blob_name
    está vacío.
    """
    if not blob_name:
        return ""
    try:
        return generate_signed_url(bucket_name, blob_name)
    except Exception as exc:
        logger.error(
            "# [_resolve_blob_download_url] Error generando URL "
            "firmada para blob=%s: %s",
            blob_name, exc, exc_info=True,
        )
        return ""


def _unassigned_documents(company, domain: str):
    """
    Devuelve la lista de documentos "sin asignar" (status=UNASSIGNED,
    sin machine_asset/company_user) de un dominio para `company`, con
    download_url ya resuelto. Extraído a helper compartido (S024-bis)
    entre DocumentationHubView (render inicial) y
    UnassignedMachineFragmentView/UnassignedPersonalFragmentView
    (refresco parcial vía HTMX, sin recargar el resto de la página).
    """
    if domain == "machine":
        docs = list(
            MachineDocument.objects
            .filter(
                company=company,
                machine_asset__isnull=True,
                status=MachineDocument.Status.UNASSIGNED,
            )
            .order_by("-created_at")
        )
        bucket_name = MACHINE_DOCUMENTS_BUCKET
    else:
        docs = list(
            PersonalDocument.objects
            .filter(
                company=company,
                company_user__isnull=True,
                status=PersonalDocument.Status.UNASSIGNED,
            )
            .order_by("-created_at")
        )
        bucket_name = PERSONNEL_DOCUMENTS_BUCKET

    for doc in docs:
        doc.download_url = _resolve_download_url(doc, bucket_name)
    return docs


def _batch_status_rows(company, batch_id: str):
    """
    Resuelve el estado EN VIVO de cada archivo de un lote de subida
    (S024-ter) -- una fila por IngestedFile, con su estado real de
    enrutado/clasificación y si sigue en curso (`is_pending`) o ya
    terminó (`is_terminal`). Usado tanto por la respuesta inicial de
    DocumentationFolderUploadView como por el sondeo periódico de
    UploadBatchStatusFragmentView -- misma lógica, un único sitio.

    Estados posibles por fila:
      - "routing"    -- IngestedFile.PENDING_ROUTING, en cola de
                        enrutado (no en curso).
      - "needs_review" -- IngestedFile.NEEDS_REVIEW (terminal).
      - "ingest_error" -- IngestedFile.ERROR (terminal).
      - "classifying" -- ROUTED, el documento resultante sigue PENDING
                        (Gemini todavía no ha respondido).
      - "classified"  -- documento CLASSIFIED (terminal, con
                        subject_label del código/nombre asignado).
      - "unassigned"  -- documento UNASSIGNED (terminal).
      - "doc_error"   -- documento con status=ERROR (terminal).
      - "discarded"   -- ROUTED pero el documento ya no existe (era un
                        documento maestro, descartado tras extraer su
                        contenido -- ver masters_to_discard en
                        machine_documents.tasks/personal_documents.tasks;
                        terminal, no es un fallo).
    """
    rows = []
    ingested_qs = (
        IngestedFile.objects
        .filter(company=company, upload_batch_id=batch_id)
        .order_by("created_at")
    )
    for ingested in ingested_qs:
        row = {
            "ingested": ingested,
            "state": "routing",
            "subject_label": "",
            "is_pending": True,
        }

        if ingested.status == IngestedFile.Status.PENDING_ROUTING:
            row["state"] = "routing"
            row["is_pending"] = True
        elif ingested.status == IngestedFile.Status.NEEDS_REVIEW:
            row["state"] = "needs_review"
            row["is_pending"] = False
        elif ingested.status == IngestedFile.Status.ERROR:
            row["state"] = "ingest_error"
            row["is_pending"] = False
        elif ingested.status == IngestedFile.Status.ROUTED:
            model = _DOMAIN_MODELS.get(
                "machine" if ingested.routed_domain == "MACHINE" else "personal"
            )
            document = (
                model.objects.filter(pk=ingested.routed_document_pk).first()
                if ingested.routed_document_pk else None
            )
            if document is None:
                row["state"] = "discarded"
                row["is_pending"] = False
            elif document.status == model.Status.PENDING:
                row["state"] = "classifying"
                row["is_pending"] = True
            elif document.is_possible_master:
                # Ya clasificado (CLASSIFIED/UNASSIGNED), pero el Paso 2
                # de process_machine_document_batch/
                # process_personal_document_batch todavía no ha
                # resuelto si es un documento maestro de verdad -- NO
                # es terminal. Bug real (Miguel Ángel, captura con
                # "Asignado a A45" para el propio documento maestro):
                # sin esta comprobación, el sondeo veía CLASSIFIED, lo
                # daba por terminado, dejaba de sondear, y nunca
                # llegaba a ver el descarte posterior -- se quedaba
                # mostrando "Asignado" para siempre.
                # is_possible_master se pone a False en cuanto el Paso
                # 2 resuelve el documento (se borra por completo, o se
                # confirma como real) -- señal exacta, no una
                # aproximación por gcs_blob_name.
                row["state"] = "classifying"
                row["is_pending"] = True
            elif document.status == model.Status.CLASSIFIED:
                row["state"] = "classified"
                row["is_pending"] = False
                row["subject_label"] = _subject_label_for(
                    document,
                    "machine" if ingested.routed_domain == "MACHINE" else "personal",
                )
            elif document.status == model.Status.UNASSIGNED:
                row["state"] = "unassigned"
                row["is_pending"] = False
            else:
                row["state"] = "doc_error"
                row["is_pending"] = False
                row["subject_label"] = document.error_message

        rows.append(row)
    return rows


def _render_upload_batch_status(request, batch_id: str, skipped_duplicates: int):
    """
    Renderiza panel/documentation/_upload_batch_status.html -- visor
    en vivo del lote, con `hx-trigger="every 3s"` incluido en la
    plantilla SOLO si queda algún archivo pendiente (sondeo que se
    detiene solo cuando todo el lote ha terminado, patrón estándar de
    HTMX). Compartido entre la respuesta inicial de
    DocumentationFolderUploadView y UploadBatchStatusFragmentView
    (el propio sondeo periódico).

    Mientras el lote siga en curso, la misma respuesta lleva TAMBIÉN
    los "out-of-band swaps" (`hx-swap-oob`, mecanismo nativo de HTMX)
    que refrescan el acordeón de Maquinaria/Personal y los bloques
    "Sin asignar" -- sustituye por completo al botón "Actualizar"
    (Miguel Ángel: "hay que eliminar el botón de actualizar... cuando
    estén cargados los documentos, tienen que ir apareciendo [solos],
    que si no, nunca sabemos, tenemos que seguir dándole al botón").
    Un único sondeo (el del visor de subida) empuja los cuatro
    contenedores a la vez -- no hay pollers independientes por
    contenedor. Se omite por completo en cuanto el lote termina, para
    no seguir refrescando el acordeón sin motivo el resto de la
    sesión.
    """
    company = request.user.company_user.company
    rows = _batch_status_rows(company, batch_id)
    any_pending = any(r["is_pending"] for r in rows)

    # S025, petición explícita de Miguel Ángel: "no sabes por dónde
    # vas... tendríamos que tener... una barra de progreso... del
    # proceso total". El sondeo cada 3s ya existía -- el problema real
    # no era la frecuencia, era la falta de un resumen fijo y legible
    # de "cuánto llevo" frente a la lista de filas, que crece/cambia y
    # se hace difícil de seguir de un vistazo. done_count cuenta
    # cualquier fila is_pending=False (terminal, sea cual sea su
    # estado final -- clasificado, sin asignar, error, descartado...
    # todo cuenta como "ya resuelto" a efectos de progreso).
    total_count = len(rows)
    done_count = sum(1 for r in rows if not r["is_pending"])
    progress_percent = (
        round(done_count / total_count * 100) if total_count else 0
    )

    context = {
        "batch_id": batch_id,
        "rows": rows,
        "any_pending": any_pending,
        "skipped_duplicates": skipped_duplicates,
        "total_count": total_count,
        "done_count": done_count,
        "progress_percent": progress_percent,
    }
    if any_pending:
        context["oob_machines"] = MachineAsset.objects.filter(
            company=company,
        ).order_by("code")
        context["oob_workers"] = CompanyUser.objects.filter(
            company=company,
        ).select_related("user").order_by("user__first_name", "user__last_name")
        context["oob_unassigned_machine_docs"] = _unassigned_documents(company, "machine")
        context["oob_unassigned_personal_docs"] = _unassigned_documents(company, "personal")

    return render(request, "panel/documentation/_upload_batch_status.html", context)


# ---------------------------------------------------------------------------
# CRUD de alertas (S024, a petición explícita de Miguel Ángel: "ese
# CRUD es necesario, así que tenemos que construirlo") -- generico
# sobre las dos apps de dominio, vía el mismo mapa `_DOMAIN_MODELS`
# que usan las vistas de detalle de arriba. document_management NUNCA
# construye interfaz propia (ver su docstring) -- estas vistas viven
# aquí, en la interfaz de Documentación que sí las consume.
# ---------------------------------------------------------------------------

_DOMAIN_MODELS = {
    "machine": MachineDocument,
    "personal": PersonalDocument,
}
_DOMAIN_BUCKETS = {
    "machine": MACHINE_DOCUMENTS_BUCKET,
    "personal": PERSONNEL_DOCUMENTS_BUCKET,
}
_DOMAIN_EXPIRY_ATTR = {
    "machine": "expiry_date",
    "personal": "computed_expiry_date",
}


def _resolve_document(domain: str, pk: int, company):
    """
    Resuelve un MachineDocument o PersonalDocument real por dominio +
    pk, acotado a `company` -- nunca deja acceder a un documento de
    otra empresa. Devuelve None si el dominio no es válido o el
    documento no existe/no pertenece a la empresa.
    """
    model = _DOMAIN_MODELS.get(domain)
    if model is None:
        return None
    return model.objects.filter(pk=pk, company=company).first()


def _subject_label_for(document, domain: str) -> str:
    """
    Mismo criterio de etiqueta de sujeto que ya usan
    machine_documents.tasks/personal_documents.tasks al crear las
    alertas por defecto -- reutilizado aquí para las alertas creadas
    a mano desde el CRUD, para que ambas vías queden con el mismo
    formato.
    """
    if domain == "machine":
        return document.machine_asset.code if document.machine_asset_id else "Sin asignar"
    return (
        (document.company_user.user.get_full_name()
         or document.company_user.user.username)
        if document.company_user_id else "Sin asignar"
    )


class DocumentAlertListFragmentView(DocsUploadAccessMixin, View):
    """
    GET (HTMX): lista las alertas de un documento concreto + un
    formulario compacto para añadir una alerta nueva. Se abre bajo
    demanda desde el botón "Alertas" de cada documento en
    _machine_detail.html/_personal_detail.html -- no viene precargado
    en el listado principal (mismo criterio de carga perezosa que el
    resto de esta interfaz).
    """

    template_name = "panel/documentation/_document_alerts.html"

    def get(self, request, domain, pk):
        company = request.user.company_user.company
        document = _resolve_document(domain, pk, company)
        if document is None:
            raise Http404("Documento no encontrado.")

        content_type = ContentType.objects.get_for_model(document)
        alerts = (
            DocumentAlert.objects
            .filter(content_type=content_type, object_id=document.pk)
            .prefetch_related("contacts__user")
            .order_by("alert_offset_days")
        )
        company_users = (
            CompanyUser.objects
            .filter(company=company)
            .select_related("user")
            .order_by("user__first_name", "user__last_name")
        )

        return render(request, self.template_name, {
            "domain": domain,
            "document": document,
            "alerts": alerts,
            "company_users": company_users,
            "suggested_offsets": DEFAULT_EXPIRY_ALERT_OFFSETS_DAYS,
        })


class DocumentAlertCreateView(DocsUploadAccessMixin, View):
    """
    POST (HTMX): crea una alerta nueva sobre un documento (offset_days
    + contactos elegidos a mano) y devuelve el fragmento de lista
    actualizado. No pasa por create_default_expiry_alerts() (esa
    función es solo para las tres alertas automáticas al clasificar,
    con idempotencia por offset) -- aquí el usuario puede añadir
    cuantas alertas adicionales quiera, incluso con un offset
    repetido, a propósito (p. ej. querer avisar dos veces a 15 días
    con contactos distintos).
    """

    def post(self, request, domain, pk):
        company = request.user.company_user.company
        document = _resolve_document(domain, pk, company)
        if document is None:
            raise Http404("Documento no encontrado.")

        effective_expiry = (
            document.expiry_date if domain == "machine"
            else (document.expiry_date or document.computed_expiry_date)
        )
        if effective_expiry is None:
            messages.error(
                request,
                "Este documento no tiene fecha de caducidad conocida "
                "-- no se puede crear una alerta.",
            )
            return redirect(reverse(
                "panel:documentation_alerts_fragment",
                kwargs={"domain": domain, "pk": document.pk},
            ))

        try:
            offset_days = int(request.POST.get("alert_offset_days", ""))
            if offset_days < 0:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(
                request, "Días de antelación no válidos.",
            )
            return redirect(reverse(
                "panel:documentation_alerts_fragment",
                kwargs={"domain": domain, "pk": document.pk},
            ))

        content_type = ContentType.objects.get_for_model(document)
        alert = DocumentAlert.objects.create(
            content_type=content_type,
            object_id=document.pk,
            document_label=document.display_name,
            subject_label=_subject_label_for(document, domain),
            company=company,
            expiry_date=effective_expiry,
            alert_offset_days=offset_days,
        )
        contact_pks = request.POST.getlist("contacts")
        if contact_pks:
            alert.contacts.set(
                CompanyUser.objects.filter(pk__in=contact_pks, company=company)
            )

        logger.info(
            "# [DocumentAlertCreateView] Alerta #%d creada a mano "
            "para %s #%d (%d días).",
            alert.pk, domain, document.pk, offset_days,
        )
        return redirect(
            reverse(
                "panel:documentation_alerts_fragment",
                kwargs={"domain": domain, "pk": document.pk},
            )
        )


class DocumentAlertUpdateView(DocsUploadAccessMixin, View):
    """
    POST (HTMX): modifica los días de antelación y/o los contactos de
    una alerta ya existente. Si el formulario incluye un campo oculto
    `next`, redirige ahí al terminar (usado por el panel de Alertas,
    S024-bis, para no sacar al usuario de la lista general) -- si no,
    mantiene el comportamiento de siempre (volver al fragmento de
    alertas del documento).
    """

    def post(self, request, alert_pk):
        alert = DocumentAlert.objects.filter(pk=alert_pk).first()
        if alert is None or alert.company_id != request.user.company_user.company_id:
            raise Http404("Alerta no encontrada.")

        try:
            offset_days = int(request.POST.get("alert_offset_days", ""))
            if offset_days < 0:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, "Días de antelación no válidos.")
        else:
            alert.alert_offset_days = offset_days
            alert.save(update_fields=["alert_offset_days"])

        contact_pks = request.POST.getlist("contacts")
        alert.contacts.set(
            CompanyUser.objects.filter(
                pk__in=contact_pks, company=alert.company,
            )
        )

        logger.info(
            "# [DocumentAlertUpdateView] Alerta #%d modificada.",
            alert.pk,
        )

        next_url = request.POST.get("next")
        if next_url:
            return redirect(next_url)
        domain = (
            "machine" if alert.content_type.model == "machinedocument"
            else "personal"
        )
        return redirect(
            reverse(
                "panel:documentation_alerts_fragment",
                kwargs={"domain": domain, "pk": alert.object_id},
            )
        )


class DocumentAlertDeleteView(DocsUploadAccessMixin, View):
    """
    POST (HTMX): borra una alerta. Sin confirmación server-side --
    la confirmación vive en el propio botón del template (JS
    `onsubmit="return confirm(...)"`, mismo patrón ligero que el resto
    del panel para acciones destructivas de poco riesgo). Mismo
    soporte de `next` que DocumentAlertUpdateView.
    """

    def post(self, request, alert_pk):
        alert = DocumentAlert.objects.filter(pk=alert_pk).first()
        if alert is None or alert.company_id != request.user.company_user.company_id:
            raise Http404("Alerta no encontrada.")

        domain = (
            "machine" if alert.content_type.model == "machinedocument"
            else "personal"
        )
        document_pk = alert.object_id
        next_url = request.POST.get("next")
        alert.delete()

        logger.info(
            "# [DocumentAlertDeleteView] Alerta #%s borrada (%s #%d).",
            alert_pk, domain, document_pk,
        )
        if next_url:
            return redirect(next_url)
        return redirect(
            reverse(
                "panel:documentation_alerts_fragment",
                kwargs={"domain": domain, "pk": document_pk},
            )
        )


class DocumentAlertResolveView(DocsUploadAccessMixin, View):
    """
    POST: marca una alerta como RESUELTA a mano (campos ya existían en
    el modelo DocumentAlert desde H26 -- resolved_at/resolved_by/
    resolution_notes -- pero nunca tenían ninguna vía de escritura
    hasta ahora). Pensada para el caso que describió Miguel Ángel: una
    alerta vencida que nunca llegó a enviarse (plantilla de WhatsApp
    sin aprobar, por ejemplo) pero cuyo asunto ya se resolvió por otra
    vía -- se marca resuelta a mano, con una nota opcional.
    """

    def post(self, request, alert_pk):
        alert = DocumentAlert.objects.filter(pk=alert_pk).first()
        if alert is None or alert.company_id != request.user.company_user.company_id:
            raise Http404("Alerta no encontrada.")

        alert.status = DocumentAlert.Status.RESOLVED
        alert.resolved_at = now()
        alert.resolved_by = request.user.company_user
        alert.resolution_notes = request.POST.get("resolution_notes", "").strip()
        alert.save(update_fields=[
            "status", "resolved_at", "resolved_by", "resolution_notes",
        ])

        logger.info(
            "# [DocumentAlertResolveView] Alerta #%d resuelta a mano "
            "por %s.",
            alert.pk, request.user.company_user,
        )
        next_url = request.POST.get("next")
        return redirect(next_url or reverse("panel:documentation_hub"))


def _alerts_dashboard_context(
    request, status_filter: str, send_result: dict | None = None,
    search: str = "",
) -> dict:
    """
    Construye el contexto completo del panel de Alertas -- extraído a
    función (S025) para que tanto AlertsDashboardFragmentView (GET)
    como DocumentAlertSendNowView (POST, envío manual) puedan
    reutilizarlo sin duplicar la lógica de agrupación. `send_result`
    (opcional) inyecta el banner de resultado del envío manual más
    reciente, mostrado una sola vez en la respuesta que lo generó.
    `search` (S025, petición explícita de Miguel Ángel: "búsqueda de
    alertas por máquina... un filtrado por centro de gasto") filtra
    por `subject_label` -- mismo campo denormalizado que ya muestra la
    columna "Sujeto" de la tabla, así que el filtro busca exactamente
    sobre lo que el usuario ve (código de máquina o nombre de
    trabajador), sin tener que resolver el objeto genérico.
    """
    company = request.user.company_user.company

    alerts_qs = (
        DocumentAlert.objects
        .filter(company=company)
        .select_related("content_type")
        .prefetch_related("contacts__user", "resolved_by__user")
    )
    if status_filter in dict(DocumentAlert.Status.choices):
        alerts_qs = alerts_qs.filter(status=status_filter)
    if search:
        alerts_qs = alerts_qs.filter(subject_label__icontains=search)

    today = now().date()
    groups: dict = {}
    group_order: list = []
    for alert in alerts_qs:
        fire_date = alert.expiry_date - timedelta(days=alert.alert_offset_days)
        is_overdue = (
            alert.status == DocumentAlert.Status.PENDING
            and fire_date <= today
        )
        domain = (
            "machine" if alert.content_type.model == "machinedocument"
            else "personal"
        )
        key = (alert.content_type_id, alert.object_id)
        if key not in groups:
            groups[key] = {
                "document_label": alert.document_label,
                "subject_label": alert.subject_label,
                "expiry_date": alert.expiry_date,
                "domain": domain,
                "object_id": alert.object_id,
                "cells": {},
                "has_overdue": False,
                "min_fire_date": fire_date,
            }
            group_order.append(key)
        group = groups[key]
        group["cells"][alert.alert_offset_days] = {
            "alert": alert,
            "fire_date": fire_date,
            "is_overdue": is_overdue,
        }
        if is_overdue:
            group["has_overdue"] = True
        group["min_fire_date"] = min(group["min_fire_date"], fire_date)

    rows = []
    for key in group_order:
        group = groups[key]
        rows.append({
            "document_label": group["document_label"],
            "subject_label": group["subject_label"],
            "expiry_date": group["expiry_date"],
            "domain": group["domain"],
            "object_id": group["object_id"],
            "has_overdue": group["has_overdue"],
            "cells": [
                group["cells"].get(offset)
                for offset in AlertsDashboardFragmentView.OFFSET_COLUMNS
            ],
            "min_fire_date": group["min_fire_date"],
        })

    # Documentos con alguna celda vencida primero, luego por fecha
    # de disparo más próxima -- lo más urgente arriba siempre.
    rows.sort(key=lambda r: (not r["has_overdue"], r["min_fire_date"]))

    overdue_count = sum(
        1 for r in rows for cell in r["cells"]
        if cell is not None and cell["is_overdue"]
    )

    return {
        "rows": rows,
        "offset_columns": AlertsDashboardFragmentView.OFFSET_COLUMNS,
        "status_filter": status_filter,
        "status_choices": DocumentAlert.Status.choices,
        "overdue_count": overdue_count,
        "send_result": send_result,
        "search": search,
    }


class AlertsDashboardFragmentView(DocsUploadAccessMixin, View):
    """
    GET (HTMX): panel general de TODAS las alertas de la empresa
    (los dos dominios juntos), no solo las de un documento concreto --
    lo que faltaba según Miguel Ángel: "no tenemos previsto ver las
    alertas que hay... si se han enviado, si no se han enviado, a
    quién se le envía, cuándo se le van a enviar, las alertas que
    están pasadas [de fecha] que no se han enviado".

    REDISEÑADO S025 (hallazgo real de Miguel Ángel, con captura):
    "el nombre del documento debe aparecer una vez, y tenemos tres
    columnas: 30 días, 15 días, 7 días... si no, vamos a ver una
    cantidad de alertas impresionante cuando es el mismo documento que
    está tres veces". Antes: una fila por DocumentAlert (siempre en
    tríos de 30/15/7 por documento). Ahora: agrupado por documento
    (content_type + object_id) -- una fila por documento, con tres
    celdas (una por offset) en vez de tres filas idénticas salvo el
    offset.

    Calcula fire_date (expiry_date - alert_offset_days, en Python --
    no es un campo de BD) y is_overdue (fire_date ya pasada Y
    status=PENDING) por cada alerta individual antes de agrupar, y
    ordena los documentos con alguna celda vencida primero. Filtro por
    estado vía `status` en query string (PENDING/SENT/RESOLVED/
    ninguno=todas) -- afecta a qué ALERTAS individuales entran en el
    cálculo, así que con un filtro puesto una celda sin alerta que lo
    cumpla queda vacía, no en blanco por error.
    """

    template_name = "panel/documentation/_alerts_dashboard.html"

    # Offsets siempre en este orden en las columnas -- ver
    # document_management.alert_service.DEFAULT_EXPIRY_ALERT_OFFSETS_DAYS.
    OFFSET_COLUMNS = [30, 15, 7]

    def get(self, request):
        status_filter = request.GET.get("status", "")
        search = request.GET.get("search", "").strip()
        context = _alerts_dashboard_context(request, status_filter, search=search)
        return render(request, self.template_name, context)


class DocumentAlertSendNowView(DocsUploadAccessMixin, View):
    """
    POST (HTMX): envío MANUAL inmediato de una alerta concreta (S025,
    petición explícita de Miguel Ángel: "tenemos que tener la
    disponibilidad de lanzar el aviso, la notificación por WhatsApp,
    de forma manual [...] se han subido documentos y ya ha pasado la
    fecha de las notificaciones [...] poder enviar esa notificación").
    Delega en document_management.alert_service.send_alert_now()
    (misma lógica que usa la tarea periódica). Re-renderiza el panel
    de Alertas completo con un banner de resultado (éxito/error) --
    nunca un redirect, para que el feedback sea inmediato dentro del
    propio swap de HTMX, sin depender de Django messages (que no se
    ven en un swap parcial).
    """

    def post(self, request, alert_pk):
        alert = DocumentAlert.objects.filter(pk=alert_pk).first()
        if alert is None or alert.company_id != request.user.company_user.company_id:
            raise Http404("Alerta no encontrada.")

        success, detail = send_alert_now(alert)
        send_result = {"success": success, "detail": detail}

        status_filter = request.POST.get("status_filter", "")
        search = request.POST.get("search", "").strip()
        context = _alerts_dashboard_context(request, status_filter, send_result, search=search)
        return render(
            request, "panel/documentation/_alerts_dashboard.html", context,
        )


class SubstitutionLogFragmentView(DocsUploadAccessMixin, View):
    """
    GET (HTMX): historial de sustituciones silenciosas aplicadas en la
    subida (S025). Corrige el diseño original del anexo H26 sección
    2.4 (diálogo interactivo) -- decisión explícita de Miguel Ángel:
    la sustitución se aplica sin preguntar, y este listado es el
    "log visible" que pidió para la trazabilidad. Alcance actual:
    solo Maquinaria (ver document_management.models.DocumentSubstitutionLog).
    """

    template_name = "panel/documentation/_substitution_log.html"

    def get(self, request):
        company = request.user.company_user.company
        logs = (
            DocumentSubstitutionLog.objects
            .filter(company=company)
            .order_by("-created_at")[:200]
        )
        return render(request, self.template_name, {"logs": logs})


class EmailTemplateListFragmentView(DocsUploadAccessMixin, View):
    """
    GET (HTMX): lista las plantillas de email de la empresa +
    formulario de alta. Resuelve el "pendiente de confirmar su
    ubicación exacta" anotado en document_management/admin.py desde
    S023 -- Miguel Ángel nunca pidió Django admin, pidió "desde la
    misma aplicación"/"desde el panel"; esto es esa vista.
    """

    template_name = "panel/documentation/_email_templates.html"

    def get(self, request):
        company = request.user.company_user.company
        templates = EmailTemplate.objects.filter(
            company=company,
        ).order_by("-is_active", "name")
        return render(request, self.template_name, {
            "templates": templates,
        })


class EmailTemplateSaveView(DocsUploadAccessMixin, View):
    """
    POST: crea una plantilla nueva (sin `template_pk` en el POST) o
    modifica una existente (con `template_pk`) -- un único endpoint
    para las dos operaciones, mismo criterio de simplicidad que el
    resto de formularios de esta interfaz.
    """

    def post(self, request):
        company = request.user.company_user.company
        template_pk = request.POST.get("template_pk", "").strip()

        name = request.POST.get("name", "").strip()
        subject = request.POST.get("subject", "").strip()
        body = request.POST.get("body", "").strip()
        is_active = bool(request.POST.get("is_active"))

        if not name or not subject or not body:
            messages.error(
                request,
                "Nombre, asunto y cuerpo son obligatorios en una "
                "plantilla de email.",
            )
            return redirect(reverse("panel:documentation_email_templates"))

        if template_pk:
            template = EmailTemplate.objects.filter(
                pk=template_pk, company=company,
            ).first()
            if template is None:
                raise Http404("Plantilla no encontrada.")
            template.name = name
            template.subject = subject
            template.body = body
            template.is_active = is_active
            template.save()
            logger.info(
                "# [EmailTemplateSaveView] Plantilla #%d modificada.",
                template.pk,
            )
        else:
            template = EmailTemplate.objects.create(
                company=company, name=name, subject=subject,
                body=body, is_active=is_active,
            )
            logger.info(
                "# [EmailTemplateSaveView] Plantilla #%d creada.",
                template.pk,
            )

        messages.success(request, "Plantilla de email guardada.")
        return redirect(reverse("panel:documentation_email_templates"))


class EmailTemplateDeleteView(DocsUploadAccessMixin, View):
    """POST: borra una plantilla de email."""

    def post(self, request, template_pk):
        company = request.user.company_user.company
        template = EmailTemplate.objects.filter(
            pk=template_pk, company=company,
        ).first()
        if template is None:
            raise Http404("Plantilla no encontrada.")
        template.delete()
        logger.info(
            "# [EmailTemplateDeleteView] Plantilla #%s borrada.",
            template_pk,
        )
        messages.success(request, "Plantilla de email borrada.")
        return redirect(reverse("panel:documentation_email_templates"))


class LearnedKeywordListFragmentView(SuperuserRequiredMixin, View):
    """
    GET (HTMX): lista el diccionario de tipos de documento APRENDIDO
    automáticamente (S026, fase 5) + formulario de alta manual --
    Miguel Ángel: "una vista de listado simple o CRUD para poder
    gestionar el diccionario... poder listar todo ese diccionario...
    aunque luego podamos manualmente decir, no, esto lo quitamos o
    añadimos esto". Mismo patrón que EmailTemplateListFragmentView,
    salvo el acceso: restringido a SuperuserRequiredMixin (S026,
    cierre de sesión, Miguel Ángel explícito: "esta vista debería ser
    visible única y exclusivamente para mi usuario") -- nunca por
    username hardcodeado (antipatrón corregido en S021, ver
    panel/mixins.py), por is_superuser real de Django.
    """

    template_name = "panel/documentation/_learned_keywords.html"

    def get(self, request):
        company = request.user.company_user.company
        keywords = LearnedDocumentTypeKeyword.objects.filter(
            company=company,
        ).order_by("-is_active", "-occurrences", "-last_seen")
        return render(request, self.template_name, {
            "keywords": keywords,
        })


class LearnedKeywordSaveView(SuperuserRequiredMixin, View):
    """
    POST: crea una entrada nueva a mano (sin `keyword_pk`) o modifica
    una existente (con `keyword_pk`) -- un único endpoint para las dos
    operaciones, mismo criterio que EmailTemplateSaveView. Una entrada
    creada a mano nunca lleva `source_filename`/`source_document_type`
    (quedan vacíos -- son trazabilidad de un aprendizaje automático
    real, no aplica a un alta manual).
    """

    def post(self, request):
        company = request.user.company_user.company
        keyword_pk = request.POST.get("keyword_pk", "").strip()

        keyword_text = request.POST.get("keyword", "").strip().upper()
        canonical_group = request.POST.get("canonical_group", "").strip().upper()
        is_active = bool(request.POST.get("is_active"))

        if not keyword_text or not canonical_group:
            messages.error(
                request,
                "La palabra clave y el grupo canónico son obligatorios.",
            )
            return redirect(reverse("panel:documentation_learned_keywords"))

        if keyword_pk:
            entry = LearnedDocumentTypeKeyword.objects.filter(
                pk=keyword_pk, company=company,
            ).first()
            if entry is None:
                raise Http404("Entrada no encontrada.")
            entry.keyword = keyword_text
            entry.canonical_group = canonical_group
            entry.is_active = is_active
            entry.save(update_fields=["keyword", "canonical_group", "is_active"])
            logger.info(
                "# [LearnedKeywordSaveView] Entrada #%d modificada a "
                "mano (%r -> %r).",
                entry.pk, keyword_text, canonical_group,
            )
        else:
            entry, created = LearnedDocumentTypeKeyword.objects.get_or_create(
                company=company, keyword=keyword_text,
                defaults={
                    "canonical_group": canonical_group,
                    "is_active": is_active,
                },
            )
            if not created:
                messages.error(
                    request,
                    f"Ya existe una entrada para «{keyword_text}» -- "
                    f"edítala en vez de crear otra.",
                )
                return redirect(reverse("panel:documentation_learned_keywords"))
            logger.info(
                "# [LearnedKeywordSaveView] Entrada #%d creada a mano "
                "(%r -> %r).",
                entry.pk, keyword_text, canonical_group,
            )

        messages.success(request, "Diccionario de tipos de documento guardado.")
        return redirect(reverse("panel:documentation_learned_keywords"))


class LearnedKeywordDeleteView(SuperuserRequiredMixin, View):
    """POST: borra una entrada del diccionario aprendido."""

    def post(self, request, keyword_pk):
        company = request.user.company_user.company
        entry = LearnedDocumentTypeKeyword.objects.filter(
            pk=keyword_pk, company=company,
        ).first()
        if entry is None:
            raise Http404("Entrada no encontrada.")
        entry.delete()
        logger.info(
            "# [LearnedKeywordDeleteView] Entrada #%s borrada.",
            keyword_pk,
        )
        messages.success(request, "Entrada del diccionario borrada.")
        return redirect(reverse("panel:documentation_learned_keywords"))


class DossierGenerateView(DocsUploadAccessMixin, View):
    """
    POST: genera un dossier combinando documentos y lo deja EN
    TEMPORAL en GCS (nunca en BD, nunca persistido de forma
    permanente) hasta que el usuario confirme -- diseño exacto que
    describió Miguel Ángel: "el dossier se crea y cuando se descarga
    se borra... pasa por un modal en el que se pregunte si se borra o
    no... la única copia que quedará será la de la descarga".

    Selección de documentos SEGÚN EL DOMINIO, también a petición
    explícita de Miguel Ángel -- criterios distintos, no una única
    regla genérica:
      - MACHINE: automático, SIN checkboxes. Toda la documentación
        VIGENTE de la máquina, EXCEPTO los manuales de uso
        (machine_documents.document_classification_service.
        MANUAL_DOCUMENT_TYPE) -- "se envía toda la documentación
        excepto el manual, en un dosier. Y el manual aparte" (el
        manual se sigue descargando suelto, con el enlace de descarga
        normal de cada documento, nunca se mete en el dossier).
      - PERSONAL: manual, vía checkboxes (ver _personal_detail.html) --
        "lo suyo es casillero... seleccionar todo o ir marcando
        casilla".

    No hay una única llamada de "generar y descargar": esta vista solo
    genera y muestra la confirmación (_dossier_confirm.html). La
    descarga real (y el borrado) vive en DossierDownloadView; el
    descarte vive en DossierDiscardView.
    """

    def post(self, request, domain, entity_pk):
        company = request.user.company_user.company
        bucket_name = _DOMAIN_BUCKETS.get(domain)
        if bucket_name is None:
            raise Http404("Dominio no válido.")

        if domain == "machine":
            machine = MachineAsset.objects.filter(
                pk=entity_pk, company=company,
            ).first()
            if machine is None:
                raise Http404("Máquina no encontrada.")
            all_docs = list(
                MachineDocument.objects
                .filter(
                    machine_asset=machine,
                    status=MachineDocument.Status.CLASSIFIED,
                )
                .exclude(document_type=MANUAL_DOCUMENT_TYPE)
                # is_possible_master=True (S025, mismo hallazgo que
                # DocumentationMachineDetailFragmentView) -- un dossier
                # generado mientras un maestro sigue pendiente de
                # resolver podría incluirlo antes de que se descarte.
                .exclude(is_possible_master=True)
            )
            documents, _archived = _split_current_archived(all_docs)
            entity_label = machine.code
        else:
            worker = CompanyUser.objects.filter(
                pk=entity_pk, company=company,
            ).select_related("user").first()
            if worker is None:
                raise Http404("Trabajador no encontrado.")
            selected_pks = request.POST.getlist("document_pks")
            if not selected_pks:
                return render(request, "panel/documentation/_dossier_error.html", {
                    "message": "Selecciona al menos un documento para el dossier.",
                })
            documents = list(
                PersonalDocument.objects
                .filter(
                    pk__in=selected_pks, company_user=worker, company=company,
                )
            )
            entity_label = worker.user.get_full_name() or worker.user.username

        documents = [d for d in documents if d.gcs_blob_name]
        if not documents:
            return render(request, "panel/documentation/_dossier_error.html", {
                "message": (
                    "No hay documentos disponibles para el dossier "
                    "(¿todavía en cola de procesamiento?)."
                ),
            })

        pdf_bytes_list = []
        for document in documents:
            try:
                pdf_bytes_list.append(
                    download_bytes(bucket_name, document.gcs_blob_name)
                )
            except Exception as exc:
                logger.error(
                    "# [DossierGenerateView] Error descargando %s #%d "
                    "(blob=%s): %s",
                    domain, document.pk, document.gcs_blob_name, exc,
                    exc_info=True,
                )

        try:
            merged_bytes = merge_pdfs(pdf_bytes_list)
        except EmptyDocumentListError:
            return render(request, "panel/documentation/_dossier_error.html", {
                "message": (
                    "No se pudo descargar ningún documento seleccionado "
                    "-- dossier no generado."
                ),
            })

        token = uuid.uuid4().hex
        temp_blob_name = f"_dossiers_temporales/{token}.pdf"
        upload_bytes(bucket_name, temp_blob_name, merged_bytes)

        logger.info(
            "# [DossierGenerateView] Dossier temporal %s generado con "
            "%d/%d documento(s) (%s, %s) -- pendiente de confirmación.",
            token, len(pdf_bytes_list), len(documents), domain, entity_label,
        )

        return render(request, "panel/documentation/_dossier_confirm.html", {
            "domain": domain,
            "token": token,
            "entity_label": entity_label,
            "documents": documents,
        })


class DossierDownloadView(DocsUploadAccessMixin, View):
    """
    POST: descarga el dossier temporal confirmado y lo BORRA de GCS en
    la misma petición -- "la única copia que quedará será la de la
    descarga" (Miguel Ángel). Si el token ya no existe (descargado o
    descartado antes), 404 -- nunca hay una segunda copia a la que
    recurrir.
    """

    def post(self, request, domain, token):
        bucket_name = _DOMAIN_BUCKETS.get(domain)
        if bucket_name is None:
            raise Http404("Dominio no válido.")
        blob_name = f"_dossiers_temporales/{token}.pdf"

        try:
            data = download_bytes(bucket_name, blob_name)
        except Exception:
            raise Http404(
                "Este dossier ya no está disponible -- puede que ya se "
                "haya descargado o descartado."
            )
        delete_file(bucket_name, blob_name)

        logger.info(
            "# [DossierDownloadView] Dossier temporal %s descargado y "
            "borrado (%s).",
            token, domain,
        )
        response = HttpResponse(data, content_type="application/pdf")
        response["Content-Disposition"] = (
            'attachment; filename="dossier_documentacion.pdf"'
        )
        return response


class DossierDiscardView(DocsUploadAccessMixin, View):
    """
    POST: descarta el dossier temporal SIN descargarlo -- botón
    "Volver atrás" del modal de confirmación (el usuario quiere
    modificar la selección de documentos antes de descargar de
    verdad).
    """

    def post(self, request, domain, token):
        bucket_name = _DOMAIN_BUCKETS.get(domain)
        if bucket_name is None:
            raise Http404("Dominio no válido.")
        blob_name = f"_dossiers_temporales/{token}.pdf"
        delete_file(bucket_name, blob_name)

        logger.info(
            "# [DossierDiscardView] Dossier temporal %s descartado (%s).",
            token, domain,
        )
        return render(request, "panel/documentation/_dossier_discarded.html")


class RetryUnassignedRoutingView(DocsUploadAccessMixin, View):
    """
    POST: encola document_ingestion.tasks.retry_unassigned_routing
    para TODOS los documentos "sin asignar" de un dominio -- a
    petición de Miguel Ángel tras el bug del prompt de enrutado que
    ignoraba el nombre de archivo (corregido en el commit 28de508):
    "habrá que crear un reenrutado para que vuelva a intentarlo, por
    si hay fallos". Asíncrono (puede implicar varias llamadas a
    Gemini) -- no bloquea la petición.
    """

    def post(self, request, domain):
        company = request.user.company_user.company
        retry_unassigned_routing.delay(domain, company.pk)
        logger.info(
            "# [RetryUnassignedRoutingView] Reenrutado encolado para "
            "%s (%s).",
            domain, company,
        )
        messages.success(
            request,
            "Reintento de enrutado en cola -- puede tardar unos "
            "minutos.",
        )
        fragment_name = (
            "panel:documentation_unassigned_machine" if domain == "machine"
            else "panel:documentation_unassigned_personal"
        )
        return redirect(reverse(fragment_name))


class DocumentationHubView(DocsUploadAccessMixin, View):
    """
    GET: página completa de "Documentación" -- las dos pestañas
    (Maquinaria/Personal), cada una con su listado inicial de
    máquinas/trabajadores sin filtro aplicado. El detalle de cada
    máquina/trabajador se carga después, perezosamente, vía
    DocumentationMachineDetailFragmentView/
    DocumentationPersonalDetailFragmentView.
    """

    template_name = "panel/documentation/hub.html"

    def get(self, request):
        company_user = request.user.company_user
        company = company_user.company

        from django.db.models import Count, Q

        machines = MachineAsset.objects.filter(
            company=company,
        ).annotate(
            incidence_count=Count(
                "documents",
                filter=~Q(documents__content_mismatch_warning=""),
            ),
        ).order_by("code")
        workers = CompanyUser.objects.filter(
            company=company,
        ).select_related("user").order_by("user__first_name", "user__last_name")

        return render(request, self.template_name, {
            "active_nav": "documentation_hub",
            "company_user": company_user,
            "machines": machines,
            "workers": workers,
            "unassigned_machine_docs": _unassigned_documents(company, "machine"),
            "unassigned_personal_docs": _unassigned_documents(company, "personal"),
        })


class UnassignedMachineFragmentView(DocsUploadAccessMixin, View):
    """
    GET (HTMX): bloque "Sin asignar" de Maquinaria, aislado en su
    propio fragmento (S024-bis, "no vamos a estar recargando la
    página") -- se refresca solo tras vincular a mano
    (DocumentAssignView) o encolar un reenrutado
    (RetryUnassignedRoutingView), sin recargar el resto de la página.
    """

    template_name = "panel/documentation/_unassigned_machine.html"

    def get(self, request):
        company = request.user.company_user.company
        return render(request, self.template_name, {
            "unassigned_machine_docs": _unassigned_documents(company, "machine"),
            "machines": MachineAsset.objects.filter(company=company).order_by("code"),
        })


class UnassignedPersonalFragmentView(DocsUploadAccessMixin, View):
    """GET (HTMX): igual que UnassignedMachineFragmentView, para Personal."""

    template_name = "panel/documentation/_unassigned_personal.html"

    def get(self, request):
        company = request.user.company_user.company
        return render(request, self.template_name, {
            "unassigned_personal_docs": _unassigned_documents(company, "personal"),
            "workers": CompanyUser.objects.filter(company=company).select_related("user").order_by("user__first_name", "user__last_name"),
        })


class DocumentationMachineListFragmentView(DocsUploadAccessMixin, View):
    """
    GET (HTMX): fragmento del acordeón de máquinas, filtrado por el
    parámetro `search` (código, matrícula o marca/modelo -- búsqueda
    en vivo, mismo patrón que panel/fleet/list.html).
    """

    template_name = "panel/documentation/_machine_accordion.html"

    def get(self, request):
        company = request.user.company_user.company
        search = request.GET.get("search", "").strip()

        from django.db.models import Count, Q

        machines = MachineAsset.objects.filter(company=company).annotate(
            incidence_count=Count(
                "documents",
                filter=~Q(documents__content_mismatch_warning=""),
            ),
        )
        if search:
            machines = machines.filter(
                Q(code__icontains=search)
                | Q(plate__icontains=search)
                | Q(brand_model__icontains=search)
            )
        machines = machines.order_by("code")

        return render(request, self.template_name, {"machines": machines})


class DocumentationPersonalListFragmentView(DocsUploadAccessMixin, View):
    """
    GET (HTMX): fragmento del acordeón de trabajadores, filtrado por
    el parámetro `search` (nombre o DNI -- búsqueda en vivo).
    """

    template_name = "panel/documentation/_personal_accordion.html"

    def get(self, request):
        company = request.user.company_user.company
        search = request.GET.get("search", "").strip()

        workers = CompanyUser.objects.filter(
            company=company,
        ).select_related("user")
        if search:
            from django.db.models import Q
            workers = workers.filter(
                Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(dni__icontains=search)
            )
        workers = workers.order_by("user__first_name", "user__last_name")

        return render(request, self.template_name, {"workers": workers})


def _machine_documents_view_data(machine):
    """
    Construye (current_docs, archived_docs) de una máquina, con
    download_url (PDF) y markdown_download_url (S025, solo si ya se
    convirtió) resueltos por documento -- extraída de
    DocumentationMachineDetailFragmentView para reutilizarla también
    en MachinePageView (ficha de página completa) sin duplicar la
    consulta ni la exclusión de is_possible_master.
    """
    documents = list(
        MachineDocument.objects
        .filter(
            machine_asset=machine,
            status=MachineDocument.Status.CLASSIFIED,
        )
        # is_possible_master=True (S025, hallazgo real): un
        # documento maestro sigue en CLASSIFIED mientras el Paso 2
        # de process_machine_document_batch no lo ha resuelto
        # todavía (puede acabar borrado, o confirmado como real) --
        # mismo campo que ya protegía al visor de subida en vivo
        # desde S024 (_batch_status_rows), pero nunca se aplicó
        # aquí. Sin esta exclusión, un maestro pendiente de
        # resolver aparecía como documento "vigente" normal en el
        # detalle de la máquina -- más visible con los reintentos
        # reales de Vertex AI (429) de esta sesión, que alargan la
        # ventana de "pendiente" de segundos a varios minutos.
        .exclude(is_possible_master=True)
        .order_by("document_type", "-created_at")
    )
    current_docs, archived_docs = _split_current_archived(documents)

    for doc in current_docs + archived_docs:
        doc.download_url = _resolve_download_url(
            doc, MACHINE_DOCUMENTS_BUCKET,
        )
        doc.markdown_download_url = _resolve_blob_download_url(
            doc.markdown_blob_name, MACHINE_DOCUMENTS_BUCKET,
        )

    return current_docs, archived_docs


class DocumentationMachineDetailFragmentView(DocsUploadAccessMixin, View):
    """
    GET (HTMX): documentación CLASSIFIED de UNA máquina, ya separada
    en vigente/archivada, con URL de descarga resuelta por documento.
    Se carga al desplegar el accordion-item de esa máquina (carga
    perezosa, propuesta aprobada en S024) -- nunca viene en el HTML
    inicial de DocumentationHubView.

    ⚠ NOTA S025: el acordeón que llamaba a esta vista fue sustituido
    por enlaces directos a MachinePageView (ficha de página completa
    con URL propia) -- esta vista ya no está enlazada desde ningún
    sitio de la interfaz, pero se conserva sin borrar por si algún
    flujo antiguo la necesitara todavía (deuda técnica menor, no
    urgente).
    """

    template_name = "panel/documentation/_machine_detail.html"

    def get(self, request, pk):
        company = request.user.company_user.company
        machine = (
            MachineAsset.objects
            .filter(pk=pk, company=company)
            .first()
        )
        if machine is None:
            raise Http404("Máquina no encontrada.")

        current_docs, archived_docs = _machine_documents_view_data(machine)

        return render(request, self.template_name, {
            "machine": machine,
            "current_docs": current_docs,
            "archived_docs": archived_docs,
        })


class MachinePageView(DocsUploadAccessMixin, View):
    """
    GET: ficha de PÁGINA COMPLETA de una máquina/centro de gasto, con
    URL propia (S025, decisión explícita de Miguel Ángel tras detectar
    el problema real del diseño anterior: "cuando entramos presentamos
    la misma página, la documentación... si actualizas la página...
    pierdes el filtro... lo suyo es poder entrar a una vista propia
    para cada máquina"). Sustituye al accordion desplegable
    (_machine_accordion.html ya no expande in-situ, ahora enlaza aquí
    directamente) -- un F5 en esta URL nunca pierde nada, porque no
    depende de ningún estado de UI, todo viene resuelto en la propia
    URL (pk).

    Reúne en una sola pantalla, tal como especificó Miguel Ángel:
    "ya tenemos el visor de esa máquina, las alertas que son de esa
    propia máquina... tendríamos la vista del centro de gasto, con su
    documentación, alertas, etcétera":
      - Documentación vigente/archivada (_machine_documents_view_data,
        misma lógica que el fragmento antiguo).
      - Alertas de ESTA máquina únicamente, reutilizando
        _alerts_dashboard_context() con search=machine.code
        precargado -- nunca se duplica la lógica de agrupación del
        panel general de Alertas, solo se acota su resultado.
      - Botón de generar dossier (ya existente, sin cambios).
      - Conversión a Markdown de manuales (S025, nueva) -- ver
        DocumentMarkdownConvertView.

    La vista general de Documentación (DocumentationHubView) sigue
    siendo el listado con búsqueda y la pestaña de Alertas SIN acotar
    (con su propio filtro por máquina, S025 commit anterior) -- las
    dos vistas conviven, cada una con su propósito: listado cruzado
    filtrable vs. ficha operativa de una máquina concreta.
    """

    template_name = "panel/documentation/machine_page.html"

    def get(self, request, pk):
        company_user = request.user.company_user
        company = company_user.company
        machine = (
            MachineAsset.objects
            .filter(pk=pk, company=company)
            .first()
        )
        if machine is None:
            raise Http404("Máquina no encontrada.")

        current_docs, archived_docs = _machine_documents_view_data(machine)

        alerts_context = _alerts_dashboard_context(
            request, status_filter="", search=machine.code,
        )

        # Botón de resolución por cada máquina distinta implicada en
        # una incidencia de esta máquina (S026, cierre de sesión).
        # Miguel Ángel: "un botón con cada una de las incidencias...
        # pulsando el botón, nos dividirá la pantalla y nos muestra
        # la máquina y la máquina con la que hemos pulsado el botón
        # que tiene incidencia. Se resuelve esa incidencia, desaparece
        # el botón". Se recalcula en cada carga -- en cuanto no quede
        # ningún MachineDocument de esta máquina con esa candidata,
        # el botón deja de aparecer solo, sin ningún estado que
        # mantener a mano.
        from django.db.models import Count

        incidence_machines = list(
            MachineDocument.objects
            .filter(machine_asset=machine)
            .exclude(content_mismatch_candidate_machine__isnull=True)
            .values(
                "content_mismatch_candidate_machine",
                "content_mismatch_candidate_machine__code",
            )
            .annotate(count=Count("pk"))
            .order_by("content_mismatch_candidate_machine__code")
        )

        # Caso distinto (Miguel Ángel, S026): un documento con
        # incidencia (content_mismatch_warning) pero SIN ninguna
        # máquina candidata resuelta -- "no está claro que el
        # documento pertenezca a la máquina. Y tampoco está claro que
        # pertenezca a ninguna otra... aparecería el botón con la
        # leyenda sin asignar". Botón único (no uno por máquina, aquí
        # no hay ninguna candidata) que lleva a la pantalla partida en
        # modo de una sola columna, con selector de máquina por
        # documento.
        unassigned_incidence_count = (
            MachineDocument.objects
            .filter(machine_asset=machine)
            .exclude(content_mismatch_warning="")
            .filter(content_mismatch_candidate_machine__isnull=True)
            .count()
        )

        return render(request, self.template_name, {
            "active_nav": "documentation_hub",
            "company_user": company_user,
            "machine": machine,
            "current_docs": current_docs,
            "archived_docs": archived_docs,
            "unassigned_incidence_count": unassigned_incidence_count,
            "incidence_machines": incidence_machines,
            **alerts_context,
        })


class DocumentMarkdownConvertView(DocsUploadAccessMixin, View):
    """
    POST: convierte un MachineDocument (típicamente un manual de uso
    pesado) a Markdown y lo persiste en GCS -- S025, petición
    explícita de Miguel Ángel (ver machine_documents.markdown_service
    para el detalle completo de la decisión y la librería elegida).
    Idempotente en el sentido de "seguro reintentar": si ya existe
    markdown_blob_name, se sobrescribe con una conversión nueva (por
    si el documento cambió o la primera conversión quedó incompleta).
    Nunca deja que un fallo de conversión reviente como 500 -- se
    captura MarkdownConversionError y se muestra como mensaje legible,
    mismo criterio que send_alert_now (S025).
    """

    def post(self, request, pk):
        company = request.user.company_user.company
        document = MachineDocument.objects.filter(
            pk=pk, company=company,
        ).first()
        if document is None:
            raise Http404("Documento no encontrado.")

        try:
            convert_document_to_markdown(document)
        except MarkdownConversionError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                f'"{document.display_name or document.document_type}" '
                "convertido a Markdown correctamente.",
            )

        redirect_pk = document.machine_asset_id
        return redirect(
            reverse("panel:documentation_machine_page", kwargs={"pk": redirect_pk}),
        )


class DocumentationPersonalDetailFragmentView(DocsUploadAccessMixin, View):
    """
    GET (HTMX): documentación CLASSIFIED de UN trabajador, ya separada
    en vigente/archivada (usando expiry_date o, si está vacío,
    computed_expiry_date -- ver PersonalDocument, S022/S024), con URL
    de descarga resuelta por documento. Carga perezosa, igual que la
    vista de máquina.
    """

    template_name = "panel/documentation/_personal_detail.html"

    def get(self, request, pk):
        company = request.user.company_user.company
        worker = (
            CompanyUser.objects
            .filter(pk=pk, company=company)
            .select_related("user")
            .first()
        )
        if worker is None:
            raise Http404("Trabajador no encontrado.")

        documents = list(
            PersonalDocument.objects
            .filter(
                company_user=worker,
                status=PersonalDocument.Status.CLASSIFIED,
            )
            # is_possible_master=True (S025, mismo hallazgo que
            # DocumentationMachineDetailFragmentView) -- ver el
            # comentario equivalente en esa vista.
            .exclude(is_possible_master=True)
            .order_by("document_type", "-created_at")
        )
        current_docs, archived_docs = _split_current_archived(
            documents, effective_expiry_attr="computed_expiry_date",
        )

        for doc in current_docs + archived_docs:
            doc.download_url = _resolve_download_url(
                doc, PERSONNEL_DOCUMENTS_BUCKET,
            )

        return render(request, self.template_name, {
            "worker": worker,
            "current_docs": current_docs,
            "archived_docs": archived_docs,
        })


class DocumentationPreflightDiscardView(DocsUploadAccessMixin, View):
    """
    POST (fetch JSON, no HTMX): recibe únicamente los NOMBRES de los
    PDF seleccionados (nunca sus bytes -- se llama antes de que el JS
    de hub.html empiece a subir nada) y devuelve las DOS listas
    calculadas por document_ingestion.preflight_discard_service (S026,
    decisión explícita de Miguel Ángel a raíz del incidente real de
    S025: 13 documentos maestros de la A-45 perdidos, que analizados
    uno a uno resultaron ser todos redundantes -- nunca deberían
    haberse llegado a subir). Flujo completo (S026, ampliado en la
    misma sesión tras revisar el primer diseño con Miguel Ángel):
    "leer nombre de archivo -> heurística -> lista de descartados Y de
    no descartados, cada una con el motivo -> el supervisor marca a
    mano archivo por archivo en cualquiera de las dos listas -> sube
    únicamente lo que quede marcado".

    Agrupa los nombres por máquina detectada
    (document_ingestion.entity_matching_service.match_machine_asset_by_filename,
    sin llamar a Gemini) para poder comparar cada candidato contra lo
    YA PERSISTIDO de esa máquina en BD. Los archivos cuya máquina no
    se identifica por nombre se evalúan igualmente contra la REGLA A
    (estructural, no necesita máquina) pero nunca contra la REGLA B
    (obsolescencia de grupo, necesita con qué comparar).

    Cuerpo esperado: {"filenames": ["a.pdf", "b.pdf", ...]}.
    Respuesta: {"discard": [...], "keep": [...]}, cada entrada con
    filename/reason/group/parsed_date -- el frontend decide qué
    marcar por defecto (descartados sin marcar, no descartados
    marcados), pero el supervisor puede cambiar cualquiera de los dos
    en cualquier sentido antes de subir. Nunca crea ni modifica ningún
    registro -- de solo lectura.
    """

    @staticmethod
    def _keep_reason(group, parsed_date):
        if group is None:
            return (
                "Tipo no reconocido por nombre -- se sube para que "
                "Gemini lo clasifique."
            )
        if parsed_date is None:
            return f"Tipo «{group}», sin fecha de caducidad -- se sube siempre."
        return (
            f"Tipo «{group}», fecha {parsed_date.isoformat()} -- el más "
            f"reciente disponible."
        )

    def post(self, request):
        company = request.user.company_user.company
        try:
            payload = json.loads(request.body or b"{}")
        except (ValueError, TypeError):
            return JsonResponse(
                {"error": "Cuerpo JSON inválido."}, status=400,
            )

        filenames = [
            name for name in (payload.get("filenames") or [])
            if isinstance(name, str) and name.lower().endswith(".pdf")
        ]
        if not filenames:
            return JsonResponse({"discard": [], "keep": []})

        # Agrupa por máquina detectada por nombre -- None para los
        # archivos sin máquina identificable (se evalúan igual, solo
        # que sin comparación contra BD, ver evaluate_batch()).
        filenames_by_machine: dict = {}
        for filename in filenames:
            machine = match_machine_asset_by_filename(company, filename)
            filenames_by_machine.setdefault(machine, []).append(filename)

        discard_entries = []
        keep_entries = []
        for machine, machine_filenames in filenames_by_machine.items():
            persisted_documents = (
                list(
                    MachineDocument.objects.filter(
                        machine_asset=machine, company=company,
                    ).exclude(status=MachineDocument.Status.ERROR)
                )
                if machine is not None else []
            )
            verdicts = evaluate_batch(
                machine_filenames,
                machine=machine,
                company=company,
                persisted_documents=persisted_documents,
            )
            for v in verdicts:
                if v.discard:
                    discard_entries.append({
                        "filename": v.filename, "reason": v.reason,
                    })
                else:
                    keep_entries.append({
                        "filename": v.filename,
                        "reason": self._keep_reason(v.group, v.parsed_date),
                    })

        logger.info(
            "# [DocumentationPreflightDiscardView] %d archivo(s) "
            "evaluados, %d descartado(s) / %d no descartado(s) para %s.",
            len(filenames), len(discard_entries), len(keep_entries), company,
        )
        return JsonResponse({"discard": discard_entries, "keep": keep_entries})


class DocumentationFolderUploadView(DocsUploadAccessMixin, View):
    """
    POST: recibe UN TROZO del lote acumulado de una o varias carpetas.
    Desde S024-sexies, el JS del navegador (hub.html) trocea la
    subida en varias peticiones si hace falta -- PythonAnywhere impone
    un límite DURO de 100 MiB por petición HTTP a cualquier aplicación
    web, sin excepción ni siquiera en cuentas de pago (confirmado con
    el foro oficial: "There is a hard limit of 100MiB imposed by us.
    If you want to upload something bigger, you would need your
    frontend code to split it into chunks and upload them
    separately"). Superarlo NO genera ni un error de Django ni un
    traceback -- la conexión se corta antes de que la petición llegue
    a nuestro código (confirmado con log real: dos "OSError: write
    error" sin ninguna traza de esta vista, en el momento exacto en
    que Miguel Ángel subió una carpeta de 121 archivos/112 PDF de la
    A36 -- nunca llegó a crearse ni un solo IngestedFile).

    Cada trozo trae un `batch_id` generado por el JAVASCRIPT del
    navegador (no por esta vista) para que TODOS los trozos de una
    misma subida compartan el mismo lote -- si no viene (compatibilidad
    con llamadas directas sin JS), se genera uno aquí como antes. El
    visor de subida en vivo (UploadBatchStatusFragmentView) no sabe ni
    le importa cuántas peticiones HTTP hicieron falta para completar
    un lote, solo filtra por upload_batch_id.

    Crea una fila IngestedFile por PDF del trozo (status=
    PENDING_ROUTING, rápido, sin llamadas a Gemini) y encola UNA tarea
    document_ingestion.tasks.route_ingested_files por trozo -- mismo
    principio async que el resto de subidas de esta plataforma
    (incidente 2026-07-14, 504 de PythonAnywhere).

    A diferencia de MachineDocumentBatchUploadView (H23, sin tocar):
    aquí NO se elige máquina/trabajador de antemano -- se detecta
    automáticamente por contenido (document_ingestion, S024).
    """

    def post(self, request):
        company = request.user.company_user.company
        company_user = request.user.company_user

        uploaded_files = request.FILES.getlist("folder")
        folder_paths = request.POST.getlist("folder_paths")
        # folder_paths llega en el mismo orden que uploaded_files (ver
        # hub.html, el JS construye ambas listas iterando el mismo
        # array `accumulated`) -- si por lo que sea no coincide en
        # longitud (formulario enviado sin JS, por ejemplo), se ignora
        # en vez de desalinear el resto del lote.
        if len(folder_paths) != len(uploaded_files):
            folder_paths = [""] * len(uploaded_files)

        pdf_files = [
            (f, path) for f, path in zip(uploaded_files, folder_paths)
            if f.name.lower().endswith(".pdf")
        ]
        if not pdf_files:
            return render(request, "panel/documentation/_upload_result.html", {
                "is_error": True,
                "message": "No se encontró ningún PDF en la(s) carpeta(s) seleccionada(s).",
            })

        # batch_id compartido entre trozos (S024-sexies) -- generado
        # por el JS del navegador y reenviado igual en cada trozo. Se
        # genera aquí solo como fallback si llega vacío/ausente.
        batch_id = request.POST.get("batch_id", "").strip() or uuid.uuid4().hex

        # Deduplicación por hash (S024) -- antes de crear cualquier
        # IngestedFile, para no gastar ni la llamada de enrutado ni la
        # de clasificación en un archivo que ya está subido. Mismo
        # criterio que MachineDocumentBatchUploadView: comprueba
        # contra BD (los dos dominios, find_duplicate) y contra el
        # resto de archivos de este mismo lote.
        ingested_pks = []
        skipped_duplicates = 0
        batch_hashes: set[str] = set()
        for uploaded_file, folder_path in pdf_files:
            file_bytes = uploaded_file.read()
            content_hash = compute_content_hash(file_bytes)
            uploaded_file.seek(0)

            if content_hash in batch_hashes or find_duplicate(
                company, content_hash,
            ):
                logger.warning(
                    "# [DocumentationFolderUploadView] %s: ya subido "
                    "(hash %s) -- omitido.",
                    uploaded_file.name, content_hash[:12],
                )
                skipped_duplicates += 1
                continue
            batch_hashes.add(content_hash)

            ingested = IngestedFile(
                company=company,
                uploaded_by=company_user,
                original_filename=uploaded_file.name,
                source_folder_path=folder_path,
                upload_batch_id=batch_id,
                content_hash=content_hash,
                status=IngestedFile.Status.PENDING_ROUTING,
            )
            ingested.source_file.save(
                uploaded_file.name, uploaded_file, save=False,
            )
            ingested.save()
            ingested_pks.append(ingested.pk)

        if not ingested_pks:
            return render(request, "panel/documentation/_upload_result.html", {
                "is_error": True,
                "message": (
                    "Todos los archivos seleccionados ya estaban subidos "
                    "(duplicados por contenido)."
                    if skipped_duplicates else
                    "No se encontró ningún PDF en la(s) carpeta(s) seleccionada(s)."
                ),
            })

        route_ingested_files.delay(ingested_pks)

        logger.info(
            "# [DocumentationFolderUploadView] %d documento(s) en "
            "cola de enrutado para %s, lote=%s, tarea encolada. %d "
            "duplicado(s) omitido(s).",
            len(ingested_pks), company, batch_id, skipped_duplicates,
        )

        return _render_upload_batch_status(request, batch_id, skipped_duplicates)


class UploadBatchStatusFragmentView(DocsUploadAccessMixin, View):
    """
    GET (HTMX): re-renderiza el visor de un lote de subida -- el
    propio `_upload_batch_status.html` se pide a sí mismo cada 3s
    (`hx-trigger="every 3s"`) mientras quede algo pendiente, y deja de
    incluir ese trigger en cuanto todo el lote termina (sondeo que se
    autodetiene, S024-ter).
    """

    def get(self, request, batch_id):
        return _render_upload_batch_status(request, batch_id, skipped_duplicates=0)


class LastUploadBatchFragmentView(DocsUploadAccessMixin, View):
    """
    GET (HTMX): visor de la ÚLTIMA subida de la empresa, accesible
    desde un botón fijo en la cabecera de Documentación (S025,
    petición explícita de Miguel Ángel: "echo en falta... si te sales
    luego no puedes volver a ver el progreso de clasificación...
    pasarlo a un modal y tener acceso a ese modal desde algún botón").
    Solo la ÚLTIMA -- nunca un historial de subidas completo (Miguel
    Ángel: "no vamos a tener un historial de clasificación de
    subidas, simplemente para ver la última").

    IngestedFile.source_file se borra al enrutar, pero la FILA se
    conserva con status=ROUTED (ver document_ingestion.models,
    document_ingestion.tasks.route_ingested_files) -- suficiente para
    reconstruir qué upload_batch_id fue el más reciente sin necesitar
    ningún modelo ni campo nuevo.
    """

    template_name = "panel/documentation/_upload_batch_status.html"

    def get(self, request):
        company = request.user.company_user.company
        last_ingested = (
            IngestedFile.objects
            .filter(company=company)
            .exclude(upload_batch_id="")
            .order_by("-created_at")
            .first()
        )
        if last_ingested is None:
            return render(request, self.template_name, {
                "batch_id": "",
                "rows": [],
                "any_pending": False,
                "skipped_duplicates": 0,
                "no_uploads_yet": True,
            })
        return _render_upload_batch_status(
            request, last_ingested.upload_batch_id, skipped_duplicates=0,
        )


class DocumentAssignView(DocsUploadAccessMixin, View):
    """
    POST: vincula a mano un documento "sin asignar" (machine_asset/
    company_user nulo, status UNASSIGNED) a una máquina o trabajador
    real elegido en el formulario -- pieza pendiente anotada
    explícitamente en el commit 107d8ef ("vincular a mano un documento
    sin asignar... anotado en la interfaz, no prometido como si
    funcionara"), construida ahora a petición de Miguel Ángel.

    Pasa el documento a CLASSIFIED, limpia el hint de detección
    (detected_reference_hint/detected_dni_hint -- ya no hace falta,
    el documento tiene entidad real), y actualiza subject_label en
    cualquier DocumentAlert ya creada para ese documento (las 3
    automáticas se crearon con subject_label="Sin asignar" en su
    momento -- quedarían desactualizadas si no se corrigen aquí).
    """

    def post(self, request, domain):
        company = request.user.company_user.company
        document_pk = request.POST.get("document_pk")
        target_pk = request.POST.get("target_pk")

        document = _resolve_document(domain, document_pk, company)
        if document is None:
            raise Http404("Documento no encontrado.")

        if domain == "machine":
            target = MachineAsset.objects.filter(
                pk=target_pk, company=company,
            ).first()
            if target is None:
                messages.error(request, "Máquina no válida.")
                return redirect(reverse("panel:documentation_unassigned_machine"))
            document.machine_asset = target
            document.detected_reference_hint = ""
            new_subject_label = target.code
        else:
            target = CompanyUser.objects.filter(
                pk=target_pk, company=company,
            ).select_related("user").first()
            if target is None:
                messages.error(request, "Trabajador no válido.")
                return redirect(reverse("panel:documentation_unassigned_personal"))
            document.company_user = target
            document.detected_dni_hint = ""
            new_subject_label = (
                target.user.get_full_name() or target.user.username
            )

        document.status = _DOMAIN_MODELS[domain].Status.CLASSIFIED
        document.save()

        content_type = ContentType.objects.get_for_model(document)
        DocumentAlert.objects.filter(
            content_type=content_type, object_id=document.pk,
        ).update(subject_label=new_subject_label)

        logger.info(
            "# [DocumentAssignView] %s #%d vinculado a mano -> %s.",
            domain, document.pk, new_subject_label,
        )
        messages.success(
            request, f"Documento vinculado a {new_subject_label}.",
        )
        fragment_name = (
            "panel:documentation_unassigned_machine" if domain == "machine"
            else "panel:documentation_unassigned_personal"
        )
        return redirect(reverse(fragment_name))


class DocumentDeleteView(DocsUploadAccessMixin, View):
    """
    POST: borra un documento, vigente O archivado -- a petición
    explícita de Miguel Ángel (S024-quinquies: "sí es necesario que en
    los documentos vigentes también haya un botón de eliminar"). La
    salvaguarda contra el borrado accidental ya no vive aquí en el
    backend (antes, solo se permitía borrar archivados) -- vive en el
    frontend, en el modal de confirmación con cuenta atrás de 5
    segundos (_delete_confirm_modal, hub.html) que antecede a
    cualquier POST a esta vista. Borra el blob de GCS, cualquier
    DocumentAlert asociada, y la fila del documento.
    """

    def post(self, request, domain, pk):
        company = request.user.company_user.company
        document = _resolve_document(domain, pk, company)
        if document is None:
            raise Http404("Documento no encontrado.")

        content_type = ContentType.objects.get_for_model(document)
        DocumentAlert.objects.filter(
            content_type=content_type, object_id=document.pk,
        ).delete()

        if document.gcs_blob_name:
            try:
                delete_file(_DOMAIN_BUCKETS[domain], document.gcs_blob_name)
            except Exception as exc:
                logger.error(
                    "# [DocumentDeleteView] Error borrando blob GCS "
                    "de %s #%d (blob=%s): %s",
                    domain, document.pk, document.gcs_blob_name, exc,
                    exc_info=True,
                )

        entity_pk = (
            document.machine_asset_id if domain == "machine"
            else document.company_user_id
        )
        document_label = document.display_name
        document.delete()

        logger.info(
            "# [DocumentDeleteView] %s #%s (%s) borrado.",
            domain, pk, document_label,
        )
        messages.success(
            request, f"Documento archivado \"{document_label}\" borrado.",
        )
        fragment_name = (
            "panel:documentation_machine_page" if domain == "machine"
            else "panel:documentation_personal_detail"
        )
        return redirect(reverse(fragment_name, kwargs={"pk": entity_pk}))


class DocumentEditFormFragmentView(DocsUploadAccessMixin, View):
    """
    GET (HTMX): formulario de edición de un documento VIGENTE, cargado
    bajo demanda al pulsar el lápiz. Campos comunes a ambos dominios
    (document_type, display_name, expiry_date, issue_date,
    document_number, issuing_entity) + validity_rule/
    computed_expiry_date, solo en personal.
    """

    template_name = "panel/documentation/_document_edit_form.html"

    def get(self, request, domain, pk):
        company = request.user.company_user.company
        document = _resolve_document(domain, pk, company)
        if document is None:
            raise Http404("Documento no encontrado.")

        return render(request, self.template_name, {
            "domain": domain,
            "document": document,
        })


class MachineDocumentTransferView(DocsUploadAccessMixin, View):
    """
    GET: pantalla partida (dos máquinas, una a cada lado) para mover
    documentación mal archivada de una a otra a mano -- Miguel Ángel,
    S026, cierre de sesión: "para resolverlas, poder enviar la
    documentación a otra máquina... dividir la pantalla en dos y
    tener en un lado una máquina y en el otro lado otra, y poder
    pasar de una a otra la documentación que esté marcada como
    errónea". El movimiento NUNCA es automático (ver
    document_ingestion.tasks.route_ingested_files) -- esta es la
    única vía para reasignar un documento de máquina, siempre a mano.

    Las dos máquinas se eligen por querystring (`machine_a`,
    `machine_b`) para poder recargar la página sin perder el
    contexto tras mover un documento.

    Con las DOS máquinas fijas (modo normal, no "sin asignar"), cada
    columna se acota ÚNICAMENTE a los documentos cuya
    content_mismatch_candidate_machine sea justo la OTRA máquina del
    par (S028, hallazgo real de Miguel Ángel: mostrar TODOS los
    documentos de la máquina con un botón fijo "mover a la otra"
    encima de cada uno, aunque la mayoría no tuviera ninguna
    incidencia real con ella, invitaba a mover por error el documento
    equivocado). El modo "sin asignar" (machine_b=None, sin candidata
    fija) es la única excepción -- ahí sí se listan todos los
    documentos de esa máquina, con un selector libre de destino.
    """

    template_name = "panel/documentation/transfer.html"

    def get(self, request):
        company_user = request.user.company_user
        company = company_user.company

        machines = MachineAsset.objects.filter(
            company=company,
        ).order_by("code")

        machine_a_pk = request.GET.get("machine_a", "").strip()
        machine_b_pk = request.GET.get("machine_b", "").strip()
        machine_a = machines.filter(pk=machine_a_pk).first() if machine_a_pk else None
        machine_b = machines.filter(pk=machine_b_pk).first() if machine_b_pk else None

        # Filtrado por candidata específica (S028) -- Miguel Ángel,
        # tras un caso real: la A36 tenía varias incidencias con
        # candidatas DISTINTAS, pero esta pantalla enseñaba TODOS sus
        # documentos con un botón fijo "mover a 58" encima de cada
        # uno, aunque solo UNO de ellos señalaba de verdad a la 58 --
        # "no tiene sentido que pongamos el resto de incidencias y
        # que pongamos que se pueden pasar a la 58, porque no son de
        # la 58... puede tender a error". Con las DOS máquinas fijas
        # (machine_a y machine_b, no el modo "sin asignar"), cada
        # columna se acota a los documentos cuya
        # content_mismatch_candidate_machine sea justo la OTRA
        # máquina del par -- nunca se ofrece mover un documento a una
        # máquina con la que no tiene ninguna incidencia real. El modo
        # "sin asignar" (machine_b=None) no se toca: ahí no hay una
        # única "otra máquina" candidata, sigue mostrando todos los
        # documentos de esa máquina con el selector libre.
        docs_a = (
            MachineDocument.objects.filter(
                machine_asset=machine_a,
            ).exclude(status=MachineDocument.Status.ERROR)
            .order_by("-content_mismatch_warning", "document_type", "-created_at")
            if machine_a else []
        )
        docs_b = (
            MachineDocument.objects.filter(
                machine_asset=machine_b,
            ).exclude(status=MachineDocument.Status.ERROR)
            .order_by("-content_mismatch_warning", "document_type", "-created_at")
            if machine_b else []
        )
        if machine_a and machine_b:
            docs_a = [
                d for d in docs_a
                if d.content_mismatch_candidate_machine_id == machine_b.pk
            ]
            docs_b = [
                d for d in docs_b
                if d.content_mismatch_candidate_machine_id == machine_a.pk
            ]
        # Visor de documento (S028) -- Miguel Ángel, al resolver
        # incidencias reales de la A36: "aquí haría falta un visor de
        # la documentación, porque si no la puedes ver, ¿cómo
        # compruebo manualmente cuál es?". Mismo helper ya usado en
        # MachinePageView/DocumentationHub -- URL firmada de GCS,
        # nunca persistida, generada al vuelo en cada petición.
        for doc in docs_a:
            doc.download_url = _resolve_download_url(doc, MACHINE_DOCUMENTS_BUCKET)
        for doc in docs_b:
            doc.download_url = _resolve_download_url(doc, MACHINE_DOCUMENTS_BUCKET)

        return render(request, self.template_name, {
            "active_nav": "documentation_hub",
            "company_user": company_user,
            "machines": machines,
            "machine_a": machine_a,
            "machine_b": machine_b,
            "docs_a": docs_a,
            "docs_b": docs_b,
        })


class DocumentMoveToMachineView(DocsUploadAccessMixin, View):
    """
    POST: reasigna un MachineDocument a otra máquina -- ÚNICA vía de
    movimiento entre máquinas, siempre a mano (S026). Limpia
    content_mismatch_warning/detected_reference_hint al mover (la
    incidencia queda resuelta con el movimiento manual) y redirige de
    vuelta a MachineDocumentTransferView con las mismas dos máquinas
    en la querystring, para no perder el contexto.
    """

    def post(self, request, pk):
        company = request.user.company_user.company
        document = MachineDocument.objects.filter(
            pk=pk, company=company,
        ).first()
        if document is None:
            raise Http404("Documento no encontrado.")

        target_machine_pk = request.POST.get("target_machine_pk", "").strip()
        target_machine = MachineAsset.objects.filter(
            pk=target_machine_pk, company=company,
        ).first()
        if target_machine is None:
            raise Http404("Máquina de destino no encontrada.")

        origin_label = (
            document.machine_asset.code if document.machine_asset
            else "SIN ASIGNAR"
        )
        document.machine_asset = target_machine
        document.content_mismatch_warning = ""
        document.content_mismatch_candidate_machine = None
        document.detected_reference_hint = ""
        document.status = MachineDocument.Status.CLASSIFIED
        document.save(update_fields=[
            "machine_asset", "content_mismatch_warning",
            "content_mismatch_candidate_machine",
            "detected_reference_hint", "status",
        ])
        logger.info(
            "# [DocumentMoveToMachineView] MachineDocument #%d movido "
            "de %s a %s a mano.",
            document.pk, origin_label, target_machine.code,
        )
        messages.success(
            request,
            f'"{document.display_name or document.document_type}" '
            f"movido de {origin_label} a {target_machine.code}.",
        )

        machine_a = request.POST.get("machine_a", "")
        machine_b = request.POST.get("machine_b", "")
        return redirect(
            f"{reverse('panel:documentation_machine_transfer')}"
            f"?machine_a={machine_a}&machine_b={machine_b}",
        )


class DocumentDismissMismatchView(DocsUploadAccessMixin, View):
    """
    POST: resuelve una incidencia de discrepancia SIN mover el
    documento -- Miguel Ángel (S028), tras revisar a mano un caso
    real: "falta el botón de revocar incidencia, es decir, resolver
    la incidencia porque no existe o porque está bien, y debe de estar
    asignada a la máquina que está asignada". La supervisión humana es
    la última palabra: si la máquina ya asignada es la correcta (falso
    positivo de Gemini, o coincidencia real que el emparejamiento
    automático no supo resolver), esto limpia el aviso sin tocar
    `machine_asset`. Mismos campos que limpia el movimiento
    (DocumentMoveToMachineView) salvo `machine_asset`, que aquí no se
    toca.
    """

    def post(self, request, pk):
        company = request.user.company_user.company
        document = MachineDocument.objects.filter(
            pk=pk, company=company,
        ).first()
        if document is None:
            raise Http404("Documento no encontrado.")

        machine_label = (
            document.machine_asset.code if document.machine_asset
            else "SIN ASIGNAR"
        )
        document.content_mismatch_warning = ""
        document.content_mismatch_candidate_machine = None
        document.detected_reference_hint = ""
        document.status = MachineDocument.Status.CLASSIFIED
        document.save(update_fields=[
            "content_mismatch_warning",
            "content_mismatch_candidate_machine",
            "detected_reference_hint", "status",
        ])
        logger.info(
            "# [DocumentDismissMismatchView] Incidencia de "
            "MachineDocument #%d resuelta a mano SIN mover -- "
            "confirmada la asignación a %s.",
            document.pk, machine_label,
        )
        messages.success(
            request,
            f'"{document.display_name or document.document_type}" '
            f"confirmado como correcto en {machine_label} -- "
            "incidencia resuelta.",
        )

        machine_a = request.POST.get("machine_a", "")
        machine_b = request.POST.get("machine_b", "")
        return redirect(
            f"{reverse('panel:documentation_machine_transfer')}"
            f"?machine_a={machine_a}&machine_b={machine_b}",
        )


class DocumentUpdateView(DocsUploadAccessMixin, View):
    """
    POST: guarda la edición de un documento vigente. Si expiry_date
    (o, en personal, expiry_date/computed_expiry_date) cambia, corrige
    también el expiry_date denormalizado de cualquier DocumentAlert ya
    creada para ese documento -- si no, las alertas seguirían
    disparándose contra la fecha vieja.
    """

    def post(self, request, domain, pk):
        company = request.user.company_user.company
        document = _resolve_document(domain, pk, company)
        if document is None:
            raise Http404("Documento no encontrado.")

        document.document_type = request.POST.get(
            "document_type", document.document_type,
        ).strip()
        document.display_name = request.POST.get(
            "display_name", document.display_name,
        ).strip()
        document.issuing_entity = request.POST.get(
            "issuing_entity", document.issuing_entity,
        ).strip()
        document.document_number = request.POST.get(
            "document_number", document.document_number,
        ).strip()

        for date_field in ("expiry_date", "issue_date"):
            raw_value = request.POST.get(date_field, "").strip()
            setattr(
                document, date_field,
                parse_iso_date(raw_value) if raw_value else None,
            )
        if domain == "personal":
            document.validity_rule = request.POST.get(
                "validity_rule", document.validity_rule,
            ).strip()
            raw_computed = request.POST.get(
                "computed_expiry_date", "",
            ).strip()
            document.computed_expiry_date = (
                parse_iso_date(raw_computed) if raw_computed else None
            )

        document.save()

        effective_expiry = getattr(
            document, _DOMAIN_EXPIRY_ATTR[domain], None,
        ) or document.expiry_date
        content_type = ContentType.objects.get_for_model(document)
        if effective_expiry is not None:
            DocumentAlert.objects.filter(
                content_type=content_type, object_id=document.pk,
            ).update(
                expiry_date=effective_expiry,
                document_label=document.display_name,
            )

        logger.info(
            "# [DocumentUpdateView] %s #%d modificado a mano.",
            domain, document.pk,
        )
        messages.success(request, "Documento actualizado.")
        entity_pk = (
            document.machine_asset_id if domain == "machine"
            else document.company_user_id
        )
        fragment_name = (
            "panel:documentation_machine_page" if domain == "machine"
            else "panel:documentation_personal_detail"
        )
        return redirect(reverse(fragment_name, kwargs={"pk": entity_pk}))
