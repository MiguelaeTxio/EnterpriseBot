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
from django.http import Http404
from django.shortcuts import render
from django.views import View

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

        return render(request, self.template_name, {
            "active_nav": "documentation_hub",
            "company_user": company_user,
            "machines": machines,
            "workers": workers,
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
