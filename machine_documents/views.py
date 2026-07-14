# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/machine_documents/views.py
"""
Views for the machine_documents app (Hito 23) -- cost-center
documentation ingestion via the panel.

  MachineDocumentListView          -- GET, read-only listing, any
                                       authenticated CompanyUser
                                       (Miguel Ángel's decision:
                                       "solo lectura todo quisqui").
  MachineDocumentBatchUploadView   -- GET renders the folder-picker
                                       upload form; POST runs the full
                                       pipeline synchronously
                                       (classify -> detect master ->
                                       compare coverage -> extract
                                       uncovered pages -> persist to
                                       Drive + BD) and renders a
                                       results report. DOCS_SUPERVISOR
                                       / ADMIN only.

The upload is synchronous (no Celery task), unlike TaskPhoto/
DeliveryNote: a handful of PDFs classified one request at a time is a
few seconds per file, acceptable for a blocking request/response,
and it lets the panel show the full classification result (including
Gemini's proposed document_type/display_name) immediately instead of
needing an HTMX-polling widget for a first version of this flow.

---

Vistas de la app machine_documents (Hito 23) -- ingesta de
documentación de centros de gasto vía el panel.

  MachineDocumentListView          -- GET, listado de solo lectura,
                                       cualquier CompanyUser
                                       autenticado (decisión de
                                       Miguel Ángel: "solo lectura
                                       todo quisqui").
  MachineDocumentBatchUploadView   -- GET renderiza el formulario de
                                       subida con selector de carpeta;
                                       POST ejecuta el pipeline
                                       completo de forma síncrona
                                       (clasificar -> detectar maestro
                                       -> comparar cobertura ->
                                       extraer páginas no cubiertas ->
                                       persistir en Drive + BD) y
                                       renderiza un informe de
                                       resultado. Solo
                                       DOCS_SUPERVISOR / ADMIN.

La subida es síncrona (sin tarea Celery), a diferencia de TaskPhoto/
DeliveryNote: un puñado de PDFs clasificados uno a uno son unos
segundos por archivo, aceptable para un ciclo request/response
bloqueante, y permite mostrar el resultado completo de clasificación
(incluyendo el document_type/display_name propuesto por Gemini) de
inmediato, sin necesitar un widget de sondeo HTMX para una primera
versión de este flujo.
"""
import logging

from django.core.files.base import ContentFile
from django.shortcuts import render
from django.views import View
from django.views.generic import ListView

from fleet.models import MachineAsset
from panel.mixins import CompanyUserRequiredMixin, DocsUploadAccessMixin
from spare_parts.gdrive_service import (
    GDriveNotConfigured,
    upload_machine_document_file,
)

from .document_classification_service import (
    assess_master_coverage,
    classify_document,
    extract_pages,
)
from .models import MachineDocument

logger = logging.getLogger(__name__)


class MachineDocumentListView(CompanyUserRequiredMixin, ListView):
    """
    Read-only listing of MachineDocument for the user's company,
    optionally filtered by machine via ?machine=<pk>. Visible to any
    authenticated CompanyUser, per Miguel Ángel's explicit decision
    for this milestone (only the upload is role-restricted).
    ---
    Listado de solo lectura de MachineDocument de la empresa del
    usuario, opcionalmente filtrado por máquina vía ?machine=<pk>.
    Visible para cualquier CompanyUser autenticado, según decisión
    explícita de Miguel Ángel para este hito (solo la subida está
    restringida por rol).
    """

    model = MachineDocument
    template_name = "machine_documents/list.html"
    context_object_name = "documents"
    paginate_by = 50

    def get_queryset(self):
        company = self.request.user.company_user.company
        queryset = (
            MachineDocument.objects
            .filter(company=company)
            .select_related("machine_asset")
        )
        machine_pk = self.request.GET.get("machine")
        if machine_pk:
            queryset = queryset.filter(machine_asset_id=machine_pk)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_nav"] = "machine_documents_list"
        context["machines"] = MachineAsset.objects.filter(
            company=self.request.user.company_user.company,
        ).order_by("code")
        context["selected_machine"] = self.request.GET.get("machine", "")
        company_user = self.request.user.company_user
        context["can_upload"] = company_user.role in {
            company_user.ROLE_DOCS_SUPERVISOR, company_user.ROLE_ADMIN,
        }
        return context


