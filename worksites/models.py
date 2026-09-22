# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/worksites/models.py
"""
H31 (S115). Modelo de Obra -- ver worksites/apps.py y la deuda
técnica 4.23 del documento maestro para el contexto completo de por
qué se crea ya, con qué alcance, y qué queda deliberadamente para
más adelante (Cliente/Proveedor reales, facturación, DECA).

Decisión explícita de Miguel Ángel (S115): crear la tabla ya --
"la necesitamos ya, pero tenemos que tener previsto que se va a
enlazar con [...] y que va a crecer con el número de registros o de
campos" -- sin esperar al diseño completo de Cliente/Proveedor.
"""
from django.db import models


class Worksite(models.Model):
    """
    Represents a real construction/service site ("obra") to which
    circulars, delivery notes (albaranes) and, in the future,
    invoicing can be attached. Deliberately minimal today (name is
    the only field actually required) but designed to grow: `client_name`
    and `managing_company` are the seams where future Cliente/Proveedor
    models will attach without needing to redesign this table.

    ---

    Representa una obra real a la que se pueden ligar circulares,
    albaranes y, en el futuro, facturación. Deliberadamente mínimo
    hoy (solo `name` es realmente obligatorio) pero pensado para
    crecer: `client_name` y `managing_company` son las costuras por
    donde engancharán los futuros modelos Cliente/Proveedor sin tener
    que rediseñar esta tabla.
    """

    name = models.CharField(
        max_length=200,
        verbose_name="Nombre de la obra",
        help_text="Nombre identificativo de la obra, tal como se usará en circulares y documentación.",
    )
    code = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Código interno",
        help_text=(
            "Código corto opcional de la obra (para referencia cruzada futura con "
            "albaranes, facturación, centros de gasto). Sin formato fijo todavía."
        ),
    )
    client_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Cliente (texto libre)",
        help_text=(
            "Cliente para el que se ejecuta la obra / a quien se factura. Texto libre "
            "por ahora -- mismo patrón que PersonIdentity.employer_company antes de "
            "tener un modelo Cliente real: se sustituirá por FK cuando ese modelo exista."
        ),
    )
    managing_company = models.ForeignKey(
        "ivr_config.Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="worksites",
        verbose_name="Empresa del grupo que gestiona la obra",
        help_text="Empresa del grupo (Grúas Álvarez, Transgrual, etc.) que gestiona esta obra.",
    )
    address = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Ubicación",
        help_text="Lugar donde se ejecuta la obra (dirección o referencia libre).",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa",
        help_text="False cuando la obra ha finalizado -- se conserva el registro, no se borra.",
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Notas",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Fecha de modificación")

    class Meta:
        verbose_name = "Obra"
        verbose_name_plural = "Obras"
        ordering = ["name"]

    def __str__(self):
        return self.name
