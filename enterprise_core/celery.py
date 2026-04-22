# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/enterprise_core/celery.py

"""
Celery application factory for the EnterpriseBot project.
Loads environment variables from the project root .env file, configures
the Django settings module and creates the main Celery application instance.

---

Factory de aplicación Celery para el proyecto EnterpriseBot.
Carga las variables de entorno del archivo .env en la raíz del proyecto,
configura el módulo de settings de Django y crea la instancia principal
de la aplicación Celery.
"""

import os

from celery import Celery
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment loading / Carga de variables de entorno
# ---------------------------------------------------------------------------
# Build the absolute path to the .env file located in the project root.
# os.path.dirname(__file__) -> /home/MiguelAeTxio/PROJECTS/EnterpriseBot/enterprise_core
# os.path.dirname(...) -> /home/MiguelAeTxio/PROJECTS/EnterpriseBot
# os.path.join(..., '.env') -> /home/MiguelAeTxio/PROJECTS/EnterpriseBot/.env
# Construir la ruta absoluta al archivo .env en la raíz del proyecto.
dotenv_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
)

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

# ---------------------------------------------------------------------------
# Django settings / Configuración de Django
# ---------------------------------------------------------------------------
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "enterprise_core.settings")

# ---------------------------------------------------------------------------
# Celery application instance / Instancia de aplicación Celery
# ---------------------------------------------------------------------------
app = Celery("enterprise_core")

# Load configuration from Django settings using the CELERY_ namespace.
# All settings.py variables prefixed with CELERY_ are automatically picked up.
# Cargar configuración desde settings de Django usando el namespace CELERY_.
# Todas las variables de settings.py con prefijo CELERY_ se recogen automáticamente.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py modules from all apps in INSTALLED_APPS.
# Autodescubrir módulos tasks.py de todas las apps en INSTALLED_APPS.
app.autodiscover_tasks()
