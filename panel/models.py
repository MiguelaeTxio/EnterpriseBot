# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/models.py
"""
Model definitions for the panel application.
Currently defines AnalyticsProfile, which persists named chart configurations
per CompanyUser so that the client-side analytics builder can save and restore
user-defined views.
---
Definiciones de modelos para la aplicación panel.
Actualmente define AnalyticsProfile, que persiste configuraciones de gráfico
nombradas por CompanyUser para que el constructor de analítica client-side
pueda guardar y restaurar vistas definidas por el usuario.
"""

from django.db import models

from ivr_config.models import CompanyUser


class AnalyticsProfile(models.Model):
    """
    Stores a named analytics chart configuration for a specific CompanyUser.

    The ``config`` JSONField holds the complete state of the client-side chart
    builder controls so that it can be restored without any server-side
    computation:

        {
            "metric":      "interventions" | "hours" | "weekday" | "top10",
            "chart_type":  "bar_v" | "bar_h" | "line" | "area",
            "palette":     "corporate" | "blues" | "viridis" | "reds"
                           | "greens" | "plasma",
            "date_from":   "YYYY-MM-DD" | null,
            "date_to":     "YYYY-MM-DD" | null,
            "assets":      ["A-54", "B-42"] | null,   // null = todos
            "work_orders": [18, 22]        | null    // null = todos
        }

    Uniqueness is enforced at the (company_user, nombre) level so that each
    user can maintain their own named profile space without collisions.
    ---
    Almacena una configuración de gráfico de analítica nombrada para un
    CompanyUser concreto.

    El JSONField ``config`` guarda el estado completo de los controles del
    constructor de gráficos client-side para poder restaurarlo sin cálculo
    en el servidor:

        {
            "metric":      "interventions" | "hours" | "weekday" | "top10",
            "chart_type":  "bar_v" | "bar_h" | "line" | "area",
            "palette":     "corporate" | "blues" | "viridis" | "reds"
                           | "greens" | "plasma",
            "date_from":   "YYYY-MM-DD" | null,
            "date_to":     "YYYY-MM-DD" | null,
            "assets":      ["A-54", "B-42"] | null,   // null = todos
            "work_orders": [18, 22]        | null    // null = todos
        }

    La unicidad se aplica a nivel (company_user, nombre) para que cada
    usuario disponga de su propio espacio de perfiles sin colisiones.
    """

    # Owner of this profile / Propietario de este perfil.
    company_user = models.ForeignKey(
        CompanyUser,
        on_delete=models.CASCADE,
        related_name="analytics_profiles",
        verbose_name="usuario de empresa",
    )

    # Human-readable name chosen by the user / Nombre legible elegido por el usuario.
    nombre = models.CharField(
        max_length=100,
        verbose_name="nombre",
    )

    # Complete chart-builder state / Estado completo del constructor de gráficos.
    config = models.JSONField(
        verbose_name="configuración",
    )

    # Audit timestamps / Marcas de tiempo de auditoría.
    creado_en = models.DateTimeField(
        auto_now_add=True,
        verbose_name="creado en",
    )
    actualizado_en = models.DateTimeField(
        auto_now=True,
        verbose_name="actualizado en",
    )

    class Meta:
        # Each user can have at most one profile per name.
        # Cada usuario puede tener como máximo un perfil por nombre.
        unique_together = [("company_user", "nombre")]
        ordering = ["nombre"]
        verbose_name = "Perfil de analítica"
        verbose_name_plural = "Perfiles de analítica"

    def __str__(self):
        """
        Returns a human-readable representation combining username and profile name.
        ---
        Devuelve una representación legible combinando el nombre de usuario y el perfil.
        """
        return f"{self.company_user.user.username} — {self.nombre}"


class PanelNavigationState(models.Model):
    """
    H31 (S75). Persiste, por CompanyUser y por pantalla (`screen_key`),
    qué pestaña estaba activa y qué filtros/orden tenía cada pestaña --
    para que recargar la página o volver atrás en el navegador NUNCA
    cambie de pestaña ni pierda los filtros, tal como pidió Miguel
    Ángel explícitamente (S75): "el que cambie la pestaña soy yo. No
    me la cambia el sistema [...] los filtros deben ser persistentes
    siempre". Decisión explícita de Miguel Ángel: tabla real en BD
    (no localStorage) -- tiene que sobrevivir incluso a cerrar el
    navegador o cambiar de dispositivo, no solo a un F5.

    `state` es un único JSONField de forma libre por pantalla (mismo
    patrón que `AnalyticsProfile.config` arriba) -- para
    `documentation_hub` tiene la forma:

        {
            "active_tab": "maquinaria" | "personal" | "epis",
            "filters": {
                "maquinaria": {"q": "...", "sort": "...", "dir": "asc"},
                "personal":   {"q": "...", "sort": "...", "dir": "asc"},
                "epis":       {"q": "...", "sort": "...", "dir": "asc"}
            }
        }

    Una fila por (company_user, screen_key) -- se sobrescribe entera
    en cada guardado (nunca hace falta un historial, solo el último
    estado real).

    ---

    H31 (S75). Persists, per CompanyUser and per screen (`screen_key`),
    which tab was active and each tab's filters/sort -- so reloading
    the page or navigating back in the browser NEVER changes tabs nor
    loses filters, per Miguel Ángel's explicit request (S75). Explicit
    decision: a real DB table (not localStorage) -- must survive even
    closing the browser or switching devices, not just an F5.
    """

    company_user = models.ForeignKey(
        CompanyUser,
        on_delete=models.CASCADE,
        related_name="navigation_states",
        verbose_name="usuario de empresa",
    )
    screen_key = models.CharField(
        max_length=100,
        verbose_name="pantalla",
        help_text="Identificador corto de la pantalla (p. ej. 'documentation_hub').",
    )
    state = models.JSONField(
        verbose_name="estado",
        help_text="Pestaña activa + filtros por pestaña, forma libre según la pantalla.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="última actualización",
    )

    class Meta:
        unique_together = [("company_user", "screen_key")]
        verbose_name = "Estado de navegación"
        verbose_name_plural = "Estados de navegación"

    def __str__(self):
        return f"{self.company_user.user.username} — {self.screen_key}"


