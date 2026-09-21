# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_circulars_h31.py
"""
H31 (S75), punto 2 de la hoja de ruta. CRUD de circulares/
notificaciones -- crear un tipo documental nuevo de circular, editar
su `content_html` con un editor de texto básico integrado (colores,
pocas fuentes -- alcance deliberadamente reducido, nunca un procesador
de textos completo), importar el contenido inicial desde un Word/PDF
real, y sustituir la plantilla vigente (`DocumentTypeCatalog.
current_template`) de forma consistente con el mecanismo ya en uso
(un `DocumentIndexEntry` más, nunca un archivo fuera del sistema --
ver el propio help_text del campo, H30 S69).

Alcance: tipos documentales de dominio PERSONAL/BOTH/COMPANY --
ampliado en S114 a COMPANY porque el tipo genérico real de circular
(`CIRCULAR_INFORMATIVA`) vive en ese dominio, no en PERSONAL/BOTH
como asumía el alcance original de S75. No toca el catálogo de tipos
de Maquinaria (`DOMAIN_MACHINE`) ni el de EPI (`DOMAIN_EPI`).

Acceso: DocsUploadAccessMixin (DOCS_SUPERVISOR/ADMIN) -- mismo
criterio que el resto de acciones de escritura de H31 (entrega de
EPI, envío de notificación), no el criterio más estricto de
`ExplorerAccessMixin`/solo-admin que usa el Catálogo de tipos general
del explorador (`document_explorer.DocumentTypeCatalogListView`):
esto es parte del flujo normal de un supervisor de documentación
gestionando sus propias circulares, no administración de la
plataforma.
"""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from document_explorer import naming_service
from document_explorer.index_writer import ensure_folder_chain
from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog, path_digest
from panel.mixins import DocsUploadAccessMixin
from spare_parts.gcs_service import upload_bytes

BUCKET = "cgs_grupo_alvarez"

# Carpeta virtual dedicada, mismo criterio de nomenclatura que
# `_CUARENTENA/` (document_explorer.buckets) -- prefijo `_` para
# distinguir carpetas de infraestructura de las carpetas reales de
# DOC. PERSONAL/DOC. MAQUINAS. Las plantillas de circular no
# pertenecen a ningún sujeto (domain_content_type/domain_object_id
# quedan nulos), así que necesitan una carpeta propia, no la de un
# centro de gasto o una persona.
TEMPLATES_ROOT = "_PLANTILLAS_CIRCULARES"

_CIRCULAR_DOMAINS = [
    DocumentTypeCatalog.DOMAIN_PERSONAL,
    DocumentTypeCatalog.DOMAIN_BOTH,
    DocumentTypeCatalog.DOMAIN_COMPANY,
]


class CircularImportError(Exception):
    """Fallo esperado (no técnico) al extraer texto de un Word/PDF
    importado -- formato no reconocido, archivo vacío, dependencia de
    parseo no disponible. Nunca deja caer una excepción cruda al
    supervisor."""


def _extract_html_from_docx(data):
    """
    Extrae el contenido de un `.docx` real con `python-docx` (ya en
    requirements.txt, usado también por pymupdf-layout/pymupdf4llm) --
    un `<p>` por párrafo del documento, con `<strong>`/`<em>` cuando
    TODO el párrafo comparte ese formato en sus runs (heurística
    simple, deliberadamente -- el editor posterior es donde se afina,
    esto es solo el punto de partida). Párrafos vacíos se descartan.
    """
    import io

    try:
        import docx
    except ImportError as exc:
        raise CircularImportError(
            "La dependencia python-docx no está disponible en este "
            "entorno -- no se puede importar el Word.",
        ) from exc

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise CircularImportError(
            "No se ha podido leer el archivo como un .docx válido.",
        ) from exc

    parts = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        runs = [r for r in paragraph.runs if r.text.strip()]
        is_bold = bool(runs) and all(r.bold for r in runs)
        is_italic = bool(runs) and all(r.italic for r in runs)
        safe_text = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        if is_bold:
            safe_text = f"<strong>{safe_text}</strong>"
        if is_italic:
            safe_text = f"<em>{safe_text}</em>"
        parts.append(f"<p>{safe_text}</p>")

    if not parts:
        raise CircularImportError(
            "El Word no contiene ningún párrafo con texto real.",
        )
    return "\n".join(parts)


