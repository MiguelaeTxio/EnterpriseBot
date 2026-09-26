# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0147_driving_licence_matrix_s120.py
"""
H30 (S120). Permiso de conducción como matriz de clases.

- Crea `DrivingLicenceCategory` y siembra las 14 clases vigentes
  (art. 4.2 RGC), confirmadas por Miguel Ángel en S120.
- Crea `DrivingLicenceGrant`: una fila por clase impresa en un carné
  (`DocumentIndexEntry` de tipo CARNET_CONDUCIR), con primera
  expedición, caducidad y códigos. Tabla nueva, vacía -- la rellena
  el comando de recolección (punto 3 de la hoja de ruta).
- Añade `JobPosition.required_driving_categories` (M2M, blank=True):
  ningún requisito existente cambia de comportamiento hasta que se
  marque alguna clase desde el panel.

Sin RemoveField de `PersonIdentity.driving_license_expiry_date` aquí
-- pendiente de decisión aparte (tiene datos reales del Excel).
"""
import django.db.models.deletion
from django.db import migrations, models


CATEGORIES = [
    ("AM", "Ciclomotores y cuatriciclos ligeros"),
    ("A1", "Motocicletas hasta 125 cm³ y 11 kW"),
    ("A2", "Motocicletas hasta 35 kW"),
    ("A", "Motocicletas y triciclos de motor"),
    ("B", "Turismos hasta 3.500 kg y 8 pasajeros"),
    ("BE", "B con remolque de más de 750 kg (remolque hasta 3.500 kg)"),
    ("C1", "Camiones de más de 3.500 kg hasta 7.500 kg"),
    ("C1E", "C1 con remolque de más de 750 kg (conjunto hasta 12.000 kg)"),
    ("C", "Camiones de más de 3.500 kg"),
    ("CE", "C con remolque de más de 750 kg"),
    ("D1", "Autobuses hasta 16 pasajeros y 8 m"),
    ("D1E", "D1 con remolque de más de 750 kg"),
    ("D", "Autobuses de más de 8 pasajeros"),
    ("DE", "D con remolque de más de 750 kg"),
]


def seed_categories(apps, schema_editor):
    """
    Seed the 14 current Spanish driving licence classes.
    ---
    Siembra las 14 clases vigentes, idempotente (update_or_create).
    """
    category_model = apps.get_model(
        "document_explorer", "DrivingLicenceCategory",
    )
    for order, (code, label) in enumerate(CATEGORIES, start=1):
        category_model.objects.update_or_create(
            code=code,
            defaults={"label": label, "display_order": order},
        )


def unseed_categories(apps, schema_editor):
    """
    Remove the seeded classes.
    ---
    Borra las clases sembradas.
    """
    category_model = apps.get_model(
        "document_explorer", "DrivingLicenceCategory",
    )
    category_model.objects.filter(
        code__in=[code for code, _label in CATEGORIES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0146_undo_machine_document_requirement_s119"),
    ]

    operations = [
        migrations.CreateModel(
            name="DrivingLicenceCategory",
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
                        max_length=4, unique=True, verbose_name="Clase",
                    ),
                ),
                (
                    "label",
                    models.CharField(
                        max_length=120,
                        verbose_name="Vehículos que autoriza",
                    ),
                ),
                (
                    "display_order",
                    models.PositiveSmallIntegerField(
                        default=0, verbose_name="Orden",
                    ),
                ),
            ],
            options={
                "verbose_name": "Clase de permiso de conducción",
                "verbose_name_plural": "Clases de permiso de conducción",
                "ordering": ["display_order"],
            },
        ),
        migrations.CreateModel(
            name="DrivingLicenceGrant",
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
                    "first_issue_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Primera expedición (columna 10)",
                    ),
                ),
                (
                    "expiry_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Caducidad (columna 11)",
                    ),
                ),
                (
                    "codes",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Códigos armonizados tal cual el carné, "
                            "p. ej. 96 o 97."
                        ),
                        max_length=100,
                        verbose_name="Códigos (columna 12)",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Fecha de creación",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Última edición",
                    ),
                ),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="grants",
                        to="document_explorer.drivinglicencecategory",
                        verbose_name="Clase",
                    ),
                ),
                (
                    "entry",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="driving_licence_grants",
                        to="document_explorer.documentindexentry",
                        verbose_name="Carné de conducir",
                    ),
                ),
            ],
            options={
                "verbose_name": "Clase de un carné de conducir",
                "verbose_name_plural": "Clases de carnés de conducir",
                "ordering": ["entry", "category__display_order"],
            },
        ),
        migrations.AddConstraint(
            model_name="drivinglicencegrant",
            constraint=models.UniqueConstraint(
                fields=("entry", "category"),
                name="unique_driving_grant_per_card_and_category",
            ),
        ),
        migrations.AddField(
            model_name="jobposition",
            name="required_driving_categories",
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "H30 (S120). Clases concretas del carné (B, C, CE...) "
                    "que exige este requisito. Cada una se comprueba "
                    "contra la matriz del carné vigente del sujeto: si no "
                    "la tiene, falta; si su fecha ya pasó, caducada."
                ),
                related_name="job_positions",
                to="document_explorer.drivinglicencecategory",
                verbose_name="Clases de permiso de conducción exigidas",
            ),
        ),
        migrations.RunPython(seed_categories, unseed_categories),
    ]