class ScreenExportTemplate(models.Model):
    """
    S148. Named column set for the export (Excel, PDF or print) of a
    panel screen without its own template model (Centros de gasto,
    Taller, Fichajes...): same idea as the Personal and Refuels
    templates. `screen` is the key of the screen in
    panel/screen_exports.py; `columns` are keys of its catalogue.
    ---
    S148. Juego de columnas con nombre para exportar (Excel, PDF o
    imprimir) una pantalla del panel que no tenía modelo de plantillas
    propio, mismo planteamiento que Personal y Repostajes: plantillas
    propias (una por defecto por pantalla) y globales de empresa que
    solo crea o edita un administrador. Además de estas, cada pantalla
    ofrece la fija "Vista del panel" (panel/export_templates.py).
    """

    company = models.ForeignKey(
        "ivr_config.Company",
        on_delete=models.CASCADE,
        related_name="screen_export_templates",
        verbose_name="Empresa",
    )
    company_user = models.ForeignKey(
        CompanyUser,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="screen_export_templates",
        verbose_name="Usuario",
        help_text="Dueño de la plantilla propia; vacío en las globales.",
    )
    screen = models.CharField(max_length=60, verbose_name="Pantalla")
    is_global = models.BooleanField(
        default=False,
        verbose_name="Plantilla global",
        help_text="La ven todos; solo un administrador la crea o edita.",
    )
    name = models.CharField(max_length=100, verbose_name="Nombre")
    is_default = models.BooleanField(
        default=False,
        verbose_name="Por defecto",
        help_text="La que sale elegida (una por usuario y pantalla).",
    )
    columns = models.JSONField(
        default=list,
        verbose_name="Columnas",
        help_text="Claves de columna, en el orden de la exportación.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Plantilla de exportación de pantalla"
        verbose_name_plural = "Plantillas de exportación de pantalla"
        ordering = ["screen", "-is_global", "-is_default", "name"]

    def __str__(self):
        return "%s — %s" % (self.screen, self.name)

    def save(self, *args, **kwargs):
        if self.is_default and not self.is_global and self.company_user_id:
            ScreenExportTemplate.objects.filter(
                company_user_id=self.company_user_id, screen=self.screen,
                is_default=True,
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class PanelUserGroup(models.Model):
    """
    Named group of panel users, for permissions (S163, new interface).

    ---

    Grupo de usuarios del panel con nombre, para dar permisos de golpe
    en la nueva interfaz (S163, sesión invasora de UX). Miguel Ángel:
    "permisos [...] con los usuarios y grupos de usuarios y los permisos
    para las diferentes vistas". Se gestiona desde la pestaña Permisos
    de la nueva interfaz (panel/views_new_ui.py).
    """

    company = models.ForeignKey(
        "ivr_config.Company",
        on_delete=models.CASCADE,
        related_name="panel_user_groups",
        verbose_name="Empresa",
    )
    name = models.CharField(max_length=120, verbose_name="Nombre")
    members = models.ManyToManyField(
        CompanyUser,
        blank=True,
        related_name="panel_user_groups",
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
        verbose_name = "Grupo de usuarios del panel"
        verbose_name_plural = "Grupos de usuarios del panel"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=("company", "name"),
                name="unique_panel_user_group_name_per_company",
            ),
        ]

    def __str__(self):
        return self.name


class PanelViewGrant(models.Model):
    """
    Permission level on one view of the new interface for one subject.

    ---

    Nivel de permiso sobre una vista de la nueva interfaz (clave de
    panel/new_ui_catalog.py) para UN sujeto: un rol, un grupo de
    usuarios o un usuario (uno solo de los tres relleno). Cómo se
    combinan: panel/new_ui_permissions.effective_level.
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
        related_name="panel_view_grants",
        verbose_name="Empresa",
    )
    view_key = models.CharField(max_length=60, verbose_name="Vista")
    role = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Rol",
    )
    user_group = models.ForeignKey(
        PanelUserGroup,
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
        related_name="panel_view_grants",
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
        ordering = ["view_key"]

    def __str__(self):
        return "%s · %s" % (self.view_key, self.get_level_display())
