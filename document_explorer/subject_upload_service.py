# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/subject_upload_service.py
"""
H30 (S48). Subida de un documento nuevo desde la ficha de un sujeto
(máquina o persona) -- el flujo real que sustituye a escribir nombres
de archivo a mano. Miguel Ángel, verbatim: "el supervisor de
documentación entra en la ficha del operario o del centro de gasto.
Ahí ya es donde sube la documentación [...] Lo único que necesitamos
es que introduzca las fechas de actualización, compararlas con OCR o
con Gemini."

Flujo:
1. El sujeto y el `document_type` ya se conocen por contexto (el
   supervisor pulsó "Actualizar ITV" en la ficha de A-45, p. ej.) --
   nunca se le pide escribir nada de eso.
2. Construye el nombre con `naming_service` (mismo esquema fijo que
   ya usa el resto de la plataforma) -- A SALVO DE COLISIONES (S102):
   si ya existe una entrada viva con ese mismo nombre virtual
   (`move_service._virtual_location_taken`, mismo mecanismo que usa
   `classification_service` para renombrados), se añade el ordinal
   `_1`/`_2`/... hasta encontrar uno libre, EXACTAMENTE igual que
   cuando la clasificación automática detecta un duplicado real.
   INCIDENTE REAL S102: antes se subía siempre al mismo nombre/blob
   sin comprobar nada -- 4 subidas seguidas del mismo tipo de
   documento en el mismo día sobrescribieron 4 veces el mismo objeto
   real en GCS, perdiendo sin aviso el contenido anterior cada vez.
   Miguel Ángel, verbatim: "jamás sobreescribir el blob real, ya que
   los documentos deben quedar siempre como históricos cuando dejan
   de ser los vigentes."
3. Sube el archivo real a GCS (`gcs_service.upload_bytes`) y crea la
   fila de `DocumentIndexEntry` -- misma carpeta que los documentos
   ya existentes de ese sujeto (mismo criterio que
   `resolve_or_create_machine_asset`: si ya hay un lugar real,
   usarlo, nunca inventar uno nuevo).
4. Extrae el texto real del documento y resuelve su fecha con
   `_resolve_date_and_text` -- heurística de nombre, texto embebido
   del PDF, Cloud Vision API, y Gemini como último recurso -- NUNCA
   OCR local (Tesseract/PythonAnywhere), decisión explícita de Miguel
   Ángel (S102). El texto se cachea siempre en `ocr_text`; la fecha
   resuelta solo si el supervisor no escribió una a mano (esa manda).
   Si ambas existen y no coinciden, se avisa sin bloquear la subida.
5. Aplica sustitución (`vigencia_service.evaluate_substitution`)
   contra los documentos ya existentes del mismo tipo y sujeto,
   SIEMPRE -- ya no solo cuando `document_type.tracks_expiry=True`
   (S102, mismo criterio que ya llevaba corregido desde S100 el flujo
   de alta -- `evaluate_substitution()` ya sabe decidir por
   `issue_date` cuando no hay `expiry_date`, e incluso por
   `indexed_at` cuando no hay ninguna fecha, ver `vigencia_service`):
   el más reciente queda vigente, los demás se marcan
   `is_obsolete=True` -- NUNCA se mueven ni se borran (4.12), y queda
   registro en `DocumentSubstitutionLog` para trazabilidad real.
"""
import mimetypes

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from document_explorer import naming_service
from document_explorer.date_verification_service import (
    extract_expiry_via_gemini,
)
from document_explorer.filename_date_service import extract_date_by_filename
from document_explorer.index_writer import ensure_folder_chain
from document_explorer.models import (
    DocumentIndexEntry, PersonIdentity, path_digest,
)
from document_explorer.move_service import _virtual_location_taken
from document_explorer.required_documentation_service import (
    get_required_type_ids,
)
from document_explorer.vigencia_selector import current_fn_for
from document_management.models import DocumentSubstitutionLog
from document_management.vigencia_service import (
    DocumentSnapshot, evaluate_substitution,
)
from fleet.models import MachineAsset
from ivr_config.models import Company
from spare_parts.gcs_service import upload_bytes

