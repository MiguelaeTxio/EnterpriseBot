# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0051_document_acknowledgment_s69.py
"""
H30 (S69). Principio de diseño critico: plantilla unica + anotacion,
nunca documento duplicado por persona. Decision explicita de Miguel
Angel al auditar `NOMBRAMIENTO RECURSO PREVENTIVO` -- ver anexo H30,
bloque "PRINCIPIO DE DISENO CRITICO", S69.

Dos cambios, mismo commit:

1. `DocumentTypeCatalog.current_template` -- FK opcional a un
   `DocumentIndexEntry` real (nunca un archivo fuera del sistema).
   Cambiar la plantilla (nueva ley, cambio de domicilio...) es
   reapuntar este campo, sin tocar ningun historico.

2. `DocumentAcknowledgment` -- deliberadamente SEPARADO de
   `EpiDelivery` (decision explicita de Miguel Angel, no una fusion):
   los EPIs son un catalogo de objetos fisicos consultado sobre todo
   por posesion actual; esto cubre tipos documentales
   (`DocumentTypeCatalog`: nombramientos, autorizaciones, circulares)
   consultados sobre todo por linea temporal con huecos reales.
   `EpiDelivery` sigue exactamente igual, sin filas todavia en
   produccion -- no hacia falta migrar datos.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0050_seed_media_types_s67"),
    ]

    operations = [
        migrations.AddField(
            model_name="documenttypecatalog",
            name="current_template",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="current_template_for_types",
                to="document_explorer.documentindexentry",
                verbose_name="Plantilla vigente",
                help_text=(
                    "H30 (S69). Plantilla en blanco real de este tipo "
                    "documental (un DocumentIndexEntry mas, nunca un "
                    "archivo aparte fuera del sistema). Decision "
                    "explicita de Miguel Angel: plantilla y anotacion "
                    "separadas -- la entrega a una persona nunca es "
                    "un documento nuevo, es una fila de "
                    "DocumentAcknowledgment que apunta a este tipo. "
                    "Cambiar la plantilla (nueva ley, cambio de "
                    "domicilio...) es reapuntar este campo a un "
                    "DocumentIndexEntry distinto; el historico de "
                    "entregas no se toca ni sabe con que version se "
                    "hizo cada una salvo que "
                    "DocumentAcknowledgment.source_entry lo guarde "
                    "explicito."
                ),
            ),
        ),
        migrations.CreateModel(
            name="DocumentAcknowledgment",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "delivery_date",
                    models.DateField(verbose_name="Fecha de entrega/firma"),
                ),
                (
                    "extraction_method",
                    models.CharField(
                        max_length=10,
                        choices=[
                            ("MANUAL", "Manual (panel)"),
                            ("HEURISTIC", "Heurística de nombre"),
                            ("OCR", "OCR"),
                            ("GEMINI", "Gemini"),
                        ],
                        default="MANUAL",
                        verbose_name="Método de extracción",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Fecha de registro",
                    ),
                ),
                (
                    "document_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="acknowledgments",
                        to="document_explorer.documenttypecatalog",
                        verbose_name="Tipo documental",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="document_acknowledgments",
                        to="document_explorer.personidentity",
                        verbose_name="Persona",
                    ),
                ),
                (
                    "source_entry",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="document_acknowledgments",
                        to="document_explorer.documentindexentry",
                        verbose_name="Documento de origen",
                        help_text=(
                            "Nulo por defecto -- el historico normal "
                            "no guarda copia individual (mismo "
                            "principio que EPIs). Se rellena solo "
                            "cuando un tipo concreto exige conservar "
                            "la version firmada exacta (p. ej. prueba "
                            "legal de firma), decision caso por caso, "
                            "nunca por defecto para todos los tipos."
                        ),
                    ),
                ),
            ],
            options={
                "verbose_name": "Reconocimiento/entrega de documento",
                "verbose_name_plural": "Reconocimientos/entregas de documentos",
                "ordering": ["-delivery_date"],
            },
        ),
        migrations.AddIndex(
            model_name="documentacknowledgment",
            index=models.Index(
                fields=["person", "document_type"],
                name="doc_ack_person_type_idx",
            ),
        ),
    ]
