# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_circulars.py
#
# S163: COPIA de panel/views_circulars_h31.py para la nueva interfaz
# (crear circulares, editar su contenido, importar Word/PDF, exportar,
# generar el documento de una persona, firma certificada y preparar
# Docuten). Rutas, plantillas y acceso propios; no llama a la antigua.
"""
H31 (S75), punto 2 de la hoja de ruta. CRUD de circulares/
notificaciones -- crear un tipo documental nuevo de circular, editar
su `content_html` con un editor de texto básico integrado (colores,
pocas fuentes -- alcance deliberadamente reducido, nunca un procesador
de textos completo), e importar el contenido inicial desde un Word/PDF
real.

S114: retirada por completo la gestión de la plantilla legacy en
archivo (`DocumentTypeCatalog.current_template`) desde esta pantalla
-- Miguel Ángel: "yo, sinceramente, eliminaría el tema del legacy. Es
que es una cosa que no interesa y complica". El campo sigue
existiendo en el modelo (lo usan otros tipos documentales fuera de
circulares), pero ya no tiene ningún punto de entrada en el CRUD de
circulares.

Alcance: tipos documentales marcados explícitamente como plantilla
de comunicación (`is_notification_template=True`) -- corregido en
S114 tras detectar que el criterio anterior (filtrar por `domain`)
mostraba el catálogo ENTERO de documentos de persona (DNI, nóminas,
formación, salud...), no una lista acotada de circulares/
notificaciones reutilizables. Miguel Ángel, verbatim, al ver la
pantalla real: "eso es un galimatías [...] aquí vamos a tener unas
10, 15, 20 plantillas como mucho". `domain` sigue existiendo como
dato de a quién se dirige (PERSONAL/BOTH/COMPANY), pero ya NO decide
si algo aparece aquí -- ver `is_notification_template` en
`DocumentTypeCatalog` para el detalle completo de la corrección.

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
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.http import HttpResponse

from document_explorer import naming_service
from document_explorer.models import (
    CompanyFiscalProfile, DocumentTypeCatalog, PersonIdentity,
)
from document_explorer.subject_upload_service import (
    SubjectUploadError, upload_subject_document,
)
from new_ui.mixins import SuperuserRequiredMixin as DocsUploadAccessMixin

_CIRCULAR_DOMAINS = [
    DocumentTypeCatalog.DOMAIN_PERSONAL,
    DocumentTypeCatalog.DOMAIN_BOTH,
    DocumentTypeCatalog.DOMAIN_COMPANY,
]
# Dominios válidos a ofrecer al crear una circular NUEVA (a quién se
# dirige) -- ya no decide qué aparece en el listado/edición, eso lo
# decide is_notification_template (S114, ver docstring del módulo).


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


CIRCULARS_SCREEN_KEY = "circulars_list"
_CIRCULARS_FILTER_KEYS = ("q", "sort")
_CIRCULARS_SORT_KEYS = ("label", "code", "domain", "template", "signature")
_CIRCULARS_MAX_SORT = 4
_CIRCULARS_BULK = {
    "sign": (True, "Marcadas «requiere firma (Docuten)»"),
    "unsign": (False, "Marcadas «sin firma»"),
}


def _circulars_hub_url():
    """
    Documentation hub with the Circulares tab open.

    ---

    Hub de Documentación con la pestaña Circulares abierta (enlace
    directo que el hub persiste como un clic de pestaña).
    """
    return "%s?s=doc" % reverse("new_ui:home")


def _parse_circular_sort(raw):
    """
    "sort=key,-key" -> [(key, desc)], known keys only, max four.

    ---

    "sort=clave,-clave" -> [(clave, desc)], solo claves conocidas, sin
    repetir y como mucho cuatro.
    """
    keys, seen = [], set()
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in _CIRCULARS_SORT_KEYS and key not in seen:
            keys.append((key, token.startswith("-")))
            seen.add(key)
    return keys[:_CIRCULARS_MAX_SORT]


def _circular_sort_value(doc_type, key):
    """
    Sort value of one column for one circular.

    ---

    Valor de orden de una columna para una circular.
    """
    if key == "template":
        return bool(doc_type.content_html or doc_type.current_template_id)
    if key == "signature":
        return doc_type.requires_signature
    if key == "domain":
        return doc_type.get_domain_display()
    return (getattr(doc_type, key) or "").lower()


class CircularBulkSignatureView(DocsUploadAccessMixin, View):
    """
    POST (htmx): mark the selected circulars with or without
    certified signature, and re-render the tab.

    ---

    POST (htmx): marca las circulares seleccionadas con o sin firma
    certificada (Docuten) y vuelve a pintar la pestaña con el
    resultado a la vista (H30, S125).
    """

    def post(self, request):
        # Nueva interfaz: responde en JSON (la lista se repinta sola).
        from django.http import JsonResponse

        action = request.POST.get("action")
        ids = [
            int(value) for value in request.POST.getlist("selected")
            if value.isdigit()
        ]
        if action not in _CIRCULARS_BULK or not ids:
            return JsonResponse({"ok": False, "message": (
                "No hay ninguna circular seleccionada.")}, status=400)
        value, headline = _CIRCULARS_BULK[action]
        updated = DocumentTypeCatalog.objects.filter(
            pk__in=ids, is_notification_template=True,
        ).update(requires_signature=value)
        return JsonResponse({"ok": True, "message": "%s: %d circular%s." % (
            headline, updated, "" if updated == 1 else "es")})


class CircularCreateView(DocsUploadAccessMixin, View):
    """
    POST: da de alta un tipo documental de circular nuevo -- mismo
    patrón que `DocumentTypeQuickCreateView` (H30 S51): `code` se
    deriva del `label` con `naming_service._sanitize_token()`,
    `content_html` nace vacío (se rellena en `CircularEditView`).
    `domain` restringido a PERSONAL/BOTH/COMPANY -- a quién se
    dirige, nunca MACHINE ni EPI. Todo lo creado aquí nace con
    `is_notification_template=True` (S114) -- es, por definición, una
    plantilla de comunicación real, el único criterio que decide su
    aparición en este CRUD y en el selector de envío.
    """

    def post(self, request):
        label = (request.POST.get("label") or "").strip()
        family = (request.POST.get("family") or "").strip()
        domain = (request.POST.get("domain") or DocumentTypeCatalog.DOMAIN_PERSONAL).strip()

        valid_families = dict(DocumentTypeCatalog.FAMILY_CHOICES)
        if not label:
            messages.error(request, "Falta el nombre visible de la circular.")
            return redirect(_circulars_hub_url())
        if family not in valid_families:
            messages.error(request, "Falta elegir una familia documental válida.")
            return redirect(_circulars_hub_url())
        if domain not in _CIRCULAR_DOMAINS:
            domain = DocumentTypeCatalog.DOMAIN_PERSONAL

        code = naming_service._sanitize_token(label)
        if not code:
            messages.error(request, "El nombre visible no genera un código válido.")
            return redirect(_circulars_hub_url())
        if DocumentTypeCatalog.objects.filter(code=code).exists():
            messages.error(
                request,
                "Ya existe un tipo documental con código «%s» -- "
                "revisa el listado, puede que ya esté ahí con otro "
                "nombre visible." % code,
            )
            return redirect(_circulars_hub_url())

        document_type = DocumentTypeCatalog.objects.create(
            code=code, label=label, domain=domain, family=family,
            is_notification_template=True,
        )
        messages.success(
            request,
            "«%s» creada -- ahora edita su contenido." % document_type.label,
        )
        return redirect(reverse("new_ui:circulars_edit", args=[document_type.pk]))


class CircularEditView(DocsUploadAccessMixin, View):
    """GET: pantalla de edición de UNA circular -- editor de texto
    básico sobre content_html. Ya no gestiona current_template (S114,
    retirado de esta pantalla -- ver docstring del módulo)."""

    def get(self, request, pk):
        document_type = get_object_or_404(
            DocumentTypeCatalog, pk=pk, is_notification_template=True,
        )
        return render(request, "new_ui/circulars/circular_edit.html", {
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
            DocumentTypeCatalog, pk=pk, is_notification_template=True,
        )
        content_html = request.POST.get("content_html", "")
        document_type.content_html = content_html
        # H30 (S124): casilla "Requiere firma (Docuten)".
        document_type.requires_signature = (
            request.POST.get("requires_signature") == "1"
        )
        document_type.save(
            update_fields=["content_html", "requires_signature"],
        )
        messages.success(request, "Contenido de «%s» guardado." % document_type.label)
        return redirect(reverse("new_ui:circulars_edit", args=[document_type.pk]))


class CircularImportDocumentView(DocsUploadAccessMixin, View):
    """
    POST: importa un Word/PDF real y SOBRESCRIBE `content_html` con
    el texto extraído (envuelto en párrafos simples, negrita/cursiva
    donde `python-docx` lo confirma para .docx) -- punto de partida
    para que el supervisor lo termine de maquetar en el editor, nunca
    una conversión perfecta 1:1 (fuera de alcance, ver docstring del
    módulo).
    """

    def post(self, request, pk):
        document_type = get_object_or_404(
            DocumentTypeCatalog, pk=pk, is_notification_template=True,
        )
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            messages.error(request, "Falta el archivo Word/PDF a importar.")
            return redirect(reverse("new_ui:circulars_edit", args=[document_type.pk]))

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
                return redirect(reverse("new_ui:circulars_edit", args=[document_type.pk]))
        except CircularImportError as exc:
            messages.error(request, str(exc))
            return redirect(reverse("new_ui:circulars_edit", args=[document_type.pk]))

        document_type.content_html = html
        document_type.save(update_fields=["content_html"])
        messages.success(
            request,
            "Contenido importado desde «%s»." % uploaded_file.name,
        )
        return redirect(reverse("new_ui:circulars_edit", args=[document_type.pk]))


def _html_to_docx_runs(paragraph, node, bold=False, italic=False, underline=False, color=None, font_name=None):
    """
    Recorre el árbol de un bloque (<p>/<li>) del `content_html` del
    editor y añade runs a `paragraph` conservando negrita/cursiva/
    subrayado/color/fuente -- el mismo subconjunto reducido que el
    propio editor permite generar (ver circular_edit.html: negrita,
    cursiva, subrayado, color de una paleta fija, fuente de una lista
    fija). `document.execCommand` en navegadores reales suele emitir
    `<font color="#..." face="...">` para color/fuente (en vez de
    `style="color:..."` moderno) -- se contemplan ambas formas.
    """
    import re

    from bs4 import NavigableString

    for child in node.children:
        if isinstance(child, NavigableString):
            text = str(child)
            if not text:
                continue
            run = paragraph.add_run(text)
            run.font.bold = bold
            run.font.italic = italic
            run.font.underline = underline
            if color:
                try:
                    from docx.shared import RGBColor
                    run.font.color.rgb = RGBColor.from_string(color.lstrip("#"))
                except ValueError:
                    pass
            if font_name:
                run.font.name = font_name
            continue

        name = getattr(child, "name", None)
        if name == "br":
            paragraph.add_run().add_break()
            continue

        new_bold = bold or name in ("b", "strong")
        new_italic = italic or name in ("i", "em")
        new_underline = underline or name == "u"
        new_color = child.get("color") if name == "font" else color
        new_font = child.get("face") if name == "font" else font_name
        style = child.get("style") or ""
        match = re.search(r"color:\s*([^;]+)", style)
        if match:
            new_color = match.group(1).strip()
        if new_font:
            new_font = new_font.split(",")[0].strip().strip("'\"")
        _html_to_docx_runs(paragraph, child, new_bold, new_italic, new_underline, new_color, new_font)


class CircularExportPdfView(DocsUploadAccessMixin, View):
    """
    GET: descarga el `content_html` de una circular como PDF real,
    vía WeasyPrint -- mismo mecanismo ya en producción para tarifas de
    aseguradora y albaranes (`budgets/views.py`,
    `weasyprint.HTML(string=...).write_pdf()`). Una copia genérica del
    contenido, sin personalizar a ninguna persona -- para imprimir,
    adjuntar o archivar fuera del flujo de envío por email.
    """

    def get(self, request, pk):
        import weasyprint

        document_type = get_object_or_404(
            DocumentTypeCatalog, pk=pk, is_notification_template=True,
        )
        if not document_type.content_html.strip():
            messages.error(
                request,
                "«%s» todavía no tiene contenido -- edítala antes de descargarla."
                % document_type.label,
            )
            return redirect(reverse("new_ui:circulars_edit", args=[document_type.pk]))

        html_content = (
            "<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'>"
            "<style>"
            "body{font-family:Arial,sans-serif;font-size:11pt;margin:2.5cm 2cm}"
            "h1{font-size:14pt;margin-bottom:18px}"
            "</style></head><body>"
            "<h1>%s</h1>%s"
            "</body></html>"
        ) % (document_type.label, document_type.content_html)

        pdf_bytes = weasyprint.HTML(string=html_content).write_pdf()
        filename = "%s.pdf" % naming_service._sanitize_token(document_type.label)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="%s"' % filename
        return response


class CircularExportWordView(DocsUploadAccessMixin, View):
    """
    GET: descarga el `content_html` de una circular como Word (.docx)
    real -- mismo mecanismo ya en producción para tarifas de
    aseguradora (`budgets/views.py`, python-docx). Recorre el HTML con
    BeautifulSoup (`_html_to_docx_runs`) para conservar negrita/
    cursiva/subrayado/color/fuente dentro del alcance reducido del
    propio editor.
    """

    def get(self, request, pk):
        from bs4 import BeautifulSoup
        from docx import Document

        document_type = get_object_or_404(
            DocumentTypeCatalog, pk=pk, is_notification_template=True,
        )
        if not document_type.content_html.strip():
            messages.error(
                request,
                "«%s» todavía no tiene contenido -- edítala antes de descargarla."
                % document_type.label,
            )
            return redirect(reverse("new_ui:circulars_edit", args=[document_type.pk]))

        doc = Document()
        doc.add_heading(document_type.label, level=1)

        soup = BeautifulSoup(document_type.content_html, "html.parser")
        blocks = soup.find_all(["p", "li"])
        if not blocks:
            doc.add_paragraph(soup.get_text())
        for block in blocks:
            paragraph = doc.add_paragraph()
            if block.name == "li":
                paragraph.style = "List Bullet"
            _html_to_docx_runs(paragraph, block)

        import io

        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)

        # S125 (4.9): faltaban estas dos líneas -- "Descargar en Word"
        # daba siempre NameError (500).
        filename = "%s.docx" % naming_service._sanitize_token(
            document_type.label,
        )
        response = HttpResponse(
            buffer.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
        )
        response["Content-Disposition"] = 'attachment; filename="%s"' % filename
        return response


def _get_letterhead_logo_data_uri():
    """
    H31 (S115). Devuelve el logo corporativo de Grupo Álvarez (versión
    a color, texto naranja -- legible sobre fondo blanco, a diferencia
    de `grupo_alvarez_logo.png`, cuyo texto es blanco y solo se lee
    sobre fondo oscuro como el de la sidebar; aportado directamente
    por Miguel Ángel tras detectar el problema de legibilidad) como
    data URI base64. Se
    embebe como data URI (no como <img src="/static/...">) para que
    funcione igual en el navegador (Mi buzón) y en weasyprint (PDF de
    "Generar documento"), sin depender de que ambos resuelvan
    STATIC_URL de la misma forma. Devuelve None si el archivo no
    existe (nunca rompe la generación del documento por esto).
    """
    import base64

    from django.contrib.staticfiles.finders import find as find_static

    logo_path = find_static("new_ui/img/grupo_alvarez_logo_color.png")
    if not logo_path:
        return None
    with open(logo_path, "rb") as logo_file:
        encoded = base64.b64encode(logo_file.read()).decode("ascii")
    return "data:image/png;base64,%s" % encoded


def is_letter_format(content_html):
    """
    H31 (S115). Heurística para saber si un content_html ya lleva su
    propio título recuadrado de carta formal (nombramientos, S115) en
    vez del formato antiguo de notificación -- todo el contenido
    escrito en el nuevo formato empieza por el <div> del título
    recuadrado; el antiguo, por un <p>. Usado para no duplicar título
    (h1 de la pantalla + título propio de la carta) ni membrete donde
    no aplica.
    """
    return content_html.strip().startswith("<div")


PUBLIC_BASE_URL = "https://enterprisebot-miguelaetxio.pythonanywhere.com"


def _render_document_variables(content_html, *, worker=None, administrator=None, company=None, worksite=None):
    """
    H31 (S114, ampliado S115 con {{obra.*}}). Sustituye tokens
    `{{...}}` del `content_html` de una plantilla por datos reales de
    la persona/empresa/obra elegidas al generar. Un token sin dato
    disponible (p. ej. {{empresa.cif}} sin empresa elegida) se deja
    tal cual, nunca se sustituye por vacío a ciegas -- así un fallo de
    selección se ve en el documento en vez de desaparecer en silencio.
    """
    tokens = {}
    if worker is not None:
        tokens["trabajador.nombre_completo"] = (
            "%s %s %s" % (worker.given_name, worker.first_surname, worker.second_surname)
        ).strip()
        tokens["trabajador.dni"] = worker.dni
        tokens["trabajador.num_seguridad_social"] = worker.ss_affiliation_number
        # H30 (S124): puesto (categoría profesional de la ficha), lo pide
        # la entrega de información PRL real.
        tokens["trabajador.puesto"] = worker.professional_category
        # H24 (S141): usuario del panel (circular de alta y fichaje).
        account = getattr(worker, "company_user", None)
        if account is not None and account.user_id:
            tokens["trabajador.usuario"] = account.user.username
    if administrator is not None:
        tokens["administrador.nombre_completo"] = (
            "%s %s %s" % (administrator.given_name, administrator.first_surname, administrator.second_surname)
        ).strip()
        tokens["administrador.dni"] = administrator.dni
    if company is not None:
        tokens["empresa.razon_social"] = company.legal_name
        tokens["empresa.cif"] = company.tax_id
        tokens["empresa.direccion_fiscal"] = company.fiscal_address
    if worksite is not None:
        tokens["obra.nombre"] = worksite.name
        tokens["obra.direccion"] = worksite.address
        tokens["obra.cliente"] = worksite.client_name
    tokens["fecha"] = timezone.now().strftime("%d/%m/%Y")
    # H24 (S141): enlaces de la circular de alta y fichaje.
    tokens["enlace.fichaje"] = PUBLIC_BASE_URL + "/fichaje/"
    tokens["enlace.panel"] = PUBLIC_BASE_URL + "/panel/"

    result = content_html
    for key, value in tokens.items():
        result = result.replace("{{%s}}" % key, value or "")
    return result


def _circular_generate_person_search(request):
    """
    H31 (S114). Búsqueda de trabajador para "Generar documento" --
    mismo criterio que el antiguo autocompletado de Vacaciones (H31
    S94, retirado en H24 S129): nombre/apellidos/DNI icontains,
    solo activos, máx. 15, nada con menos de 2 caracteres. Duplicado
    aquí en vez de importado para no acoplar este módulo al de
    Documentación/Personal por una función de 8 líneas.
    """
    search = request.GET.get("q", "").strip()
    if len(search) < 2:
        return []
    return list(
        PersonIdentity.objects.filter(is_active_employee=True).filter(
            Q(first_surname__icontains=search)
            | Q(second_surname__icontains=search)
            | Q(given_name__icontains=search)
            | Q(dni__icontains=search),
        ).order_by("first_surname", "second_surname", "given_name")[:15],
    )


class CircularGenerateView(DocsUploadAccessMixin, View):
    """
    GET/POST: genera un documento real a partir de una plantilla de
    comunicación con variables. Miguel Ángel, verbatim: "las
    plantillas deben ser programáticas [...] elegida la plantilla el
    documento se genera con variables basadas en la base de datos, si
    por ejemplo se quiere dar poderes a un trabajador, elegimos la
    empresa, el administrador y el trabajador y se genera el
    documento ad-hoc".

    El administrador se resuelve SIEMPRE de forma automática a partir
    de la empresa elegida (`CompanyFiscalProfile.administrator`,
    confirmado contra contrato real de cada empresa, S114) -- sin
    selector aparte para él en este primer alcance; Miguel Ángel no
    llegó a confirmar si hace falta poder elegir a otra persona caso
    por caso, así que de momento es siempre el administrador oficial.

    El PDF generado se guarda en la carpeta real del trabajador (vía
    `upload_subject_document`, mismo mecanismo que la entrega de
    EPIs, H31 S113) con el propio `document_type` de la plantilla --
    confirmado explícitamente por Miguel Ángel (pregunta 2 de esta
    misma sesión: "¿se guardan en la carpeta del trabajador?" -- "Sí").
    """

    def get(self, request, pk):
        document_type = get_object_or_404(
            DocumentTypeCatalog, pk=pk, is_notification_template=True,
        )
        if not document_type.content_html.strip():
            messages.error(
                request,
                "«%s» todavía no tiene contenido -- edítala antes de generar un documento."
                % document_type.label,
            )
            return redirect(reverse("new_ui:circulars_edit", args=[document_type.pk]))
        companies = CompanyFiscalProfile.objects.select_related(
            "administrator",
        ).order_by("legal_name")
        from worksites.models import Worksite
        worksites = Worksite.objects.filter(is_active=True).order_by("name")
        return render(request, "new_ui/circulars/circular_generate.html", {
            "document_type": document_type,
            "companies": companies,
            "worksites": worksites,
        })

    def post(self, request, pk):
        document_type = get_object_or_404(
            DocumentTypeCatalog, pk=pk, is_notification_template=True,
        )
        company = get_object_or_404(CompanyFiscalProfile, pk=request.POST.get("company_id"))
        worker = get_object_or_404(PersonIdentity, pk=request.POST.get("person_id"))
        administrator = company.administrator

        worksite = None
        worksite_id = request.POST.get("worksite_id", "").strip()
        if worksite_id:
            from worksites.models import Worksite
            worksite = get_object_or_404(Worksite, pk=worksite_id)

        rendered_body = _render_document_variables(
            document_type.content_html, worker=worker,
            administrator=administrator, company=company,
            worksite=worksite,
        )
        letter_format = is_letter_format(document_type.content_html)
        logo_data_uri = _get_letterhead_logo_data_uri() if letter_format else None
        heading_html = "" if letter_format else "<h1>%s</h1>" % document_type.label
        logo_html = (
            '<div style="text-align:center;margin-bottom:12px;">'
            '<img src="%s" style="max-height:70px;"></div>' % logo_data_uri
            if logo_data_uri else ""
        )
        html_content = (
            "<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'>"
            "<style>"
            "body{font-family:Arial,sans-serif;font-size:11pt;margin:2.5cm 2cm}"
            "h1{font-size:14pt;margin-bottom:18px}"
            "</style></head><body>"
            "%s%s%s"
            "</body></html>"
        ) % (logo_html, heading_html, rendered_body)

        import weasyprint
        pdf_bytes = weasyprint.HTML(string=html_content).write_pdf()

        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        subject_label = "%s %s, %s" % (
            worker.first_surname, worker.second_surname, worker.given_name,
        )
        try:
            upload_subject_document(
                subject=worker, domain_content_type=person_ct,
                document_type=document_type, data=pdf_bytes,
                original_filename="%s_%s.pdf" % (
                    naming_service._sanitize_token(document_type.label),
                    timezone.now().strftime("%Y%m%d"),
                ),
                typed_date=None, subject_label=subject_label,
                uploaded_by=getattr(request.user, "company_user", None),
            )
        except SubjectUploadError as exc:
            messages.error(request, "No se pudo guardar el documento generado: %s" % exc)
            return redirect(reverse("new_ui:circulars_generate", args=[document_type.pk]))

        messages.success(
            request,
            "Documento «%s» generado para %s %s y guardado en su carpeta."
            % (document_type.label, worker.given_name, worker.first_surname),
        )
        # Nueva interfaz: vuelve a Personal con esa persona y sus
        # documentos a la vista.
        from new_ui.lists import person_name
        from new_ui.state import get_key, save_keys

        tabs = get_key(request.user.company_user, "nui", "tabs", {}) or {}
        tabs["per:listado"] = "documentos"
        save_keys(request.user.company_user, "nui", {
            "scope_per": {"pk": str(worker.pk),
                          "label": person_name(worker)},
            "tabs": tabs,
        })
        return redirect("%s?s=per" % reverse("new_ui:home"))


class CircularGeneratePersonSearchView(DocsUploadAccessMixin, View):
    """GET: fragmento de sugerencias de trabajador para "Generar
    documento" -- ver _circular_generate_person_search."""

    def get(self, request):
        results = _circular_generate_person_search(request)
        search_performed = len(request.GET.get("q", "").strip()) >= 2
        return render(
            request,
            "new_ui/circulars/_circular_generate_person_options.html",
            {"results": results, "search_performed": search_performed},
        )


