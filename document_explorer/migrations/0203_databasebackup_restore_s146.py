# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0203_databasebackup_restore_s146.py
# H24 (S146): restauración de una copia de la BD desde el panel (solo
# administradores).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0202_databasebackup_s146"),
    ]

    operations = [
        migrations.AddField(
            model_name="databasebackup",
            name="restore_status",
            field=models.CharField(blank=True, choices=[("running", "Restaurando"), ("done", "Restaurada"), ("failed", "Restauración fallida")], default="", max_length=20, verbose_name="Restauración"),
        ),
        migrations.AddField(
            model_name="databasebackup",
            name="restore_requested_by",
            field=models.CharField(blank=True, default="", max_length=150, verbose_name="Restauración pedida por"),
        ),
        migrations.AddField(
            model_name="databasebackup",
            name="restore_started_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Restauración empezada"),
        ),
        migrations.AddField(
            model_name="databasebackup",
            name="restore_finished_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Restauración terminada"),
        ),
        migrations.AddField(
            model_name="databasebackup",
            name="restore_safety_copy",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="Copia previa a la restauración"),
        ),
        migrations.AddField(
            model_name="databasebackup",
            name="restore_error",
            field=models.TextField(blank=True, default="", verbose_name="Error de la restauración"),
        ),
    ]
