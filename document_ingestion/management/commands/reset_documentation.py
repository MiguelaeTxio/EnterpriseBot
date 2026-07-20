# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_ingestion/management/commands/reset_documentation.py
"""
Comando de gestión Django: reset_documentation.

Comando destructivo solicitado por Miguel Ángel (S024-bis, tras
encontrar duplicados masivos en las pruebas reales de H23/H25):
"borramos BBDD para tener zona cero de documentación. Y realizar
nuevas pruebas". Sustituye por completo a
machine_documents/management/commands/reset_machine_documents.py
(BORRADO en este mismo commit) -- ese comando quedó obsoleto sin que
nadie lo actualizara tras la migración de Google Drive a Google Cloud
Storage (H23/S022): seguía llamando a spare_parts.gdrive_service, que
ya no es la vía real de persistencia -- hallazgo real detectado al
escribir este comando, corregido en el mismo commit según la
directriz de no dejar hallazgos sin reparar.

A diferencia del comando antiguo (una sola máquina, vía --machine-code),
este cubre TODA la documentación de la plataforma en un solo golpe --
los dos dominios (MachineDocument/PersonalDocument), el staging de
ingesta (IngestedFile), las alertas asociadas (DocumentAlert, vía
ContentType -- nunca se borran solas al borrar el documento porque es
una relación genérica, no un FK con CASCADE) y (S025, hallazgo real
detectado al retomar este comando en la misma sesión que creó el
modelo) el historial de sustituciones (DocumentSubstitutionLog, misma
razón -- relación genérica sin CASCADE, quedaría apuntando a
documentos ya borrados si no se limpia aquí también):

1. DocumentAlert de MachineDocument/PersonalDocument.
2. DocumentSubstitutionLog de MachineDocument/PersonalDocument (S025).
3. MachineDocument -- fila + blob de GCS (MACHINE_DOCUMENTS_BUCKET) +
   archivo local de staging si quedara alguno.
4. PersonalDocument -- igual, PERSONNEL_DOCUMENTS_BUCKET.
5. IngestedFile -- fila + archivo local de staging si quedara alguno
   (normalmente ya se borra solo al enrutar, pero una fila NEEDS_REVIEW
   o ERROR puede conservarlo).

Requiere --confirm -- se niega a ejecutar si no se pasa. --dry-run
muestra qué se borraría sin tocar BD ni GCS. --company limita a una
empresa (por defecto, TODAS -- "zona cero" tal cual lo pidió Miguel
Ángel, sin acotar).

Uso:
    python -m dotenv run python manage.py reset_documentation --confirm
    python -m dotenv run python manage.py reset_documentation --dry-run
    python -m dotenv run python manage.py reset_documentation --company grupo-alvarez --confirm
"""
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError

from document_ingestion.models import IngestedFile
from document_management.models import DocumentAlert, DocumentSubstitutionLog
from ivr_config.models import Company
from machine_documents.models import MachineDocument
from personal_documents.models import PersonalDocument
from spare_parts.gcs_service import (
    MACHINE_DOCUMENTS_BUCKET,
    PERSONNEL_DOCUMENTS_BUCKET,
    delete_file,
)


