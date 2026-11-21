# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/mixins.py
"""
Access control of the new interface.

---

Control de acceso de la nueva interfaz (copia adaptada de
panel/mixins.py, S163): mientras no se abra a todos, solo superusuarios
con un CompanyUser activo. Sin sesión, al inicio de sesión del panel.
"""

from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

LOGIN_URL = "/panel/login/"


class SuperuserRequiredMixin:
    """
    Only active panel users that are Django superusers.

    ---

    Solo usuarios del panel activos que además son superusuarios.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(LOGIN_URL)
        company_user = getattr(request.user, "company_user", None)
        if company_user is None or not company_user.is_active:
            messages.error(request, "Tu cuenta no tiene acceso al panel. "
                                    "Contacta con tu administrador.")
            return redirect(LOGIN_URL)
        if not request.user.is_superuser:
            return HttpResponseForbidden("Solo para administradores.")
        return super().dispatch(request, *args, **kwargs)
