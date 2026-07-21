# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/machine_documents/management/commands/inventory_machine_documents.py
"""
Django management command: inventory_machine_documents.

Informe de SOLO LECTURA (S026) -- lista TODA la documentación de
maquinaria realmente persistida en BD para una empresa, agrupada por
máquina (incluida "SIN ASIGNAR"), antes de decidir qué borrar. Miguel
Ángel, explícito: "genera un script para ver qué documentación tenemos
realmente. No sea que Yolanda haya subido alguna más y ya esté ahí" --
nunca se borra nada a ciegas, se comprueba primero contra datos
reales.

Nunca escribe en BD ni en GCS. Muestra pk, máquina, estado,
document_type, nombre de archivo original y fecha de creación de cada
MachineDocument -- y de paso, cualquier IngestedFile que se haya
quedado a medias (NEEDS_REVIEW/ERROR/PENDING_ROUTING), que también
cuenta como "documentación ahí metida" aunque nunca llegara a
enrutarse a un MachineDocument real.

Uso:
    python -m dotenv run python manage.py inventory_machine_documents \\
        --company-id <id>

---

Comando de gestión Django: inventory_machine_documents.

Informe de SOLO LECTURA (S026) -- lista toda la documentación de
maquinaria realmente persistida en BD para una empresa, agrupada por
máquina, antes de decidir qué borrar.
"""
from django.core.management.base import BaseCommand, CommandError

from document_ingestion.models import IngestedFile
from ivr_config.models import Company
from machine_documents.models import MachineDocument


class Command(BaseCommand):
    help = (
        "Informe de solo lectura de toda la documentación de "
        "maquinaria (MachineDocument) e ingesta pendiente "
        "(IngestedFile) persistida para una empresa -- nunca borra "
        "nada."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--company-id", type=int, required=True,
            help="pk de ivr_config.Company a inspeccionar.",
        )

    def handle(self, *args, **options):
        company_id = options["company_id"]
        try:
            company = Company.objects.get(pk=company_id)
        except Company.DoesNotExist:
            raise CommandError(f"No existe Company #{company_id}.")

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"=== MachineDocument -- {company.name} (#{company.pk}) ===",
        ))
        documents = (
            MachineDocument.objects
            .filter(company=company)
            .select_related("machine_asset")
            .order_by(
                "machine_asset__code", "-created_at",
            )
        )
        if not documents:
            self.stdout.write("(ninguno)")
        else:
            for doc in documents:
                machine_label = (
                    doc.machine_asset.code if doc.machine_asset
                    else "SIN ASIGNAR"
                )
                self.stdout.write(
                    f"#{doc.pk:<6} {machine_label:<12} "
                    f"{doc.status:<12} "
                    f"tipo={doc.document_type or '(pendiente)':<30} "
                    f"archivo={doc.original_filename!r:<60} "
                    f"subido={doc.created_at:%Y-%m-%d %H:%M} "
                    f"por={doc.uploaded_by}",
                )
        self.stdout.write(f"Total MachineDocument: {documents.count()}")

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"=== IngestedFile pendiente/con incidencia -- {company.name} ===",
        ))
        stuck = (
            IngestedFile.objects
            .filter(company=company)
            .exclude(status=IngestedFile.Status.ROUTED)
            .order_by("-created_at")
        )
        if not stuck:
            self.stdout.write("(ninguno)")
        else:
            for item in stuck:
                self.stdout.write(
                    f"#{item.pk:<6} {item.status:<20} "
                    f"archivo={item.original_filename!r:<60} "
                    f"carpeta={item.source_folder_path!r:<40} "
                    f"lote={item.upload_batch_id} "
                    f"error={item.error_message!r}",
                )
        self.stdout.write(f"Total IngestedFile sin enrutar: {stuck.count()}")