class PersonalDocutenExportView(DocsUploadAccessMixin, View):
    """
    POST: one of the three Docuten files for a circular.

    ---

    H30 (S124), punto 4. POST con `tipo` (código de una circular con
    firma), `person_ids`, `archivo` (`pdf`, `csv` o `pasos`) y, si la
    circular lleva datos de obra, `worksite_id`: devuelve ese
    archivo suelto (`panel.docuten_export.build_file`). El panel pide
    los tres seguidos con un solo clic -- nunca un ZIP (Miguel Ángel:
    "¿para qué vamos a darle una cosa que tiene que descomprimir?").
    Cabeceras `X-Docuten-Included`/`X-Docuten-Excluded` para el aviso
    del panel. Solo lectura: no crea documentos ni acuses.
    """

    def post(self, request):
        import json
        from urllib.parse import quote

        from django.http import JsonResponse

        from new_ui.docuten_export import (
            FILE_KINDS, DocutenExportError, build_file,
        )
        from worksites.models import Worksite

        person_ids = request.POST.getlist("person_ids")
        type_code = request.POST.get("tipo", "").strip()
        kind = request.POST.get("archivo", "").strip()
        if not person_ids:
            return JsonResponse(
                {"ok": False, "error": "No hay ninguna persona seleccionada."},
                status=400,
            )
        if not type_code:
            return JsonResponse(
                {"ok": False, "error": "Falta elegir la circular."},
                status=400,
            )
        if kind not in FILE_KINDS:
            return JsonResponse(
                {"ok": False, "error": "Archivo no válido."}, status=400,
            )
        document_type = get_object_or_404(
            DocumentTypeCatalog, code=type_code, is_active=True,
            is_notification_template=True, requires_signature=True,
        )
        people = list(PersonIdentity.objects.filter(
            pk__in=person_ids,
        ).order_by("first_surname", "second_surname", "given_name"))
        worksite = None
        worksite_id = request.POST.get("worksite_id", "").strip()
        if worksite_id:
            worksite = get_object_or_404(Worksite, pk=worksite_id)
        try:
            filename, data, content_type, included, excluded = build_file(
                document_type, people, kind, worksite=worksite,
            )
        except DocutenExportError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        if not included:
            return JsonResponse({
                "ok": False,
                "error": "Ninguna persona seleccionada se puede incluir: %s."
                % "; ".join(
                    "%s %s: %s" % (p.given_name, p.first_surname, reason)
                    for p, reason in excluded
                ),
            }, status=400)

        response = HttpResponse(data, content_type=content_type)
        response["Content-Disposition"] = (
            "attachment; filename*=UTF-8''%s" % quote(filename)
        )
        response["X-Docuten-Filename"] = quote(filename)
        response["X-Docuten-Included"] = str(len(included))
        response["X-Docuten-Excluded"] = json.dumps([
            "%s %s" % (person.given_name, person.first_surname)
            for person, _reason in excluded
        ])
        return response