def _extract_html_from_pdf(data):
    """
    Extrae el texto de un `.pdf` real con `pymupdf4llm` (ya en
    requirements.txt) -- devuelve Markdown, aquí se toman solo los
    párrafos de texto plano (líneas no vacías) envueltos en `<p>`,
    sin intentar preservar tablas/imágenes/formato Markdown avanzado
    -- mismo alcance deliberadamente reducido que la importación de
    Word. Si `pymupdf4llm` no está disponible, cae a extracción de
    texto plano por página vía `pymupdf` (`fitz`) directamente.
    """
    try:
        import pymupdf4llm

        markdown_text = pymupdf4llm.to_markdown(("pdf", data))
    except ImportError:
        try:
            import fitz  # pymupdf
        except ImportError as exc:
            raise CircularImportError(
                "Ninguna dependencia de lectura de PDF (pymupdf4llm/"
                "pymupdf) está disponible en este entorno -- no se "
                "puede importar el PDF.",
            ) from exc
        try:
            doc = fitz.open(stream=data, filetype="pdf")
            markdown_text = "\n\n".join(page.get_text() for page in doc)
        except Exception as exc:
            raise CircularImportError(
                "No se ha podido leer el archivo como un .pdf válido.",
            ) from exc
    except Exception as exc:
        raise CircularImportError(
            "No se ha podido leer el archivo como un .pdf válido.",
        ) from exc

    lines = [line.strip() for line in markdown_text.splitlines()]
    lines = [line for line in lines if line and not line.startswith("#")]
    if not lines:
        raise CircularImportError(
            "El PDF no contiene ningún texto extraíble (¿es un "
            "escaneo de imagen sin OCR?).",
        )
    safe_lines = [
        line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        for line in lines
    ]
    return "\n".join(f"<p>{line}</p>" for line in safe_lines)


def _upload_circular_template(document_type, data, original_filename):
    """
    Sube el archivo real (Word/PDF, tal cual, sin parsear) a una
    carpeta propia de plantillas y repunta `current_template` al
    `DocumentIndexEntry` nuevo -- nunca borra ni toca el anterior
    (4.12, y el propio help_text de `current_template`: "el histórico
    de entregas no se toca"). `domain_content_type`/`domain_object_id`
    quedan nulos -- esta fila no pertenece a ningún sujeto, es
    infraestructura del propio tipo documental.
    """
    extension = (
        original_filename.rsplit(".", 1)[-1].lower()
        if "." in original_filename else "bin"
    )
    today = timezone.now().date()
    filename = "%s_PLANTILLA_%s.%s" % (
        document_type.code, today.isoformat(), extension,
    )
    target_folder = "%s/%s" % (TEMPLATES_ROOT, document_type.code)
    ensure_folder_chain(BUCKET, target_folder)
    blob_name = "%s/%s" % (target_folder, filename)
    content_type = (
        "application/pdf" if extension == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if extension == "docx"
        else "application/octet-stream"
    )
    upload_bytes(BUCKET, blob_name, data, content_type=content_type)

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
    )
    document_type.current_template = entry
    document_type.save(update_fields=["current_template"])
    return entry


class CircularListView(DocsUploadAccessMixin, View):
    """GET: listado de tipos documentales de circular/notificación
    (dominio PERSONAL/BOTH) -- estado de content_html y de
    current_template de un vistazo, acceso a crear uno nuevo o editar
    uno existente."""

    def get(self, request):
        types = DocumentTypeCatalog.objects.filter(
            is_active=True, domain__in=_CIRCULAR_DOMAINS,
        ).select_related("current_template").order_by("label")
        return render(request, "panel/circulars_h31/circular_list.html", {
            "types": types,
            "family_choices": DocumentTypeCatalog.FAMILY_CHOICES,
            "active_nav": "documentation_hub",
        })


class CircularCreateView(DocsUploadAccessMixin, View):
    """
    POST: da de alta un tipo documental de circular nuevo -- mismo
    patrón que `DocumentTypeQuickCreateView` (H30 S51): `code` se
    deriva del `label` con `naming_service._sanitize_token()`,
    `content_html` nace vacío (se rellena en `CircularEditView`).
    `domain` restringido a PERSONAL/BOTH/COMPANY (S114) -- nunca
    MACHINE ni EPI.
    """

    def post(self, request):
        label = (request.POST.get("label") or "").strip()
        family = (request.POST.get("family") or "").strip()
        domain = (request.POST.get("domain") or DocumentTypeCatalog.DOMAIN_PERSONAL).strip()

        valid_families = dict(DocumentTypeCatalog.FAMILY_CHOICES)
        if not label:
            messages.error(request, "Falta el nombre visible de la circular.")
            return redirect(reverse("panel:circulars_list"))
        if family not in valid_families:
            messages.error(request, "Falta elegir una familia documental válida.")
            return redirect(reverse("panel:circulars_list"))
        if domain not in _CIRCULAR_DOMAINS:
            domain = DocumentTypeCatalog.DOMAIN_PERSONAL

        code = naming_service._sanitize_token(label)
        if not code:
            messages.error(request, "El nombre visible no genera un código válido.")
            return redirect(reverse("panel:circulars_list"))
        if DocumentTypeCatalog.objects.filter(code=code).exists():
            messages.error(
                request,
                "Ya existe un tipo documental con código «%s» -- "
                "revisa el listado, puede que ya esté ahí con otro "
                "nombre visible." % code,
            )
            return redirect(reverse("panel:circulars_list"))

        document_type = DocumentTypeCatalog.objects.create(
            code=code, label=label, domain=domain, family=family,
        )
        messages.success(
            request,
            "«%s» creada -- ahora edita su contenido." % document_type.label,
        )
        return redirect(reverse("panel:circulars_edit", args=[document_type.pk]))


