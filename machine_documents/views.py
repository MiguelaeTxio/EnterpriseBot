# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/machine_documents/views.py
"""
Views for the machine_documents app (Hito 23) -- cost-center
documentation ingestion via the panel.

  MachineDocumentBatchUploadView   -- GET renders the folder-picker
                                       upload form; POST runs the full
                                       pipeline synchronously
                                       (classify -> detect master ->
                                       compare coverage -> extract
                                       uncovered pages -> persist to
                                       Drive + BD) and renders a
                                       results report. DOCS_SUPERVISOR
                                       / ADMIN only.

There is deliberately no cross-machine listing view here (removed
2026-07-14, Miguel Ángel's decision): with hundreds of machines a
single listing crossing all of them would grow unmanageably large.
Read access lives instead inside history.views.MachineHistoryView
(the "#documentacion" section, scoped to one selected machine at a
time) -- same precedent as the H7 task-photo gallery, merged into
that same view instead of a standalone page. panel/fleet/list.html
(fleet_list) links there per row as the entry point.

The upload is synchronous (no Celery task), unlike TaskPhoto/
DeliveryNote: a handful of PDFs classified one request at a time is a
few seconds per file, acceptable for a blocking request/response,
and it lets the panel show the full classification result (including
Gemini's proposed document_type/display_name) immediately instead of
needing an HTMX-polling widget for a first version of this flow.

---

Vistas de la app machine_documents (Hito 23) -- ingesta de
documentación de centros de gasto vía el panel.

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

Deliberadamente no hay aquí ninguna vista de listado cruzado entre
máquinas (retirada 2026-07-14, decisión de Miguel Ángel): con
cientos de máquinas un único listado cruzándolas todas crecería de
forma inmanejable. El acceso de lectura vive en su lugar dentro de
history.views.MachineHistoryView (la sección "#documentacion",
acotada a una única máquina seleccionada) -- mismo precedente que la
galería de fotos de tarea de H7, fusionada en esa misma vista en vez
de una página independiente. panel/fleet/list.html (fleet_list)
enlaza ahí por cada fila como punto de entrada.

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

from fleet.models import MachineAsset
from panel.mixins import DocsUploadAccessMixin
from spare_parts.gdrive_service import (
    GDriveNotConfigured,
    upload_machine_document_file,
)

from .document_classification_service import (
    assess_master_coverage,
    classify_by_filename_heuristic,
    classify_document,
    extract_pages,
)
from .models import MachineDocument

logger = logging.getLogger(__name__)


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
        preselected_machine_pk = request.GET.get("machine", "")
        return render(request, self.template_name, {
            "active_nav": "machine_documents_upload",
            "machines": machines,
            "preselected_machine_pk": preselected_machine_pk,
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
                "preselected_machine_pk": machine_pk,
                "error": (
                    "No se encontró ningún PDF en la carpeta "
                    "seleccionada."
                ),
            })

        # ------------------------------------------------------------
        # Step 1 -- classify every uploaded file individually. Files
        # matching a filename heuristic (currently: user manuals)
        # NEVER reach Gemini -- see
        # document_classification_service.classify_by_filename_heuristic
        # docstring for why (2026-07-14 incident).
        # Paso 1 -- clasificar cada archivo subido individualmente.
        # Los archivos que coinciden con una heurística de nombre
        # (actualmente: manuales de uso) NUNCA llegan a Gemini -- ver
        # el docstring de
        # document_classification_service.classify_by_filename_heuristic
        # para el motivo (incidente 2026-07-14).
        # ------------------------------------------------------------
        classified = []
        for uploaded_file in uploaded_files:
            file_bytes = uploaded_file.read()
            heuristic_result = classify_by_filename_heuristic(
                uploaded_file.name,
            )
            if heuristic_result is not None:
                classified.append({
                    "django_file": uploaded_file,
                    "filename": uploaded_file.name,
                    "bytes": file_bytes,
                    "result": heuristic_result,
                    "via_heuristic": True,
                })
                continue

            result = classify_document(file_bytes, uploaded_file.name)
            classified.append({
                "django_file": uploaded_file,
                "filename": uploaded_file.name,
                "bytes": file_bytes,
                "result": result,
                "via_heuristic": False,
            })

        # ------------------------------------------------------------
        # Step 2 -- for every candidate master, compare against the
        # rest of the batch and extract any uncovered content as a
        # new synthetic entry. Heuristic-classified files (manuals)
        # are excluded from the comparison set -- sending their bytes
        # to assess_master_coverage() would defeat the whole point of
        # never sending them to Gemini.
        # Paso 2 -- para cada candidato a maestro, comparar contra el
        # resto del lote y extraer cualquier contenido no cubierto
        # como una entrada sintética nueva. Los archivos clasificados
        # por heurística (manuales) se excluyen del conjunto de
        # comparación -- enviar sus bytes a assess_master_coverage()
        # anularía el sentido de no enviarlos nunca a Gemini.
        # ------------------------------------------------------------
        extra_entries = []
        for item in classified:
            if item["via_heuristic"]:
                continue
            if not item["result"]["is_possible_master"]:
                continue

            individuals = [
                (other["filename"], other["bytes"])
                for other in classified
                if other is not item and not other["via_heuristic"]
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
