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
    Used by MachineAssetCreateView and MachineAssetUpdateView.
    All fields are optional except code, which is the primary lookup key.

    ---

    Formulario para crear y actualizar un registro MachineAsset desde el panel.
    Usado por MachineAssetCreateView y MachineAssetUpdateView.
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
            "family": forms.TextInput(attrs={
                "class": "form-control text-uppercase",
                "placeholder": "Ej: MOVILES",
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
        }
