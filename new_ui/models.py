# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/models.py
"""
Tables of the new interface (S163, invasora UX), apart from `panel`.

---

Tablas propias de la nueva interfaz (S163, sesión invasora de UX). Van
en su propia app para que la nueva interfaz se pueda borrar entera sin
tocar la antigua, y al revés. Miguel Ángel: "si no me gusta y tenemos
que borrar, no quiero borrar lo otro. Y si borramos la antigua porque
la nueva funciona, no pueden estar mezcladas."

- UiUserGroup / UiViewGrant: grupos de usuarios y permisos por vista
  (pestaña Permisos). Sustituyen a PanelUserGroup / PanelViewGrant,
  que estaban en `panel`.
- UiState: lo que cada usuario deja puesto en la nueva interfaz
  (sección, filtros, columnas, pestañas, tamaños, selección...), en vez
  del PanelNavigationState de la antigua.
"""

from django.db import models

from ivr_config.models import CompanyUser


class UiUserGroup(models.Model):
    """
    Named group of panel users, for permissions.

    ---

    Grupo de usuarios con nombre, para dar permisos de golpe desde la
    pestaña Permisos.
    """

    company = models.ForeignKey(
        "ivr_config.Company",
        on_delete=models.CASCADE,
        related_name="new_ui_user_groups",
        verbose_name="Empresa",
    )
    name = models.CharField(max_length=120, verbose_name="Nombre")
    members = models.ManyToManyField(
        CompanyUser,
        blank=True,
        related_name="new_ui_user_groups",
        verbose_name="Usuarios",
    )
    created_by = models.ForeignKey(
        CompanyUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Creado por",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Grupo de usuarios (nueva interfaz)"
        verbose_name_plural = "Grupos de usuarios (nueva interfaz)"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=("company", "name"),
                name="unique_new_ui_user_group_name_per_company",
            ),
        ]

    def __str__(self):
        return self.name


class UiViewGrant(models.Model):
    """
    Permission level on one view of the new interface for one subject.

    ---

    Nivel de permiso sobre una vista (clave de new_ui/catalog.py) para
    UN sujeto: un rol, un grupo de usuarios o un usuario (uno solo de
    los tres). Cómo se combinan: new_ui/permissions.effective_levels.
    """

    LEVEL_NONE = "NONE"
    LEVEL_VIEW = "VIEW"
    LEVEL_EDIT = "EDIT"
    LEVEL_CHOICES = [
        (LEVEL_NONE, "Sin acceso"),
        (LEVEL_VIEW, "Ver"),
        (LEVEL_EDIT, "Ver y modificar"),
    ]

    company = models.ForeignKey(
        "ivr_config.Company",
        on_delete=models.CASCADE,
        related_name="new_ui_view_grants",
        verbose_name="Empresa",
    )
    view_key = models.CharField(max_length=60, verbose_name="Vista")
    role = models.CharField(
        max_length=20, blank=True, default="", verbose_name="Rol",
    )
    user_group = models.ForeignKey(
        UiUserGroup,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="grants",
        verbose_name="Grupo de usuarios",
    )
    company_user = models.ForeignKey(
        CompanyUser,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="new_ui_view_grants",
        verbose_name="Usuario",
    )
    level = models.CharField(
        max_length=10,
        choices=LEVEL_CHOICES,
        default=LEVEL_NONE,
        verbose_name="Nivel",
    )
    updated_by = models.ForeignKey(
        CompanyUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Modificado por",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Permiso de vista (nueva interfaz)"
        verbose_name_plural = "Permisos de vista (nueva interfaz)"
        indexes = [models.Index(fields=["company", "view_key"])]

    def __str__(self):
        return "%s: %s" % (self.view_key, self.level)


class UiState(models.Model):
    """
    What one user left set on one screen of the new interface.

    ---

    Lo que un usuario deja puesto en una pantalla de la nueva interfaz
    (un JSON por pantalla: "nui", "nui_filters_<sección>"...).
    """

    company_user = models.ForeignKey(
        CompanyUser,
        on_delete=models.CASCADE,
        related_name="new_ui_states",
        verbose_name="Usuario",
    )
    screen_key = models.CharField(max_length=80, verbose_name="Pantalla")
    state = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Estado de pantalla (nueva interfaz)"
        verbose_name_plural = "Estados de pantalla (nueva interfaz)"
        constraints = [
            models.UniqueConstraint(
                fields=("company_user", "screen_key"),
                name="unique_new_ui_state_per_user_screen",
            ),
        ]

    def __str__(self):
        return "%s · %s" % (self.company_user_id, self.screen_key)