class CircularEditView(DocsUploadAccessMixin, View):
    """GET: pantalla de edición de UNA circular -- editor de texto
    básico sobre content_html, más el bloque de plantilla vigente
    (current_template)."""

    def get(self, request, pk):
        document_type = get_object_or_404(
            DocumentTypeCatalog, pk=pk, domain__in=_CIRCULAR_DOMAINS,
        )
        return render(request, "panel/circulars_h31/circular_edit.html", {
            "document_type": document_type,
            "active_nav": "documentation_hub",
        })


class CircularSaveContentView(DocsUploadAccessMixin, View):
    """
    POST: guarda `content_html` tal cual llega del editor -- el
    propio editor (JS, `_personal_pane.html`-style, ver
    circular_edit.html) ya sintetiza el HTML del `contenteditable` a
    un campo oculto antes de enviar el formulario. Sin sanitizado
    adicional aquí -- el editor solo permite negrita/cursiva/color/
    fuente/lista vía `document.execCommand`, nunca `<script>` ni
    HTML pegado libre (el pegado se limpia a texto plano, ver JS),
    así que el HTML que llega ya está dentro del alcance reducido
    pactado (colores, pocas fuentes -- nunca un procesador de textos
    completo).
    """

    def post(self, request, pk):
        document_type = get_object_or_404(
            DocumentTypeCatalog, pk=pk, domain__in=_CIRCULAR_DOMAINS,
        )
        content_html = request.POST.get("content_html", "")
        document_type.content_html = content_html
        document_type.save(update_fields=["content_html"])
        messages.success(request, "Contenido de «%s» guardado." % document_type.label)
        return redirect(reverse("panel:circulars_edit", args=[document_type.pk]))


class CircularImportDocumentView(DocsUploadAccessMixin, View):
    """
    POST: importa un Word/PDF real y SOBRESCRIBE `content_html` con
    el texto extraído (envuelto en párrafos simples, negrita/cursiva
    donde `python-docx` lo confirma para .docx) -- punto de partida
    para que el supervisor lo termine de maquetar en el editor, nunca
    una conversión perfecta 1:1 (fuera de alcance, ver docstring del
    módulo). No toca `current_template` -- eso es
    `CircularTemplateUploadView`, una acción deliberadamente separada.
    """

    def post(self, request, pk):
        document_type = get_object_or_404(
            DocumentTypeCatalog, pk=pk, domain__in=_CIRCULAR_DOMAINS,
        )
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            messages.error(request, "Falta el archivo Word/PDF a importar.")
            return redirect(reverse("panel:circulars_edit", args=[document_type.pk]))

        extension = (
            uploaded_file.name.rsplit(".", 1)[-1].lower()
            if "." in uploaded_file.name else ""
        )
        data = uploaded_file.read()
        try:
            if extension == "docx":
                html = _extract_html_from_docx(data)
            elif extension == "pdf":
                html = _extract_html_from_pdf(data)
            else:
                messages.error(
                    request,
                    "Formato «%s» no soportado -- solo .docx o .pdf." % extension,
                )
                return redirect(reverse("panel:circulars_edit", args=[document_type.pk]))
        except CircularImportError as exc:
            messages.error(request, str(exc))
            return redirect(reverse("panel:circulars_edit", args=[document_type.pk]))

        document_type.content_html = html
        document_type.save(update_fields=["content_html"])
        messages.success(
            request,
            "Contenido importado desde «%s» -- revísalo y ajusta "
            "colores/formato en el editor antes de darlo por bueno."
            % uploaded_file.name,
        )
        return redirect(reverse("panel:circulars_edit", args=[document_type.pk]))


class CircularTemplateUploadView(DocsUploadAccessMixin, View):
    """
    POST: sustituye la plantilla vigente (`current_template`) de un
    tipo documental de circular -- sube el archivo real (Word/PDF) y
    repunta el FK, nunca borra ni toca la plantilla anterior (4.12).
    Acción deliberadamente separada de la importación de contenido
    (`CircularImportDocumentView`): esta es la plantilla legacy en
    archivo que Miguel Ángel decidió mantener en paralelo al
    `content_html` (S73), no el contenido enriquecido en sí.
    """

    def post(self, request, pk):
        document_type = get_object_or_404(
            DocumentTypeCatalog, pk=pk, domain__in=_CIRCULAR_DOMAINS,
        )
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            messages.error(request, "Falta el archivo de la nueva plantilla.")
            return redirect(reverse("panel:circulars_edit", args=[document_type.pk]))

        data = uploaded_file.read()
        _upload_circular_template(document_type, data, uploaded_file.name)
        messages.success(
            request,
            "Plantilla vigente de «%s» actualizada a «%s»."
            % (document_type.label, uploaded_file.name),
        )
        return redirect(reverse("panel:circulars_edit", args=[document_type.pk]))
