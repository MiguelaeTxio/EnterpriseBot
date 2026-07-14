# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/apps.py
"""
App configuration for hr_calendar (Hito 24).

Dedicated app for vacation/absence calendar management, kept separate
from existing apps to avoid bloating an unrelated functional domain
with RRHH/planning concerns -- same architectural directive applied in
H22 (see that annex, section 3.1) and reused again in H23
(machine_documents).

---

Configuración de la app hr_calendar (Hito 24).

App dedicada para la gestión del calendario de vacaciones/ausencias,
mantenida separada de las apps existentes para no engordar un dominio
funcional ajeno con asuntos de RRHH/planificación -- misma directriz
arquitectónica aplicada en H22 (ver ese anexo, sección 3.1) y reutilizada
de nuevo en H23 (machine_documents).
"""
from django.apps import AppConfig


class HrCalendarConfig(AppConfig):
    """
    AppConfig for the hr_calendar application.
    ---
    AppConfig para la aplicación hr_calendar.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "hr_calendar"
    verbose_name = "Vacaciones y Calendario"
