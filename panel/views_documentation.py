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

Alcance funcional (S024): subir documentación, descargar documentación,
ver vigente, ver archivada, borrar archivada, modificar vigente. Este
commit construye el LISTADO (ver vigente/archivada + descarga) -- subir
desde esta vista nueva, borrar archivada y modificar vigente quedan
para los siguientes pasos de la hoja de ruta (subida de carpeta en
lote, según lo acordado con Miguel Ángel). La subida de una sola
máquina ya construida en H23 (MachineDocumentBatchUploadView) sigue
existiendo tal cual, sin relación con esta vista.

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
import logging

from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from document_ingestion.deduplication_service import (
    compute_content_hash,
    find_duplicate,
)
from document_ingestion.models import IngestedFile
from document_ingestion.tasks import route_ingested_files
from document_management.alert_service import DEFAULT_EXPIRY_ALERT_OFFSETS_DAYS
from document_management.models import DocumentAlert
from document_management.vigencia_service import DocumentSnapshot, is_current
from fleet.models import MachineAsset
from ivr_config.models import CompanyUser
from machine_documents.models import MachineDocument
from panel.mixins import DocsUploadAccessMixin
from personal_documents.models import PersonalDocument
from spare_parts.gcs_service import (
    MACHINE_DOCUMENTS_BUCKET,
    PERSONNEL_DOCUMENTS_BUCKET,
    generate_signed_url,
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
    if not document.gcs_blob_name:
        return ""
    try:
        return generate_signed_url(bucket_name, document.gcs_blob_name)
    except Exception as exc:
        logger.error(
            "# [_resolve_download_url] Error generando URL firmada "
            "para %s (blob=%s): %s",
            document, document.gcs_blob_name, exc, exc_info=True,
        )
        return ""


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
            return redirect(reverse("panel:documentation_hub"))

        try:
            offset_days = int(request.POST.get("alert_offset_days", ""))
            if offset_days < 0:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(
                request, "Días de antelación no válidos.",
            )
            return redirect(reverse("panel:documentation_hub"))

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
    una alerta ya existente.
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
    del panel para acciones destructivas de poco riesgo).
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
        alert.delete()

        logger.info(
            "# [DocumentAlertDeleteView] Alerta #%s borrada (%s #%d).",
            alert_pk, domain, document_pk,
        )
        return redirect(
            reverse(
                "panel:documentation_alerts_fragment",
                kwargs={"domain": domain, "pk": document_pk},
            )
        )


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

        machines = MachineAsset.objects.filter(
            company=company,
        ).order_by("code")
        workers = CompanyUser.objects.filter(
            company=company,
        ).select_related("user").order_by("user__first_name", "user__last_name")

        unassigned_machine_docs = list(
            MachineDocument.objects
            .filter(
                company=company,
                machine_asset__isnull=True,
                status=MachineDocument.Status.UNASSIGNED,
            )
            .order_by("-created_at")
        )
        unassigned_personal_docs = list(
            PersonalDocument.objects
            .filter(
                company=company,
                company_user__isnull=True,
                status=PersonalDocument.Status.UNASSIGNED,
            )
            .order_by("-created_at")
        )
        for doc in unassigned_machine_docs:
            doc.download_url = _resolve_download_url(
                doc, MACHINE_DOCUMENTS_BUCKET,
            )
        for doc in unassigned_personal_docs:
            doc.download_url = _resolve_download_url(
                doc, PERSONNEL_DOCUMENTS_BUCKET,
            )

        return render(request, self.template_name, {
            "active_nav": "documentation_hub",
            "company_user": company_user,
            "machines": machines,
            "workers": workers,
            "unassigned_machine_docs": unassigned_machine_docs,
            "unassigned_personal_docs": unassigned_personal_docs,
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

        machines = MachineAsset.objects.filter(company=company)
        if search:
            from django.db.models import Q
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


class DocumentationMachineDetailFragmentView(DocsUploadAccessMixin, View):
    """
    GET (HTMX): documentación CLASSIFIED de UNA máquina, ya separada
    en vigente/archivada, con URL de descarga resuelta por documento.
    Se carga al desplegar el accordion-item de esa máquina (carga
    perezosa, propuesta aprobada en S024) -- nunca viene en el HTML
    inicial de DocumentationHubView.
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

        documents = list(
            MachineDocument.objects
            .filter(
                machine_asset=machine,
                status=MachineDocument.Status.CLASSIFIED,
            )
            .order_by("document_type", "-created_at")
        )
        current_docs, archived_docs = _split_current_archived(documents)

        for doc in current_docs + archived_docs:
            doc.download_url = _resolve_download_url(
                doc, MACHINE_DOCUMENTS_BUCKET,
            )

        return render(request, self.template_name, {
            "machine": machine,
            "current_docs": current_docs,
            "archived_docs": archived_docs,
        })


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


class DocumentationFolderUploadView(DocsUploadAccessMixin, View):
    """
    POST: recibe el lote acumulado de una o varias carpetas (JS del
    lado del navegador, ver hub.html -- el input real es
    `<input type="file" webkitdirectory multiple>` invocado varias
    veces y fusionado en un único FormData antes de enviar). Crea una
    fila IngestedFile por PDF (status=PENDING_ROUTING, rápido, sin
    llamadas a Gemini) y encola UNA tarea
    document_ingestion.tasks.route_ingested_files para todo el lote --
    mismo principio async que el resto de subidas de esta plataforma
    (incidente 2026-07-14, 504 de PythonAnywhere).

    A diferencia de MachineDocumentBatchUploadView (H23, sin tocar):
    aquí NO se elige máquina/trabajador de antemano -- se detecta
    automáticamente por contenido (document_ingestion, S024).
    """

    def post(self, request):
        company = request.user.company_user.company
        company_user = request.user.company_user

        uploaded_files = [
            f for f in request.FILES.getlist("folder")
            if f.name.lower().endswith(".pdf")
        ]
        if not uploaded_files:
            messages.error(
                request,
                "No se encontró ningún PDF en la(s) carpeta(s) "
                "seleccionada(s).",
            )
            return redirect(reverse("panel:documentation_hub"))

        # Deduplicación por hash (S024) -- antes de crear cualquier
        # IngestedFile, para no gastar ni la llamada de enrutado ni la
        # de clasificación en un archivo que ya está subido. Mismo
        # criterio que MachineDocumentBatchUploadView: comprueba
        # contra BD (los dos dominios, find_duplicate) y contra el
        # resto de archivos de este mismo lote.
        ingested_pks = []
        skipped_duplicates = 0
        batch_hashes: set[str] = set()
        for uploaded_file in uploaded_files:
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
                content_hash=content_hash,
                status=IngestedFile.Status.PENDING_ROUTING,
            )
            ingested.source_file.save(
                uploaded_file.name, uploaded_file, save=False,
            )
            ingested.save()
            ingested_pks.append(ingested.pk)

        if not ingested_pks:
            messages.error(
                request,
                "Todos los archivos seleccionados ya estaban subidos "
                "(duplicados por contenido)."
                if skipped_duplicates else
                "No se encontró ningún PDF en la(s) carpeta(s) "
                "seleccionada(s).",
            )
            return redirect(reverse("panel:documentation_hub"))

        route_ingested_files.delay(ingested_pks)

        logger.info(
            "# [DocumentationFolderUploadView] %d documento(s) en "
            "cola de enrutado para %s, tarea encolada. %d "
            "duplicado(s) omitido(s).",
            len(ingested_pks), company, skipped_duplicates,
        )

        success_message = (
            f"{len(ingested_pks)} documento(s) en cola de "
            f"clasificación automática. Puede tardar unos minutos -- "
            f"recarga esta página para ver el resultado en la pestaña "
            f"correspondiente (o en \"sin asignar\" si no se pudo "
            f"determinar la máquina/trabajador con confianza)."
        )
        if skipped_duplicates:
            success_message += (
                f" ({skipped_duplicates} archivo(s) omitido(s) por "
                f"estar ya subido(s).)"
            )
        messages.success(request, success_message)
        return redirect(reverse("panel:documentation_hub"))
