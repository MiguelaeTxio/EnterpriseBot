# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/machine_documents/views.py
"""
Views for the machine_documents app (Hito 23) -- cost-center
documentation ingestion via the panel.

  MachineDocumentBatchUploadView   -- GET renders the folder-picker
                                       upload form; POST creates a
                                       MachineDocument row per PDF
                                       (status=PENDING) and enqueues
                                       machine_documents.tasks.
                                       process_machine_document_batch
                                       to do the actual work in the
                                       background. DOCS_SUPERVISOR /
                                       ADMIN only.

There is deliberately no cross-machine listing view here (removed
2026-07-14, Miguel Ángel's decision): with hundreds of machines a
single listing crossing all of them would grow unmanageably large.
Read access lives instead inside history.views.MachineHistoryView
(the "#documentacion" section, scoped to one selected machine at a
time) -- same precedent as the H7 task-photo gallery, merged into
that same view instead of a standalone page. panel/fleet/list.html
(fleet_list) links there per row as the entry point.

The upload is asynchronous (Celery task), same pattern as TaskPhoto/
DeliveryNote. CHANGED 2026-07-14 (Miguel Ángel's explicit decision,
"desde ya", no technical debt left for later): the first version of
this view ran the whole classification pipeline synchronously inside
the request, which caused a real PythonAnywhere 504 (5-minute webapp
timeout) on the first end-to-end panel test with 9 real documents --
see machine_documents.tasks.process_machine_document_batch docstring
for the full incident writeup. POST now only saves each uploaded file
to disk (fast, no Gemini/Drive calls) and enqueues the task, so
request/response time no longer depends on batch size at all.

---

Vistas de la app machine_documents (Hito 23) -- ingesta de
documentación de centros de gasto vía el panel.

  MachineDocumentBatchUploadView   -- GET renderiza el formulario de
                                       subida con selector de carpeta;
                                       POST crea una fila
                                       MachineDocument por PDF
                                       (status=PENDING) y encola
                                       machine_documents.tasks.
                                       process_machine_document_batch
                                       para hacer el trabajo real en
                                       segundo plano. Solo
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

La subida es asíncrona (tarea Celery), mismo patrón que TaskPhoto/
DeliveryNote. CAMBIADO 2026-07-14 (decisión explícita de Miguel Ángel,
"desde ya", sin dejar deuda técnica para después): la primera versión
de esta vista ejecutaba el pipeline de clasificación completo de
forma síncrona dentro de la petición, lo que causó un 504 real de
PythonAnywhere (timeout de 5 minutos del webapp) en la primera prueba
end-to-end desde el panel con 9 documentos reales -- ver el docstring
de machine_documents.tasks.process_machine_document_batch para el
relato completo del incidente. POST ahora solo guarda cada archivo
subido en disco (rápido, sin llamadas a Gemini/Drive) y encola la
tarea, así que el tiempo de petición/respuesta ya no depende en
absoluto del tamaño del lote.
"""
import logging

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from fleet.models import MachineAsset
from panel.mixins import DocsUploadAccessMixin

from .models import MachineDocument
from .tasks import process_machine_document_batch

logger = logging.getLogger(__name__)


class MachineDocumentBatchUploadView(DocsUploadAccessMixin, View):
    """
    GET renders the upload form (machine picker + folder/multi-file
    picker). POST creates one MachineDocument (status=PENDING) per
    uploaded PDF and enqueues a single Celery task to process the
    whole batch in the background, then redirects to the
    documentation section of the selected machine's Historial de
    Máquina.
    ---
    GET renderiza el formulario de subida (selector de máquina +
    selector de carpeta/multi-archivo). POST crea un MachineDocument
    (status=PENDING) por cada PDF subido y encola una única tarea
    Celery para procesar el lote completo en segundo plano, y después
    redirige a la sección de documentación del Historial de Máquina
    de la máquina seleccionada.
    """

    template_name = "machine_documents/upload.html"

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
        # Fast path -- just persist each file with status=PENDING.
        # No Gemini/Drive calls here; that's all in the Celery task
        # (2026-07-14, see module docstring for why).
        # Vía rápida -- solo persistir cada archivo con
        # status=PENDING. Ninguna llamada a Gemini/Drive aquí; todo
        # eso vive en la tarea Celery (2026-07-14, ver el docstring
        # del módulo para el motivo).
        # ------------------------------------------------------------
        document_pks = []
        for uploaded_file in uploaded_files:
            document = MachineDocument(
                machine_asset=machine_asset,
                company=company,
                uploaded_by=company_user,
                original_filename=uploaded_file.name,
                status=MachineDocument.Status.PENDING,
            )
            document.source_file.save(
                uploaded_file.name, uploaded_file, save=False,
            )
            document.save()
            document_pks.append(document.pk)

        process_machine_document_batch.delay(document_pks)

        logger.info(
            "# [MachineDocumentBatchUploadView] %d documento(s) en "
            "cola para %s (máquina %s), tarea encolada.",
            len(document_pks), company, machine_asset.code,
        )

        messages.success(
            request,
            f"{len(document_pks)} documento(s) en cola de "
            f"procesamiento para {machine_asset.code}. La "
            f"clasificación puede tardar unos minutos -- recarga esta "
            f"página para ver el resultado.",
        )
        return redirect(
            reverse("history:machine_history")
            + f"?machine_code={machine_asset.code}#documentacion"
        )