BUCKET = "cgs_grupo_alvarez"


class SubjectUploadError(Exception):
    pass


def content_type_of(data, filename=""):
    """
    Real MIME type from the bytes, then from the file name.

    ---

    Tipo real del archivo: por sus propios bytes (PDF, PNG, JPEG, WebP)
    y, si no, por la extensión. S125: antes todo lo que no era PDF se
    guardaba como application/octet-stream -- las fotos subidas desde
    la ficha o por WhatsApp no se podían pasar a Gemini (400) ni verse
    como imagen.
    """
    if data[:5] == b"%PDF-":
        return "application/pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    guessed, _encoding = mimetypes.guess_type(filename or "")
    return guessed or "application/octet-stream"


def _resolve_company():
    """
    Ni MachineAsset ni PersonIdentity comparten la misma forma de
    llegar a la empresa (MachineAsset.company es FK directa;
    PersonIdentity no tiene ningun campo de empresa -- ver docstring
    del modelo). Dado que existe exactamente UNA fila `Company` en
    toda la plataforma (confirmado con datos reales, mismo hecho ya
    documentado en `classification_service._DEFAULT_MACHINE_COMPANY_
    CODE`), se resuelve siempre así -- nunca depende del tipo de
    sujeto.
    """
    company = Company.objects.first()
    if not company:
        raise SubjectUploadError(
            "No existe ninguna fila Company en la plataforma -- no "
            "se puede registrar la sustitución."
        )
    return company


def _resolve_target_folder(domain_content_type, domain_object_id, subject):
    """
    Reutiliza la carpeta real donde ya vive la documentación de este
    sujeto -- nunca inventa una nueva. Si el sujeto no tiene ningún
    documento todavía, cae a `subject.folder_path` (PersonIdentity) o
    a un error explícito para MACHINE (una máquina sin ningún
    documento previo no tiene carpeta real de la que partir -- se
    pide al supervisor que suba el primer documento por la vía
    normal del explorador, no desde aquí).
    """
    existing = DocumentIndexEntry.objects.filter(
        bucket=BUCKET, domain_content_type=domain_content_type,
        domain_object_id=domain_object_id,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).order_by("-id").first()
    if existing:
        return existing.parent_path

    folder_path = getattr(subject, "folder_path", None)
    if folder_path:
        return folder_path.strip("/")

    raise SubjectUploadError(
        "Este sujeto todavía no tiene ningún documento indexado -- "
        "no hay una carpeta real de la que partir. Sube el primer "
        "documento por la vía normal del explorador de archivos."
    )


def _build_filename(subject, document_type_code, upload_date, extension,
                    ordinal=None):
    if isinstance(subject, MachineAsset):
        return naming_service.build_filename_machine(
            subject.code, document_type_code, upload_date,
            ordinal=ordinal, extension=extension,
        )
    return naming_service.build_filename_personal(
        subject.first_surname, subject.second_surname,
        subject.given_name, document_type_code, upload_date,
        ordinal=ordinal, extension=extension,
    )


def _resolve_free_filename(subject, document_type_code, upload_date,
                           extension, target_folder):
    """
    Igual que `_build_filename`, pero a salvo de colisiones (S102):
    si el nombre "base" (sin ordinal) ya está en uso por una entrada
    viva en esa misma carpeta virtual, añade `_1`, `_2`... hasta
    encontrar uno libre -- mismo mecanismo
    (`move_service._virtual_location_taken`) y misma convención de
    ordinal que ya usa `classification_service` para renombrados con
    colisión real. Nunca sube al mismo nombre/blob que un documento ya
    existente -- ver incidente real S102 (subida silenciosa
    sobrescribiendo el blob real 4 veces seguidas).
    """
    filename = _build_filename(
        subject, document_type_code, upload_date, extension,
    )
    ordinal = 1
    while _virtual_location_taken(BUCKET, target_folder, filename):
        filename = _build_filename(
            subject, document_type_code, upload_date, extension,
            ordinal=ordinal,
        )
        ordinal += 1
    return filename


