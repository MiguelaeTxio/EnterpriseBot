# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0150_lifting_accessories_s121.py
"""
H30 (S121). Accesorios de elevación, equivalente de los EPIs para la
maquinaria. Diseño cerrado con Miguel Ángel en S121:

- `LiftingAccessoryType`: catálogo editable desde el panel, sembrado
  aquí con los 6 tipos iniciales (decisión 2).
- `LiftingAccessory`: una ficha por accesorio físico, identificado por
  su nº de certificado o serie (decisión 1).
- `LiftingAccessoryAssignment`: entrega a una persona responsable y,
  opcionalmente, a una máquina, con historial (decisión 3).
- `LiftingAccessoryReview`: revisión por accesorio (decisión 4); la
  vigencia es revisión + 12 meses salvo caducidad indicada por el
  supervisor, que prevalece (decisión 5).

Solo tablas nuevas -- ninguna tabla existente cambia.
"""
import django.db.models.deletion
from django.db import migrations, models


ACCESSORY_TYPES = [
    ("ESLINGA_CABLE_ACERO", "Eslinga de cable de acero"),
    ("ESLINGA_POLIESTER_PLANA", "Eslinga de poliéster plana"),
    ("ESLINGA_CADENA", "Eslinga de cadena"),
    ("GRILLETE", "Grillete"),
    ("BALANCIN_SEPARADOR", "Balancín / separador"),
    ("LINEA_CARGA", "Línea de carga"),
]


def seed_types(apps, schema_editor):
    """
    Seed the initial lifting accessory types.
    ---
    Siembra los tipos iniciales, idempotente (update_or_create).
    """
    type_model = apps.get_model("document_explorer", "LiftingAccessoryType")
    for order, (code, label) in enumerate(ACCESSORY_TYPES, start=1):
        type_model.objects.update_or_create(
            code=code,
            defaults={"label": label, "display_order": order},
        )


