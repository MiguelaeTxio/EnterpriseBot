# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/forms.py
"""
Forms for the fleet application.
Provides MachineAssetForm for creating and updating MachineAsset records
from the panel CRUD views.

---

Formularios de la aplicación fleet.
Proporciona MachineAssetForm para crear y actualizar registros MachineAsset
desde las vistas CRUD del panel.
"""

from django import forms

from fleet.models import MachineAsset


class MachineAssetForm(forms.ModelForm):
    """
    Form for creating and updating a MachineAsset record from the panel.
    Used by MachineAssetCreateView and, since S117, by the machine
    detail page (panel MachineDetailView), where machine data is edited.
    All fields are optional except code, which is the primary lookup key.

    ---

    Formulario para crear y actualizar un registro MachineAsset desde el panel.
    Usado por MachineAssetCreateView y, desde S117, por la ficha de la
    máquina (MachineDetailView del panel), donde se editan sus datos.
    Todos los campos son opcionales excepto code, que es la clave de búsqueda
    principal.
    """

    class Meta:
        model = MachineAsset
        fields = [
            "code",
            "plate",
            "chassis_number",
            "brand_model",
            "company_code",
            "company_name",
            "family",
            "type_code",
            "type_name",
            "purchase_date",
            "mileage",
            "hours",
            "is_active",
            # H30 (S131): plan de revisiones por horas y km.
            "service_hours_interval",
            "service_crane_hours_interval",
            "service_every_km",
            # S148: observaciones libres (campo Memo).
            "notes",
        ]
        widgets = {
            "code": forms.TextInput(attrs={
                "class": "form-control text-uppercase",
                "placeholder": "Ej: A54, Z45, BEN",
            }),
            "plate": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: E2052BCW",
            }),
            "chassis_number": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: VHX2FF1P22",
            }),
            "brand_model": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: LIEBHERR LTM 1055",
            }),
            "company_code": forms.TextInput(attrs={
                "class": "form-control text-uppercase",
                "placeholder": "Ej: GRA",
            }),
            "company_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Gruas Adolfo Álvarez, S.L.",
            }),
            "type_code": forms.TextInput(attrs={
                "class": "form-control text-uppercase",
                "placeholder": "Ej: MV035",
            }),
            "type_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: GRUA MOVIL DE 35 TM",
            }),
            "purchase_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                },
                format="%Y-%m-%d",
            ),
            "mileage": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0",
            }),
            "hours": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0",
            }),
            "is_active": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
            "service_hours_interval": forms.Select(attrs={
                "class": "form-select",
            }),
            "service_crane_hours_interval": forms.Select(attrs={
                "class": "form-select",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Avisos y notas (p. ej. cambios de "
                               "matrícula)",
            }),
            "service_every_km": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "1",
                "placeholder": "Sin revisión por km",
            }),
        }
        labels = {
            "code":           "Código",
            "plate":          "Matrícula",
            "chassis_number": "Nº Bastidor",
            "brand_model":    "Marca / Modelo",
            "company_code":   "Cód. Empresa",
            "company_name":   "Nombre Empresa",
            "family":         "Familia",
            "type_code":      "Cód. Tipo",
            "type_name":      "Nombre Tipo",
            "purchase_date":  "Fecha de Compra",
            "mileage":        "Kilómetros",
            "hours":          "Horas",
            "is_active":      "Activo",
            "service_hours_interval": "Revisión por horas",
            "service_crane_hours_interval": "Revisión de la grúa por horas",
            "service_every_km":       "Revisión cada N km",
            "notes":          "Observaciones",
        }

    # S117 -- petición de Miguel Ángel: "Familia" deja de ser texto libre
    # y pasa a ser el mismo desplegable de familias que ya tiene el
    # filtro del listado, con una opción "Nueva familia…" que despliega
    # un campo de texto para dar de alta una familia nueva sin salir del
    # formulario. Evita variantes escritas a mano de una misma familia.
    NEW_FAMILY_VALUE = "__new__"

    family_new = forms.CharField(
        label="Nueva familia",
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={
            "class": "form-control text-uppercase",
            "placeholder": "Ej: GRUAS TORRE",
        }),
    )

    def __init__(self, *args, company=None, **kwargs):
        """
        Builds the "family" select from the families already used by
        the company's cost centres (same source as the list filter),
        keeping the current value even if it is not in the list.
        ---
        Construye el desplegable de "family" con las familias ya usadas
        por los centros de gasto de la empresa (misma fuente que el
        filtro del listado), conservando el valor actual aunque no esté
        en la lista.
        """
        super().__init__(*args, **kwargs)
        # S117: solo familias con al menos una máquina activa (mismo punto
        # único que el filtro del listado); la familia actual de ESTA
        # máquina se conserva aunque esté "desactivada".
        from fleet.family_service import active_families

        families = active_families(company) if company is not None else []
        current = (self.instance.family or "") if self.instance else ""
        if current and current not in families:
            families.append(current)
            families.sort()
        choices = [("", "(Sin familia)")]
        choices += [(family, family) for family in families]
        choices.append((self.NEW_FAMILY_VALUE, "Nueva familia…"))
        self.fields["family"] = forms.ChoiceField(
            label="Familia",
            required=False,
            choices=choices,
            widget=forms.Select(attrs={
                "class": "form-select",
                "data-new-family-value": self.NEW_FAMILY_VALUE,
            }),
        )

    def clean(self):
        """
        Resolves "Nueva familia…" into the typed family name
        (upper-cased, like the rest of the catalogue).
        ---
        Resuelve "Nueva familia…" en el nombre de familia escrito (en
        mayúsculas, igual que el resto del catálogo).
        """
        cleaned = super().clean()
        if cleaned.get("family") == self.NEW_FAMILY_VALUE:
            new_family = (cleaned.get("family_new") or "").strip().upper()
            if not new_family:
                self.add_error(
                    "family_new",
                    "Escribe el nombre de la nueva familia.",
                )
            cleaned["family"] = new_family
        # H30 (S131): 0 km equivale a "sin revisión por kilómetros".
        if not cleaned.get("service_every_km"):
            cleaned["service_every_km"] = None
        return cleaned