def _resolve_date_and_text(document_type, filename, data, content_type):
    """
    Motor de resolución de fecha + texto para la subida desde la
    ficha del sujeto (H31, S102). Decisión explícita de Miguel Ángel,
    verbatim: "el texto lo tenemos que extraer con llamadas a...
    Cloud Vision, nunca jamás con OCR de PythonAnywhere" -- NUNCA usa
    Tesseract local (`date_verification_service.extract_text`/
    `ocr_pdf_to_text`), aunque sea la vía más barata; el coste de CPU
    compartida real de PythonAnywhere y su cuota diaria por cuenta ya
    causó la migración a Cloud Vision en el alta (H31, S100, ver
    `personal_intake_service.extract_one_document`) -- este flujo
    reutiliza exactamente ese mismo motor, nunca uno propio nuevo:

    1. Heurística de nombre de archivo
       (`filename_date_service.extract_date_by_filename`) -- gratis,
       sin abrir el archivo.
    2. Texto real incrustado del PDF (`personal_intake_service.
       _pdf_embedded_text`) -- gratis, instantáneo, más fiable que
       cualquier OCR cuando el documento no es un escaneo/foto.
    3. Cloud Vision API (`personal_intake_service._cloud_vision_text`)
       -- nube de Google, sin CPU local, responde en menos de un
       segundo.
    4. Gemini Vision directo sobre el archivo -- último recurso, solo
       si nada de lo anterior encontró ninguna fecha.

    H31 (S111): si ninguna fecha se resuelve en las 2 primeras
    páginas, reintenta automáticamente con las páginas 3-4 antes de
    caer a Gemini (ver `cloud_vision_service.extract_text_for_dates()`
    para el caso real que lo motivó -- 15 de 16 personas "sin fecha"
    la tenían en la página 3, en la cláusula CUARTA del impreso de
    "fijo discontinuo" del SEPE).

    Devuelve (field, date, text, source): `field` es "expiry"/"issue"
    o None si nada encontró fecha; `text` es el texto real extraído
    (embebido o Cloud Vision, de todas las páginas realmente leídas)
    -- quien llama lo cachea en `DocumentIndexEntry.ocr_text` para no
    repetir la extracción; `source` identifica el paso que resolvió
    la fecha, para el aviso de discrepancia al supervisor.
    """
    by_name = extract_date_by_filename(document_type.code, filename)
    if by_name:
        field, date_value = by_name
        return field, date_value, "", "nombre_archivo"

    from document_explorer.cloud_vision_service import extract_text_for_dates

    text, expiry, issue, other, _paginas = extract_text_for_dates(
        filename, data,
    )

    if expiry:
        return "expiry", expiry, text, "Cloud Vision"
    if issue:
        return "issue", issue, text, "Cloud Vision"
    if len(other) == 1:
        # Fecha encontrada, sin contexto claro de caducidad ni
        # emisión -- mismo criterio ya usado en el resto de la
        # plataforma: una única fecha ambigua se trata como la
        # relevante, mejor que ninguna.
        return "issue", other[0], text, "Cloud Vision"

    gemini_expiry = extract_expiry_via_gemini(data, filename)
    if gemini_expiry:
        return "expiry", gemini_expiry, text, "Gemini"

    return None, None, text, None


def _queue_entry_hooks(subject, document_type, entry):
    """
    Queue the reading hooks of a document that has just entered.

    ---

    Encola los enganches de un documento recién entrado (Celery, tras
    confirmar la transacción): un permiso de conducción se lee su
    matriz de clases, y un contrato/alta puede cambiar la empresa de la
    persona (H30, S125). S126: antes estaban al final de
    `upload_subject_document`, después de la salida anticipada de los
    tipos acumulables -- y CONTRATO, ALTA, prórroga y modificación son
    acumulables, así que un contrato subido desde la ficha nunca
    recalculaba la empresa.
    """
    from document_explorer.driving_licence_service import queue_harvest

    queue_harvest(entry)
    if isinstance(subject, PersonIdentity):
        from document_explorer.employer_service import (
            queue_contract_refresh,
        )

        queue_contract_refresh(subject, document_type.code, entry)