class MachineDocumentBatchUploadView(DocsUploadAccessMixin, View):
    """
    GET renders the upload form (machine picker + folder/multi-file
    picker). POST runs the full classification pipeline against every
    uploaded PDF and persists the results.
    ---
    GET renderiza el formulario de subida (selector de máquina +
    selector de carpeta/multi-archivo). POST ejecuta el pipeline de
    clasificación completo sobre cada PDF subido y persiste los
    resultados.
    """

    template_name = "machine_documents/upload.html"
    result_template_name = "machine_documents/upload_result.html"

    def get(self, request):
        company = request.user.company_user.company
        machines = MachineAsset.objects.filter(
            company=company,
        ).order_by("code")
        return render(request, self.template_name, {
            "active_nav": "machine_documents_upload",
            "machines": machines,
        })

    def post(self, request):
        company = request.user.company_user.company
        company_user = request.user.company_user

        machine_pk = request.POST.get("machine_asset")
        machine_asset = (
            MachineAsset.objects
            .filter(pk=machine_pk, company=company)
            .first()
        )
        uploaded_files = [
            f for f in request.FILES.getlist("folder")
            if f.name.lower().endswith(".pdf")
        ]

        machines = MachineAsset.objects.filter(
            company=company,
        ).order_by("code")

        if not machine_asset:
            return render(request, self.template_name, {
                "active_nav": "machine_documents_upload",
                "machines": machines,
                "error": (
                    "Selecciona una máquina/centro de gasto válido "
                    "antes de subir la carpeta."
                ),
            })

        if not uploaded_files:
            return render(request, self.template_name, {
                "active_nav": "machine_documents_upload",
                "machines": machines,
                "error": (
                    "No se encontró ningún PDF en la carpeta "
                    "seleccionada."
                ),
            })

        # ------------------------------------------------------------
        # Step 1 -- classify every uploaded file individually.
        # Paso 1 -- clasificar cada archivo subido individualmente.
        # ------------------------------------------------------------
        classified = []
        for uploaded_file in uploaded_files:
            file_bytes = uploaded_file.read()
            result = classify_document(file_bytes, uploaded_file.name)
            classified.append({
                "django_file": uploaded_file,
                "filename": uploaded_file.name,
                "bytes": file_bytes,
                "result": result,
            })

        # ------------------------------------------------------------
        # Step 2 -- for every candidate master, compare against the
        # rest of the batch and extract any uncovered content as a
        # new synthetic entry.
        # Paso 2 -- para cada candidato a maestro, comparar contra el
        # resto del lote y extraer cualquier contenido no cubierto
        # como una entrada sintética nueva.
        # ------------------------------------------------------------
        extra_entries = []
        for item in classified:
            if not item["result"]["is_possible_master"]:
                continue

            individuals = [
                (other["filename"], other["bytes"])
                for other in classified
                if other is not item
            ]
            if not individuals:
                continue

            coverage = assess_master_coverage(
                item["bytes"], item["filename"], individuals,
            )
            item["coverage"] = coverage

            if coverage["uncovered_pages"]:
                extracted_bytes = extract_pages(
                    item["bytes"], coverage["uncovered_pages"],
                )
                extracted_name = (
                    f"{item['filename']} (páginas no cubiertas)"
                )
                extra_result = classify_document(
                    extracted_bytes, extracted_name,
                )
                extra_entries.append({
                    "filename": extracted_name,
                    "bytes": extracted_bytes,
                    "result": extra_result,
                    "source_master_hint": item["filename"],
                })

        # ------------------------------------------------------------
        # Step 3 -- persist every resulting document (originals +
        # extracted-from-master) to the DB and to Google Drive.
        # Paso 3 -- persistir cada documento resultante (originales +
        # extraídos del maestro) en BD y en Google Drive.
        # ------------------------------------------------------------
        saved_documents = []
        drive_error = None
        all_entries = classified + [
            {
                "filename": e["filename"],
                "bytes": e["bytes"],
                "result": e["result"],
                "source_master_hint": e["source_master_hint"],
            }
            for e in extra_entries
        ]

        for entry in all_entries:
            result = entry["result"]
            if not result["document_type"]:
                # Classification failed for this file -- skip
                # persistence, it will show up in the report as an
                # error row.
                # Clasificación fallida para este archivo -- se omite
                # la persistencia, aparecerá en el informe como fila
                # de error.
                continue

            document = MachineDocument(
                machine_asset=machine_asset,
                company=company,
                uploaded_by=company_user,
                document_type=result["document_type"],
                display_name=result["display_name"],
                source_master_hint=entry.get("source_master_hint", ""),
            )
            document.source_file.save(
                entry["filename"],
                ContentFile(entry["bytes"]),
                save=False,
            )
            document.save()

            try:
                drive_result = upload_machine_document_file(document)
                document.drive_file_id = drive_result["file_id"]
                document.drive_web_link = drive_result["web_link"]
                document.save(
                    update_fields=["drive_file_id", "drive_web_link"],
                )
            except GDriveNotConfigured as exc:
                drive_error = str(exc)
                logger.warning(
                    "# [MachineDocumentBatchUploadView] Drive no "
                    "configurado, documento #%d guardado solo en BD: "
                    "%s", document.pk, exc,
                )
            except Exception as exc:
                logger.error(
                    "# [MachineDocumentBatchUploadView] Error subiendo "
                    "documento #%d a Drive: %s",
                    document.pk, exc, exc_info=True,
                )

            saved_documents.append(document)

        return render(request, self.result_template_name, {
            "active_nav": "machine_documents_upload",
            "machine_asset": machine_asset,
            "classified": classified,
            "extra_entries": extra_entries,
            "saved_documents": saved_documents,
            "drive_error": drive_error,
        })