# ------------------------------------------------- ventanas (S163, 24/11)
class CircularSheetView(DocsUploadAccessMixin, View):
    """
    GET: one circular template in the viewer.

    ---

    GET: una plantilla de circular en el visor (al pulsarla): su
    contenido y lo que se hace con ella (editar el contenido, generar
    para una persona, descargar en PDF o Word, con o sin firma).
    """

    def get(self, request, pk):
        document_type = get_object_or_404(
            DocumentTypeCatalog, pk=pk, is_notification_template=True)
        return render(request, "new_ui/circulars/_circular_sheet.html", {
            "doc_type": document_type,
            "family": DocumentTypeCatalog.family_label(
                document_type.family, for_person=True),
        })


class CircularNewFormView(DocsUploadAccessMixin, View):
    """
    GET: «Nueva circular» in the viewer (name, family and audience as
    buttons, no dropdowns).

    ---

    GET: la ventana de «Nueva circular»: nombre, familia y a quién va
    dirigida (botones, sin desplegables). Al crearla se pasa a escribir
    su contenido.
    """

    def get(self, request):
        return render(request, "new_ui/circulars/_circular_new.html", {
            "families": [
                (code, DocumentTypeCatalog.family_label(
                    code, for_person=True))
                for code, _label in DocumentTypeCatalog.FAMILY_CHOICES],
            "domains": [
                (code, label) for code, label
                in DocumentTypeCatalog.DOMAIN_CHOICES
                if code in _CIRCULAR_DOMAINS],
        })


class CircularSentSheetView(DocsUploadAccessMixin, View):
    """
    GET: one delivered circular in the viewer.

    ---

    GET: una circular entregada (Enviadas): a quién, cuándo, por qué
    canal, el estado del WhatsApp y cuándo la leyó, el documento que
    recibió y el contenido de la circular.
    """

    def get(self, request, pk):
        from document_explorer.models import DocumentAcknowledgment

        ack = get_object_or_404(DocumentAcknowledgment.objects.select_related(
            "person", "document_type", "worksite"), pk=pk)
        status_label = {
            "queued": "en cola", "accepted": "aceptado", "sending":
            "enviándose", "sent": "enviado", "delivered": "entregado",
            "read": "leído", "failed": "fallido", "undelivered":
            "no entregado"}.get((ack.whatsapp_status or "").lower(),
                                ack.whatsapp_status)
        return render(request, "new_ui/circulars/_circular_sent.html", {
            "ack": ack, "status_label": status_label,
        })