def upload_subject_document(
    *, subject, domain_content_type, document_type, data, original_filename,
    typed_date, subject_label, uploaded_by=None, typed_issue_date=None,
    filename_date=None,
):
    """
    Ejecuta el flujo completo. Devuelve un dict:
        {
            "entry": DocumentIndexEntry (la fila creada),
            "warning": dict|None (de verify_typed_date, o None),
            "superseded_count": int,
        }
    Lanza `SubjectUploadError` si no se puede resolver una carpeta
    destino real.

    `uploaded_by`: CompanyUser que hace la subida (H30 S50) -- se
    añade como contacto de las alertas de caducidad, junto con los
    DOCS_SUPERVISOR reales (ver get_docs_supervisor_contacts()),
    aunque quien suba no sea documentación (p. ej. un ADMIN subiendo
    en su nombre). Nunca bloquea la subida si viene None.

    `typed_issue_date` (H30 S123): fecha del documento escrita a mano
    en la ficha para los tipos sin caducidad (un contrato: su fecha de
    inicio). Manda sobre la de Cloud Vision/Gemini, igual que
    `typed_date` para la caducidad -- en S122 el OCR cogía la fecha de
    nacimiento de los contratos y los dejaba fuera de su periodo.

    `filename_date` (H30 S127): fecha del nombre de archivo cuando se
    conoce la del propio documento (documentos sacados de un dossier,
    `dossier_service`). Sin ella, el nombre lleva la fecha de subida,
    como desde la ficha.
    """
    extension = (
        original_filename.rsplit(".", 1)[-1]
        if "." in original_filename else "pdf"
    )
    target_folder = _resolve_target_folder(
        domain_content_type, subject.pk, subject,
    )
    today = timezone.now().date()
    ensure_folder_chain(BUCKET, target_folder)
    filename = _resolve_free_filename(
        subject, document_type.code, filename_date or today, extension,
        target_folder,
    )
    blob_name = "%s/%s" % (target_folder, filename)
    content_type = content_type_of(data, filename)
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
        domain_content_type=domain_content_type,
        domain_object_id=subject.pk,
        expiry_date=typed_date if document_type.tracks_expiry else None,
        issue_date=typed_issue_date,
    )

    # H31 (S102): antes se usaba `verify_typed_date()` (Tesseract
    # local) solo para comparar y avisar -- el texto y la fecha que sí
    # llegaba a leer se tiraban siempre. Miguel Ángel, verbatim: "la
    # extracción de texto debe persistir en BBDD [...] el texto lo
    # tenemos que extraer con llamadas a... Cloud Vision, nunca jamás
    # con OCR de PythonAnywhere." Se usa ahora `_resolve_date_and_text`
    # (heurística de nombre -> texto embebido -> Cloud Vision ->
    # Gemini, NUNCA Tesseract) y se cachea todo lo que devuelva: el
    # texto en `ocr_text` (nunca se repetirá la extracción sobre este
    # documento, sea cual sea `tracks_expiry`), y la fecha resuelta en
    # `expiry_date` (solo si el tipo la admite) o `issue_date` -- solo
    # cuando el supervisor no escribió una a mano, que sigue mandando
    # si la hay.
    engine_field, engine_date, ocr_text, engine_source = (
        _resolve_date_and_text(
            document_type, original_filename, data, content_type,
        )
    )
    warning = None
    # S123: el aviso compara con la fecha escrita del mismo campo que
    # ha leído el motor (caducidad o fecha del documento).
    compared_date = (
        typed_issue_date if engine_field == "issue" else typed_date
    )
    if (
        engine_date is not None and compared_date is not None
        and engine_date != compared_date
    ):
        warning = {
            "system_date": engine_date, "typed_date": compared_date,
            "source": engine_source,
        }

    update_fields = []
    if ocr_text:
        entry.ocr_text = ocr_text
        update_fields.append("ocr_text")
    if engine_date is not None:
        if (
            engine_field == "expiry" and document_type.tracks_expiry
            and not entry.expiry_date
        ):
            entry.expiry_date = engine_date
            update_fields.append("expiry_date")
        elif engine_field == "issue" and not entry.issue_date:
            entry.issue_date = engine_date
            update_fields.append("issue_date")
    if update_fields:
        entry.save(update_fields=update_fields)

    # H30 (S122): aquí se creaban las 3 alertas 30/15/7 de H30/S50. Ya
    # no: los avisos se calculan en vivo desde los requisitos de
    # documentación y el ámbito de cada supervisor
    # (document_notice_service / notice_delivery_service).

    # S102: la sustitución YA NO se limita a `tracks_expiry=True` --
    # `evaluate_substitution()` sabe decidir igual de bien por
    # `issue_date`, e incluso por `indexed_at` cuando no hay ninguna
    # fecha (ver `vigencia_service`), mismo criterio que ya llevaba
    # corregido desde S100 el flujo de alta (`views_documentation_h30.
    # _process_alta_documents`). Limitarlo a `tracks_expiry` era
    # justo lo que dejaba varios documentos "vigentes" a la vez sin
    # ningún criterio real (incidente real S102, `CONTRATO`).
    superseded_count = 0
    company = _resolve_company()
    # H30 (S122): un tipo acumulable (varios vigentes a la vez --
    # contratos, altas, cursos, entregas...) nunca entra en la
    # sustitución: vigencia_service deja este filtro al llamador y aquí
    # faltaba, así que cada documento nuevo dejaba obsoleto al anterior.
    if document_type.is_cumulative:
        _queue_entry_hooks(subject, document_type, entry)
        return {
            "entry": entry, "warning": warning,
            "superseded_count": superseded_count,
        }
    siblings_qs = DocumentIndexEntry.objects.filter(
        bucket=BUCKET, document_type=document_type,
        domain_content_type=domain_content_type,
        domain_object_id=subject.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
        is_obsolete=False,
    ).exclude(pk=entry.pk)
    existing_snapshots = [
        DocumentSnapshot(
            identifier=sibling.pk, expiry_date=sibling.expiry_date,
            issue_date=sibling.issue_date, indexed_at=sibling.indexed_at,
        )
        for sibling in siblings_qs
    ]
    incoming_snapshot = DocumentSnapshot(
        identifier=entry.pk, expiry_date=entry.expiry_date,
        issue_date=entry.issue_date, indexed_at=entry.indexed_at,
    )
    result = evaluate_substitution(
        incoming_snapshot, existing_snapshots,
        current_fn=current_fn_for(
            document_type, get_required_type_ids(subject),
        ),
    )
    if result.incoming_should_prevail and result.existing_to_archive:
        to_obsolete = siblings_qs.filter(
            pk__in=result.existing_to_archive,
        )
        for old_entry in to_obsolete:
            old_entry.is_obsolete = True
            old_entry.save(update_fields=["is_obsolete"])
            DocumentSubstitutionLog.objects.create(
                company=company,
                superseding_content_type=ContentType.objects.get_for_model(
                    DocumentIndexEntry,
                ),
                superseding_object_id=entry.pk,
                superseding_label=entry.name,
                superseded_content_type=ContentType.objects.get_for_model(
                    DocumentIndexEntry,
                ),
                superseded_object_id=old_entry.pk,
                superseded_label=old_entry.name,
                subject_label=subject_label,
                document_type=document_type.code,
                reasoning=result.reasoning,
            )
            superseded_count += 1

    _queue_entry_hooks(subject, document_type, entry)
    return {
        "entry": entry, "warning": warning,
        "superseded_count": superseded_count,
    }
