# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0217_signing_agent_s153.py
# S153: firma digital con agente (AutoFirma en el ordenador con los
# certificados): alias del certificado por firma, agente y cola de lotes.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0216_companysignature_s153"),
        ("ivr_config", "0060_companyuser_signature_access_s153"),
    ]

    operations = [
        migrations.AddField(
            model_name="companysignature",
            name="certificate_alias",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Certificado digital (alias en el agente)",
            ),
        ),
        migrations.CreateModel(
            name="SignedFormJob",
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
                    "certificate_alias",
                    models.CharField(
                        max_length=255, verbose_name="Certificado (alias)"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pendiente de firma digital"),
                            ("done", "Firmado"),
                            ("error", "Con errores"),
                        ],
                        default="pending",
                        max_length=10,
                        verbose_name="Estado",
                    ),
                ),
                (
                    "notes",
                    models.JSONField(
                        blank=True,
                        default=list,
                        verbose_name="Avisos al rellenar",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="ivr_config.companyuser",
                        verbose_name="Creado por",
                    ),
                ),
                (
                    "signature",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="jobs",
                        to="document_explorer.companysignature",
                        verbose_name="Firma",
                    ),
                ),
            ],
            options={
                "verbose_name": "Lote de firma digital",
                "verbose_name_plural": "Lotes de firma digital",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SignedFormFile",
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
                    "name",
                    models.CharField(max_length=255, verbose_name="Nombre"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pendiente"),
                            ("signing", "Firmándose"),
                            ("done", "Firmado"),
                            ("error", "Error"),
                        ],
                        default="pending",
                        max_length=10,
                        verbose_name="Estado",
                    ),
                ),
                (
                    "unsigned_encrypted",
                    models.BinaryField(verbose_name="PDF generado (cifrado)"),
                ),
                (
                    "signed_encrypted",
                    models.BinaryField(
                        blank=True,
                        null=True,
                        verbose_name="PDF firmado (cifrado)",
                    ),
                ),
                (
                    "error",
                    models.TextField(
                        blank=True, default="", verbose_name="Error"
                    ),
                ),
                ("taken_at", models.DateTimeField(blank=True, null=True)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="files",
                        to="document_explorer.signedformjob",
                        verbose_name="Lote",
                    ),
                ),
            ],
            options={
                "verbose_name": "Documento a firmar",
                "verbose_name_plural": "Documentos a firmar",
                "ordering": ["pk"],
            },
        ),
        migrations.CreateModel(
            name="SigningAgent",
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
                    "name",
                    models.CharField(max_length=120, verbose_name="Nombre"),
                ),
                (
                    "token_hash",
                    models.CharField(
                        max_length=64,
                        unique=True,
                        verbose_name="Huella del código",
                    ),
                ),
                (
                    "host",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=255,
                        verbose_name="Ordenador",
                    ),
                ),
                (
                    "aliases",
                    models.JSONField(
                        blank=True,
                        default=list,
                        verbose_name="Certificados que ve (alias)",
                    ),
                ),
                (
                    "autofirma_version",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=120,
                        verbose_name="AutoFirma",
                    ),
                ),
                (
                    "last_error",
                    models.TextField(
                        blank=True, default="", verbose_name="Último error"
                    ),
                ),
                (
                    "last_seen_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Último contacto"
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="Activo"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="ivr_config.companyuser",
                        verbose_name="Creado por",
                    ),
                ),
            ],
            options={
                "verbose_name": "Agente de firmas",
                "verbose_name_plural": "Agentes de firmas",
                "ordering": ["-created_at"],
            },
        ),
    ]
