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
