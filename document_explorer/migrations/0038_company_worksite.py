# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0038_company_worksite.py
"""
H30 (S58). Tercer tipo de dominio para DocumentIndexEntry:
CompanyWorksite (empresa + obra), junto a MachineAsset/PersonIdentity.
Ver docstring completo del modelo en models.py para el razonamiento
real (verbatim de Miguel Angel) -- solo estructura de esquema aqui.

Reasigna el dominio de PAGO_CORRIENTE de PERSONAL a COMPANY (dato,
via RunPython) -- confirmado con datos reales de S58: de 1.762
archivos, 1.149 viven bajo la carpeta de empresa "GRUAS" y 511 bajo
"TRANSGRUAL", organizados por obra en la practica totalidad de los
casos, nunca por persona salvo la excepcion real ya vista (alta suelta
de un trabajador sobre una relacion ya enviada).

La poblacion real de filas CompanyWorksite y el relinkado de los 1.762
DocumentIndexEntry (incluidos los 274 ya vinculados a PersonIdentity
en el bloque anterior de esta misma sesion) se hace aparte, via
comando de gestion (resolve_company_worksite_domain, dry-run por
defecto) -- nunca en esta migracion, mismo criterio que
resolve_domain_pending_types: una migracion no reprocesa miles de
filas de indice documental con logica de parseo de ruta.
"""
from django.db import migrations, models


def _reasignar_dominio_pago_corriente(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(code="PAGO_CORRIENTE").update(domain="COMPANY")


def _revertir_dominio_pago_corriente(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(code="PAGO_CORRIENTE").update(domain="PERSONAL")


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0037_seed_s57_notif_types"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyWorksite",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "company",
                    models.CharField(
                        help_text=(
                            "Segmento real de carpeta tal cual aparece"
                            " hoy (p. ej. 'GRUAS', 'TRANSGRUAL') --"
                            " nunca normalizado a una lista cerrada."
                        ),
                        max_length=100,
                        verbose_name="Empresa propia",
                    ),
                ),
                (
                    "worksite",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Segmento real de carpeta tal cual aparece"
                            " hoy (p. ej. 'OBRALIA', 'DRAGADOS'). En"
                            " blanco cuando el documento real no vive"
                            " dentro de ninguna subcarpeta de obra."
                        ),
                        max_length=150,
                        verbose_name="Obra/cliente",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Fecha de alta",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Última actualización",
                    ),
                ),
            ],
            options={
                "verbose_name": "Empresa y obra",
                "verbose_name_plural": "Empresas y obras",
                "ordering": ["company", "worksite"],
            },
        ),
        migrations.AddConstraint(
            model_name="companyworksite",
            constraint=models.UniqueConstraint(
                fields=("company", "worksite"),
                name="unique_company_worksite",
            ),
        ),
        migrations.AlterField(
            model_name="documenttypecatalog",
            name="domain",
            field=models.CharField(
                choices=[
                    ("MACHINE", "Maquinaria"),
                    ("PERSONAL", "Personal"),
                    ("BOTH", "Ambos"),
                    ("COMPANY", "Empresa y obra (CompanyWorksite, H30 S58)"),
                ],
                default="BOTH",
                help_text="A qué tipo de entidad aplica este tipo documental.",
                max_length=8,
                verbose_name="Dominio",
            ),
        ),
        migrations.RunPython(
            _reasignar_dominio_pago_corriente,
            _revertir_dominio_pago_corriente,
        ),
    ]
