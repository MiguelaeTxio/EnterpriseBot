# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/forms.py
"""
Form definitions for the panel application.
Covers all entities manageable from the CompanyUser panel.
---
Definiciones de formularios para la aplicación panel.
Cubre todas las entidades gestionables desde el panel de CompanyUser.
"""

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from ivr_config.models import (
    CompanyUser,
    Contact,
    Section,
    CallFlow,
    PhoneNumber,
    PresenceStatus,
    CorporateVoiceProfile,
)


class PanelAuthenticationForm(AuthenticationForm):
    """
    Custom authentication form for the panel login view.
    Applies panel-specific CSS classes to username and password fields.
    ---
    Formulario de autenticación personalizado para la vista de login del panel.
    Aplica clases CSS específicas del panel a los campos de usuario y contraseña.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Usuario",
            "autofocus": True,
        })
        self.fields["password"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Contraseña",
        })


class PresenceStatusForm(forms.ModelForm):
    """
    Form for creating and updating a CompanyUser's presence status.
    ---
    Formulario para crear y actualizar el estado de presencia de un CompanyUser.
    """

    class Meta:
        model = PresenceStatus
        fields = ["status", "ends_at"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "ends_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }
        labels = {
            "status": "Estado",
            "ends_at": "Disponible a partir de",
        }


class ContactForm(forms.ModelForm):
    """
    Form for creating and updating a Contact record.
    ---
    Formulario para crear y actualizar un registro de Contact.
    """

    class Meta:
        model = Contact
        fields = ["name", "phone_number", "is_internal", "company_user"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "phone_number": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "+34XXXXXXXXX",
            }),
            "is_internal": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "company_user": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "name": "Nombre",
            "phone_number": "Teléfono (E.164)",
            "is_internal": "Usuario interno",
            "company_user": "Usuario vinculado",
        }


class SectionForm(forms.ModelForm):
    """
    Form for creating and updating a Section record.
    ---
    Formulario para crear y actualizar un registro de Section.
    """

    class Meta:
        model = Section
        fields = ["name", "description", "contacts", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "contacts": forms.SelectMultiple(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "name": "Nombre",
            "description": "Descripción",
            "contacts": "Contactos",
            "is_active": "Activa",
        }


class CallFlowForm(forms.ModelForm):
    """
    Form for creating and updating a CallFlow record.
    ---
    Formulario para crear y actualizar un registro de CallFlow.
    """

    class Meta:
        model = CallFlow
        fields = ["name", "system_instruction", "initial_greeting", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "system_instruction": forms.Textarea(attrs={"class": "form-control", "rows": 8}),
            "initial_greeting": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "name": "Nombre del flujo",
            "system_instruction": "Instrucción de sistema",
            "initial_greeting": "Saludo inicial",
            "is_active": "Activo",
        }


class CorporateVoiceProfileForm(forms.ModelForm):
    """
    Form for creating and updating a CorporateVoiceProfile record.
    ---
    Formulario para crear y actualizar un registro de CorporateVoiceProfile.
    """

    class Meta:
        model = CorporateVoiceProfile
        fields = ["tone_guidelines", "sample_responses", "forbidden_phrases", "is_active"]
        widgets = {
            "tone_guidelines": forms.Textarea(attrs={"class": "form-control", "rows": 6}),
            "sample_responses": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": '["Ejemplo de respuesta 1", "Ejemplo de respuesta 2"]',
            }),
            "forbidden_phrases": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": '["Frase prohibida 1", "Frase prohibida 2"]',
            }),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "tone_guidelines": "Directrices de tono",
            "sample_responses": "Respuestas de ejemplo (JSON)",
            "forbidden_phrases": "Frases prohibidas (JSON)",
            "is_active": "Activo",
        }
