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
4. Contrasta la fecha escrita por el supervisor contra el propio
   documento (`date_verification_service.verify_typed_date`) --
   nunca decide, solo avisa si no coincide.
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
import datetime

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from document_explorer import naming_service
from document_explorer.date_verification_service import verify_typed_date
from document_explorer.index_writer import ensure_folder_chain
from document_explorer.models import DocumentIndexEntry, path_digest
from document_explorer.move_service import _virtual_location_taken
from document_management.alert_service import (
    create_default_expiry_alerts, get_docs_supervisor_contacts,
)
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
        domain_object_id=domain_object_id, entry_kind=DocumentIndexEntry.KIND_FILE,
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


def _build_filename(subject, document_type_code, upload_date, extension, ordinal=None):
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


def _resolve_free_filename(subject, document_type_code, upload_date, extension, target_folder):
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
    filename = _build_filename(subject, document_type_code, upload_date, extension)
    ordinal = 1
    while _virtual_location_taken(BUCKET, target_folder, filename):
        filename = _build_filename(
            subject, document_type_code, upload_date, extension,
            ordinal=ordinal,
        )
        ordinal += 1
    return filename


def upload_subject_document(
    *, subject, domain_content_type, document_type, data, original_filename,
    typed_date, subject_label, uploaded_by=None,
):
    """
    Ejecuta el flujo completo. Devuelve un dict:
        {
            "entry": DocumentIndexEntry (la fila creada),
            "warning": dict|None (de verify_typed_date, o None),
            "superseded_count": int,
            "alerts_created": int,
        }
    Lanza `SubjectUploadError` si no se puede resolver una carpeta
    destino real.

    `uploaded_by`: CompanyUser que hace la subida (H30 S50) -- se
    añade como contacto de las alertas de caducidad, junto con los
    DOCS_SUPERVISOR reales (ver get_docs_supervisor_contacts()),
    aunque quien suba no sea documentación (p. ej. un ADMIN subiendo
    en su nombre). Nunca bloquea la subida si viene None.
    """
    extension = original_filename.rsplit(".", 1)[-1] if "." in original_filename else "pdf"
    target_folder = _resolve_target_folder(
        domain_content_type, subject.pk, subject,
    )
    today = timezone.now().date()
    ensure_folder_chain(BUCKET, target_folder)
    filename = _resolve_free_filename(
        subject, document_type.code, today, extension, target_folder,
    )
    blob_name = "%s/%s" % (target_folder, filename)
    content_type = (
        "application/pdf" if extension.lower() == "pdf"
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
        domain_content_type=domain_content_type,
        domain_object_id=subject.pk,
        expiry_date=typed_date if document_type.tracks_expiry else None,
    )

    warning = verify_typed_date(
        document_type, original_filename, data, typed_date,
    )

    alerts_created = 0
    if document_type.tracks_expiry and entry.expiry_date:
        # H30 (S50): hueco real detectado -- esta via de subida nunca
        # habia llamado a create_default_expiry_alerts. Ninguna
        # subida hecha desde la ficha del sujeto generaba alerta de
        # caducidad hasta ahora, aunque el motor de envio (Twilio,
        # tarea diaria) llevaba activo desde H26. Se enganchan aqui
        # las 3 alertas por defecto (30/15/7 dias) mas los DOCS_
        # SUPERVISOR reales como contacto, mas quien sube el
        # documento si no es ya uno de ellos.
        alerts = create_default_expiry_alerts(
            document=entry,
            expiry_date=entry.expiry_date,
            document_label=document_type.label,
            subject_label=subject_label,
            company=_resolve_company(),
        )
        contacts = get_docs_supervisor_contacts()
        if uploaded_by is not None and uploaded_by not in contacts:
            contacts.append(uploaded_by)
        for alert in alerts:
            alert.contacts.add(*contacts)
        alerts_created = len(alerts)

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
    result = evaluate_substitution(incoming_snapshot, existing_snapshots)
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

    return {
        "entry": entry, "warning": warning,
        "superseded_count": superseded_count,
    }