def unseed_types(apps, schema_editor):
    """
    Remove the seeded types.
    ---
    Borra los tipos sembrados.
    """
    type_model = apps.get_model("document_explorer", "LiftingAccessoryType")
    type_model.objects.filter(
        code__in=[code for code, _label in ACCESSORY_TYPES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0149_sync_state_s120"),
        ("fleet", "0016_sync_state_s120"),
        ("ivr_config", "0044_companyuser_email_signature_html"),
    ]

    operations = [
        migrations.CreateModel(
            name="LiftingAccessoryType",
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
                    "code",
                    models.CharField(
                        help_text=(
                            "Código corto único del tipo de accesorio."
                        ),
                        max_length=40,
                        unique=True,
                        verbose_name="Código",
                    ),
                ),
                (
                    "label",
                    models.CharField(
                        max_length=150, verbose_name="Nombre visible",
                    ),
                ),
                (
                    "display_order",
                    models.PositiveSmallIntegerField(
                        default=0, verbose_name="Orden",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Desactivar en vez de borrar conserva los "
                            "accesorios ya registrados con este tipo."
                        ),
                        verbose_name="Activo",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Fecha de alta",
                    ),
                ),
            ],
            options={
                "verbose_name": "Tipo de accesorio de elevación",
                "verbose_name_plural": "Tipos de accesorio de elevación",
                "ordering": ["display_order", "label"],
            },
        ),
        migrations.CreateModel(
            name="LiftingAccessory",
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
                    "identifier",
                    models.CharField(
                        max_length=100,
                        verbose_name="Nº de certificado / serie",
                    ),
                ),
                (
                    "description",
                    models.CharField(
                        blank=True, max_length=255,
                        verbose_name="Descripción",
                    ),
                ),
                (
                    "dimensions",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Tal cual el certificado, p. ej. '26 mm x 6 m'."
                        ),
                        max_length=100,
                        verbose_name="Medidas",
                    ),
                ),
                (
                    "working_load_kg",
                    models.PositiveIntegerField(
                        blank=True, null=True,
                        verbose_name="Carga de trabajo (kg)",
                    ),
                ),
                (
                    "standard",
                    models.CharField(
                        blank=True,
                        help_text="P. ej. 'EN 13414-1' o 'EN 1492-1'.",
                        max_length=100,
                        verbose_name="Norma",
                    ),
                ),
                (
                    "manufacturer",
                    models.CharField(
                        blank=True, max_length=150,
                        verbose_name="Fabricante / proveedor",
                    ),
                ),
                (
                    "supply_date",
                    models.DateField(
                        blank=True,
                        help_text=(
                            "Fecha del certificado del fabricante. Sin "
                            "ninguna revisión registrada, la vigencia se "
                            "cuenta desde aquí."
                        ),
                        null=True,
                        verbose_name="Fecha de suministro",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Desmarcar al retirar el accesorio; nunca se "
                            "borra."
                        ),
                        verbose_name="En servicio",
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
                        auto_now=True, verbose_name="Última edición",
                    ),
                ),
                (
                    "accessory_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="accessories",
                        to="document_explorer.liftingaccessorytype",
                        verbose_name="Tipo",
                    ),
                ),
                (
                    "certificate_entry",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="lifting_accessories",
                        to="document_explorer.documentindexentry",
                        verbose_name="Certificado del fabricante",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lifting_accessories",
                        to="ivr_config.company",
                        verbose_name="Empresa",
                    ),
                ),
            ],
            options={
                "verbose_name": "Accesorio de elevación",
                "verbose_name_plural": "Accesorios de elevación",
                "ordering": ["accessory_type__display_order", "identifier"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("company", "accessory_type", "identifier"),
                        name="unique_lifting_accessory_per_company_type",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="LiftingAccessoryAssignment",
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
                    "start_date",
                    models.DateField(verbose_name="Fecha de entrega"),
                ),
                (
                    "end_date",
                    models.DateField(
                        blank=True, null=True,
                        verbose_name="Fecha de devolución",
                    ),
                ),
                (
                    "notes",
                    models.TextField(
                        blank=True, verbose_name="Observaciones",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Fecha de registro",
                    ),
                ),
                (
                    "accessory",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assignments",
                        to="document_explorer.liftingaccessory",
                        verbose_name="Accesorio",
                    ),
                ),
                (
                    "machine",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="lifting_accessory_assignments",
                        to="fleet.machineasset",
                        verbose_name="Máquina",
                    ),
                ),
                (
                    "responsible_person",
                    models.ForeignKey(
                        help_text=(
                            "Persona a quien se entrega y responde del "
                            "accesorio."
                        ),
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="lifting_accessory_assignments",
                        to="document_explorer.personidentity",
                        verbose_name="Responsable",
                    ),
                ),
            ],
            options={
                "verbose_name": "Entrega de accesorio de elevación",
                "verbose_name_plural": "Entregas de accesorios de elevación",
                "ordering": ["-start_date", "-id"],
            },
        ),
        migrations.CreateModel(
            name="LiftingAccessoryReview",
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
                    "review_date",
                    models.DateField(verbose_name="Fecha de revisión"),
                ),
                (
                    "explicit_expiry_date",
                    models.DateField(
                        blank=True,
                        help_text=(
                            "Solo si el supervisor la indica: prevalece "
                            "sobre la fecha de revisión + 12 meses."
                        ),
                        null=True,
                        verbose_name="Caducidad indicada",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Fecha de registro",
                    ),
                ),
                (
                    "accessory",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reviews",
                        to="document_explorer.liftingaccessory",
                        verbose_name="Accesorio",
                    ),
                ),
                (
                    "source_entry",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="lifting_accessory_reviews",
                        to="document_explorer.documentindexentry",
                        verbose_name="Documento de la revisión",
                    ),
                ),
            ],
            options={
                "verbose_name": "Revisión de accesorio de elevación",
                "verbose_name_plural": (
                    "Revisiones de accesorios de elevación"
                ),
                "ordering": ["-review_date", "-id"],
            },
        ),
        migrations.RunPython(seed_types, unseed_types),
    ]
