# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/machine_documents/management/commands/reset_machine_documents.py
"""
Django management command: reset_machine_documents.

Borra TODA la documentación de maquinaria (MachineDocument) de una
empresa -- alertas asociadas, historial de sustituciones, archivos
reales en GCS/local, y las filas de BD -- para dejar el hito H23 "a
cero" antes de una prueba de subida real (S026, Miguel Ángel: "hay
que crear una, hacer una cero... hay que borrar toda la documentación
que haya de maquinaria, porque solamente hemos subido la de la A45").

Borra TODOS los MachineDocument de la empresa, sin filtrar por
máquina -- decisión explícita de Miguel Ángel tras confirmar que no
hay más documentación real subida que la de la A-45 (incluidos los 3
documentos que quedaron sin enrutar correctamente antes del fix de
herencia por carpeta). Si en el futuro hace falta borrar solo una
máquina concreta, añadir --machine-code como filtro adicional -- no
construido ahora porque no hace falta para este caso real.

SIEMPRE en modo dry-run (solo lista lo que borraría) salvo que se pase
--confirm explícito -- nunca se borra nada por accidente. Usa
`python manage.py inventory_machine_documents` ANTES de este comando
para comprobar contra datos reales qué hay exactamente (Miguel Ángel:
"no sea que Yolanda haya subido alguna más y ya esté ahí").

Uso:
    # 1. Comprobar primero qué hay de verdad:
    python -m dotenv run python manage.py inventory_machine_documents --company-id <id>

    # 2. Dry-run (no borra nada, solo lista):
    python -m dotenv run python manage.py reset_machine_documents --company-id <id>

    # 3. Borrado real:
    python -m dotenv run python manage.py reset_machine_documents --company-id <id> --confirm

---

Comando de gestión Django: reset_machine_documents.

Borra toda la documentación de maquinaria de una empresa para dejar
el hito H23 "a cero" antes de una prueba de subida real. Dry-run por
defecto, --confirm obligatorio para borrar de verdad.
"""
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError

from document_management.models import DocumentAlert, DocumentSubstitutionLog
from ivr_config.models import Company
from machine_documents.models import MachineDocument


class Command(BaseCommand):
    help = (
        "Borra TODA la documentación de maquinaria (MachineDocument) "
        "de una empresa -- alertas, historial de sustituciones, "
        "archivos y filas de BD. Dry-run por defecto; --confirm "
        "obligatorio para borrar de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--company-id", type=int, required=True,
            help="pk de ivr_config.Company a limpiar.",
        )
        parser.add_argument(
            "--confirm", action="store_true",
            help="Borra de verdad. Sin este flag, solo lista lo que "
                 "se borraría (dry-run).",
        )

    def handle(self, *args, **options):
        company_id = options["company_id"]
        confirm = options["confirm"]
        try:
            company = Company.objects.get(pk=company_id)
        except Company.DoesNotExist:
            raise CommandError(f"No existe Company #{company_id}.")

        documents = list(
            MachineDocument.objects
            .filter(company=company)
            .select_related("machine_asset"),
        )
        substitution_logs_count = DocumentSubstitutionLog.objects.filter(
            company=company,
        ).count()

        if not documents:
            self.stdout.write(self.style.WARNING(
                f"No hay ningún MachineDocument para {company.name} "
                f"(#{company.pk}) -- nada que borrar.",
            ))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"{'BORRANDO' if confirm else 'DRY-RUN -- se borraría'} "
            f"{len(documents)} MachineDocument de {company.name} "
            f"(#{company.pk}):",
        ))
        for doc in documents:
            machine_label = (
                doc.machine_asset.code if doc.machine_asset
                else "SIN ASIGNAR"
            )
            self.stdout.write(
                f"  #{doc.pk:<6} {machine_label:<12} {doc.status:<12} "
                f"{doc.original_filename!r}",
            )
        self.stdout.write(
            f"  + {substitution_logs_count} entrada(s) de historial "
            f"de sustituciones de la empresa.",
        )

        if not confirm:
            self.stdout.write(self.style.WARNING(
                "\nDry-run -- no se ha borrado nada. Repite con "
                "--confirm para borrar de verdad.",
            ))
            return

        content_type = ContentType.objects.get_for_model(MachineDocument)
        deleted_alerts = 0
        deleted_files = 0
        for doc in documents:
            alerts_qs = DocumentAlert.objects.filter(
                content_type=content_type, object_id=doc.pk,
            )
            deleted_alerts += alerts_qs.count()
            alerts_qs.delete()
            if doc.source_file:
                doc.source_file.delete(save=False)
                deleted_files += 1
            doc.delete()

        DocumentSubstitutionLog.objects.filter(company=company).delete()

        self.stdout.write(self.style.SUCCESS(
            f"\nBorrados {len(documents)} MachineDocument, "
            f"{deleted_alerts} alerta(s), {deleted_files} archivo(s) "
            f"real(es), y {substitution_logs_count} entrada(s) de "
            f"historial de sustituciones. {company.name} queda a "
            f"cero en documentación de maquinaria.",
        ))
