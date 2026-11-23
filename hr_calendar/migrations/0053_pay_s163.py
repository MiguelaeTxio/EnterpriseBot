# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0053_pay_s163.py
# H31 (S163, sesión invasora): Horas y pagos -- qué se paga (por empresa),
# origen y precios de cada trabajador, y periodos liquidados con sus
# líneas (bloqueadas). Solo tablas nuevas.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0063_role_services_s149"),
        ("hr_calendar", "0052_vacationrule_group_person_s163"),
    ]

    operations = [
        migrations.CreateModel(
            name="PaySettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("modes", models.JSONField(blank=True, default=dict, verbose_name="Qué se paga")),
                ("monthly_cap_minutes", models.PositiveIntegerField(blank=True, help_text="Minutos de horas extra al mes que se pagan; lo que pasa va a la bolsa. Vacío = sin tope.", null=True, verbose_name="Tope mensual de horas extra")),
                ("parte_day_minutes", models.PositiveIntegerField(default=480, help_text="Lo que pasa de esto en un día de parte es hora extra.", verbose_name="Jornada de los partes (minutos)")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="pay_settings", to="ivr_config.company", verbose_name="Empresa")),
            ],
            options={
                "verbose_name": "Ajustes de horas y pagos",
                "verbose_name_plural": "Ajustes de horas y pagos",
            },
        ),
        migrations.CreateModel(
            name="PayWorker",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(choices=[("AUTO", "Automático (parte si lo hay, si no fichaje)"), ("CLOCK", "Fichaje"), ("PARTE", "Parte")], default="AUTO", max_length=5, verbose_name="De dónde salen sus horas")),
                ("prices", models.JSONField(blank=True, default=dict, verbose_name="Precios por clase de hora")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company_user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="pay_worker", to="ivr_config.companyuser", verbose_name="Trabajador")),
            ],
            options={
                "verbose_name": "Horas y pagos de un trabajador",
                "verbose_name_plural": "Horas y pagos de los trabajadores",
            },
        ),
        migrations.CreateModel(
            name="PayPeriod",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date_from", models.DateField(verbose_name="Desde")),
                ("date_to", models.DateField(verbose_name="Hasta")),
                ("closed_at", models.DateTimeField(auto_now_add=True, verbose_name="Liquidado el")),
                ("closed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="ivr_config.companyuser", verbose_name="Liquidado por")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pay_periods", to="ivr_config.company", verbose_name="Empresa")),
            ],
            options={
                "verbose_name": "Periodo liquidado",
                "verbose_name_plural": "Periodos liquidados",
                "ordering": ["-date_from", "-pk"],
            },
        ),
        migrations.CreateModel(
            name="PayLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=60, verbose_name="Clase de hora")),
                ("label", models.CharField(max_length=120, verbose_name="Nombre")),
                ("hours", models.DecimalField(decimal_places=2, default=0, max_digits=8, verbose_name="Horas")),
                ("holiday_hours", models.DecimalField(decimal_places=2, default=0, max_digits=8, verbose_name="Horas en festivo")),
                ("price", models.DecimalField(decimal_places=2, default=0, max_digits=8, verbose_name="Precio")),
                ("holiday_price", models.DecimalField(decimal_places=2, default=0, max_digits=8, verbose_name="Precio festivo")),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name="Importe")),
                ("company_user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pay_lines", to="ivr_config.companyuser", verbose_name="Trabajador")),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="hr_calendar.payperiod", verbose_name="Periodo")),
            ],
            options={
                "verbose_name": "Línea de liquidación",
                "verbose_name_plural": "Líneas de liquidación",
                "ordering": ["company_user_id", "key"],
            },
        ),
    ]
