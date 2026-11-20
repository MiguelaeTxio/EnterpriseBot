# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/crane_albaranes/apps.py
"""
App configuration for crane work delivery notes (H11, S162).

---

Configuración de la app de albaranes de trabajo de las grúas (H11,
S162): el albarán digital que prepara la oficina (o el propio gruista),
rellena el gruista con sus fichajes, firma el cliente y se le envía.
"""
from django.apps import AppConfig


class CraneAlbaranesConfig(AppConfig):
    """
    AppConfig for crane_albaranes.
    ---
    AppConfig de crane_albaranes.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "crane_albaranes"
    verbose_name = "Albaranes de grúas"
