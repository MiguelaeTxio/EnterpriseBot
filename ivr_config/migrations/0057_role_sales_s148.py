# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/migrations/0057_role_sales_s148.py
# S148: rol nuevo SALES (Comercial), de momento sin permisos propios.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0056_workdayscheduleday_holiday_s144"),
    ]

    operations = [
        migrations.AlterField(
            model_name="companyuser",
            name="role",
            field=models.CharField(
                choices=[
                    ("ADMIN", "Administrador"),
                    ("ADMIN_SUPERVISOR", "Supervisor de Administración"),
                    ("OPERATOR", "Operador"),
                    ("WORKSHOP", "Operario de taller"),
                    ("WORKSHOPBOSS", "Jefe de taller"),
                    ("SUPERVISOR", "Supervisor"),
                    ("DRIVER", "Chófer"),
                    ("CRANE_OPERATOR", "Gruista"),
                    ("ASSISTANCE", "Operario de Asistencia"),
                    ("ASSIST_SUPERVISOR", "Supervisor de Asistencia"),
                    ("DOCS_SUPERVISOR", "Supervisor de Documentación"),
                    ("OFFICE", "Administrativo"),
                    ("NIGHTGUARD", "Guarda nocturno"),
                    ("SALES", "Comercial"),
                ],
                default="OPERATOR",
                help_text=(
                    "ADMIN: acceso completo a la configuración. OPERATOR: "
                    "gestión de presencia. WORKSHOP: partes de taller. "
                    "WORKSHOPBOSS: jefe de taller — tickets de avería, "
                    "sala BREAKDOWNS y sección propia, más acceso "
                    "equivalente a SUPERVISOR en Taller, Administración y "
                    "jornada. SUPERVISOR: revisión y exportación de partes "
                    "PDF. DRIVER: reservado. ASSISTANCE: operario de "
                    "Asistencia — solo modulo de presupuestos. "
                    "ASSIST_SUPERVISOR: supervisor de Asistencia — página "
                    "Servicios. DOCS_SUPERVISOR: puede subir documentación "
                    "de centros de gasto (el listado es de solo lectura "
                    "para cualquier usuario). OFFICE: administrativo. "
                    "NIGHTGUARD: guarda nocturno. ADMIN_SUPERVISOR: como "
                    "ADMIN salvo Asistencia (de Asistencia, solo Bases y "
                    "Calendarios laborales). SALES: comercial (de momento "
                    "sin permisos propios)."
                ),
                max_length=20,
                verbose_name="Rol",
            ),
        ),
    ]