class Command(BaseCommand):
    """
    Comando destructivo de reinicio completo de documentación (H23 +
    H25 + staging de ingesta + alertas) -- BD + GCS.
    """

    help = (
        "Borra en BD y en GCS toda la documentación de máquinas y "
        "personal, el staging de ingesta y las alertas asociadas "
        "(zona cero). Requiere --confirm."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--company",
            type=str,
            default=None,
            help=(
                "Slug de empresa (ivr_config.Company.slug) para acotar "
                "el borrado. Sin especificar, afecta a TODAS las "
                "empresas."
            ),
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            default=False,
            help="Obligatorio -- confirma la operación destructiva.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Muestra qué se borraría, sin tocar BD ni GCS.",
        )

    def handle(self, *args, **options) -> None:
        dry_run = options["dry_run"]
        company_slug = options["company"]

        if not dry_run and not options["confirm"]:
            raise CommandError(
                "# Operación destructiva -- vuelve a ejecutar con "
                "--confirm para proceder, o con --dry-run para ver "
                "qué se borraría sin tocar nada."
            )

        company_filter = {}
        if company_slug:
            company = Company.objects.filter(slug=company_slug).first()
            if company is None:
                raise CommandError(
                    f"# No existe Company con slug={company_slug!r}."
                )
            company_filter = {"company": company}
            self.stdout.write(f"# Acotado a la empresa {company_slug}.")
        else:
            self.stdout.write(
                "# Sin --company: afecta a TODAS las empresas."
            )

        # ------------------------------------------------------------
        # 1. DocumentAlert -- relación genérica, no se borra sola al
        #    borrar el documento (GenericForeignKey, sin CASCADE).
        # ------------------------------------------------------------
        machine_ct = ContentType.objects.get_for_model(MachineDocument)
        personal_ct = ContentType.objects.get_for_model(PersonalDocument)
        alerts_qs = DocumentAlert.objects.filter(
            content_type__in=[machine_ct, personal_ct],
            **company_filter,
        )
        alerts_count = alerts_qs.count()
        self.stdout.write(f"# {alerts_count} DocumentAlert encontrada(s).")
        if not dry_run:
            alerts_qs.delete()

        # ------------------------------------------------------------
        # 2. DocumentSubstitutionLog (S025) -- misma razón que
        #    DocumentAlert: relación genérica sin CASCADE, hay que
        #    limpiarla explícitamente o quedaría apuntando a
        #    documentos ya borrados por este mismo comando.
        # ------------------------------------------------------------
        substitution_logs_qs = DocumentSubstitutionLog.objects.filter(
            **company_filter,
        )
        substitution_logs_count = substitution_logs_qs.count()
        self.stdout.write(
            f"# {substitution_logs_count} DocumentSubstitutionLog "
            "encontrado(s)."
        )
        if not dry_run:
            substitution_logs_qs.delete()

        # ------------------------------------------------------------
        # 3. MachineDocument -- fila + blob GCS + staging local.
        # ------------------------------------------------------------
        machine_docs = list(MachineDocument.objects.filter(**company_filter))
        self.stdout.write(
            f"# {len(machine_docs)} MachineDocument encontrado(s)."
        )
        for document in machine_docs:
            if dry_run:
                self.stdout.write(
                    f"# [dry-run] Se borraría MachineDocument #{document.pk} "
                    f"({document.display_name or document.original_filename})."
                )
                continue
            if document.gcs_blob_name:
                try:
                    delete_file(MACHINE_DOCUMENTS_BUCKET, document.gcs_blob_name)
                except Exception as exc:
                    self.stdout.write(
                        f"# Aviso: no se pudo borrar el blob GCS de "
                        f"MachineDocument #{document.pk} "
                        f"({document.gcs_blob_name}): {exc}"
                    )
            if document.source_file:
                document.source_file.delete(save=False)
            document.delete()

        # ------------------------------------------------------------
        # 4. PersonalDocument -- igual, PERSONNEL_DOCUMENTS_BUCKET.
        # ------------------------------------------------------------
        personal_docs = list(PersonalDocument.objects.filter(**company_filter))
        self.stdout.write(
            f"# {len(personal_docs)} PersonalDocument encontrado(s)."
        )
        for document in personal_docs:
            if dry_run:
                self.stdout.write(
                    f"# [dry-run] Se borraría PersonalDocument #{document.pk} "
                    f"({document.display_name or document.original_filename})."
                )
                continue
            if document.gcs_blob_name:
                try:
                    delete_file(PERSONNEL_DOCUMENTS_BUCKET, document.gcs_blob_name)
                except Exception as exc:
                    self.stdout.write(
                        f"# Aviso: no se pudo borrar el blob GCS de "
                        f"PersonalDocument #{document.pk} "
                        f"({document.gcs_blob_name}): {exc}"
                    )
            if document.source_file:
                document.source_file.delete(save=False)
            document.delete()

        # ------------------------------------------------------------
        # 5. IngestedFile -- fila + staging local si quedara alguno
        #    (NEEDS_REVIEW/ERROR pueden conservarlo; ROUTED ya lo
        #    borró al enrutar).
        # ------------------------------------------------------------
        ingested_files = list(IngestedFile.objects.filter(**company_filter))
        self.stdout.write(
            f"# {len(ingested_files)} IngestedFile encontrado(s)."
        )
        for ingested in ingested_files:
            if dry_run:
                self.stdout.write(
                    f"# [dry-run] Se borraría IngestedFile #{ingested.pk} "
                    f"({ingested.original_filename})."
                )
                continue
            if ingested.source_file:
                ingested.source_file.delete(save=False)
            ingested.delete()

        if dry_run:
            self.stdout.write(
                "# [dry-run] Fin -- no se ha borrado nada realmente."
            )
        else:
            self.stdout.write(
                f"# Zona cero lista: {alerts_count} alerta(s), "
                f"{substitution_logs_count} registro(s) de sustitución, "
                f"{len(machine_docs)} documento(s) de máquina, "
                f"{len(personal_docs)} documento(s) de personal y "
                f"{len(ingested_files)} archivo(s) en ingesta eliminados "
                f"de BD y GCS."
            )
