# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/forms.py
"""
Form definitions for the panel application.
Covers all entities manageable from the CompanyUser panel.
Updated 2026-04-13: ContactForm extended with email/gender, SectionForm with
is_24h, CallFlowForm with notification_contact. New SectionScheduleForm and
BlockedCallerForm added.
---
Definiciones de formularios para la aplicación panel.
Cubre todas las entidades gestionables desde el panel de CompanyUser.
Actualización 2026-04-13: ContactForm extendido con email/gender, SectionForm
con is_24h, CallFlowForm con notification_contact. Nuevos SectionScheduleForm
y BlockedCallerForm añadidos.
"""

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from ivr_config.models import (
    CompanyUser,
    Contact,
    Section,
    SectionSchedule,
    CallFlow,
    PhoneNumber,
    PresenceStatus,
    CorporateVoiceProfile,
    BlockedCaller,
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
    Includes email and gender fields added in session 2026-04-13.
    ---
    Formulario para crear y actualizar un registro de Contact.
    Incluye los campos email y gender añadidos en la sesión 2026-04-13.
    """

    class Meta:
        model = Contact
        fields = ["name", "phone_number", "email", "gender", "is_internal", "company_user"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "phone_number": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "+34XXXXXXXXX",
            }),
            "email": forms.EmailInput(attrs={
                "class": "form-control",
                "placeholder": "correo@ejemplo.com",
            }),
            "gender": forms.Select(attrs={"class": "form-select"}),
            "is_internal": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "company_user": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "name": "Nombre",
            "phone_number": "Teléfono (E.164)",
            "email": "Correo electrónico",
            "gender": "Tratamiento (Sr./Sra.)",
            "is_internal": "Usuario interno",
            "company_user": "Usuario vinculado",
        }


class SectionForm(forms.ModelForm):
    """
    Form for creating and updating a Section record.
    Includes is_24h field added in session 2026-04-13.
    ---
    Formulario para crear y actualizar un registro de Section.
    Incluye el campo is_24h añadido en la sesión 2026-04-13.
    """

    class Meta:
        model = Section
        fields = ["name", "description", "contacts", "is_24h", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "contacts": forms.SelectMultiple(attrs={"class": "form-select", "size": "6"}),
            "is_24h": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "name": "Nombre",
            "description": "Descripción",
            "contacts": "Contactos",
            "is_24h": "Disponible 24 horas",
            "is_active": "Activa",
        }


class SectionScheduleForm(forms.ModelForm):
    """
    Form for creating and updating a single SectionSchedule time slot.
    Used as an inline form within the Section create/edit views.
    ---
    Formulario para crear y actualizar una franja horaria SectionSchedule.
    Se usa como formulario inline dentro de las vistas de creación/edición de Section.
    """

    class Meta:
        model = SectionSchedule
        fields = ["weekday", "time_open", "time_close"]
        widgets = {
            "weekday": forms.Select(attrs={"class": "form-select"}),
            "time_open": forms.TimeInput(
                attrs={"class": "form-control", "type": "time"},
                format="%H:%M",
            ),
            "time_close": forms.TimeInput(
                attrs={"class": "form-control", "type": "time"},
                format="%H:%M",
            ),
        }
        labels = {
            "weekday": "Día de la semana",
            "time_open": "Hora de apertura",
            "time_close": "Hora de cierre",
        }

    def clean(self):
        """
        Validates that time_open is strictly before time_close.
        ---
        Valida que time_open sea estrictamente anterior a time_close.
        """
        cleaned_data = super().clean()
        time_open = cleaned_data.get("time_open")
        time_close = cleaned_data.get("time_close")
        if time_open and time_close and time_open >= time_close:
            raise forms.ValidationError(
                "La hora de apertura debe ser anterior a la hora de cierre."
            )
        return cleaned_data


class CallFlowForm(forms.ModelForm):
    """
    Form for creating and updating a CallFlow record.
    Includes notification_contact field added in session 2026-04-13.
    The notification_contact queryset is restricted to the company's contacts
    by the view layer (CallFlowCreateView / CallFlowUpdateView).
    ---
    Formulario para crear y actualizar un registro de CallFlow.
    Incluye el campo notification_contact añadido en la sesión 2026-04-13.
    El queryset de notification_contact se restringe a los contactos de la empresa
    desde la capa de vistas (CallFlowCreateView / CallFlowUpdateView).
    """

    class Meta:
        model = CallFlow
        fields = [
            "name",
            "system_instruction",
            "initial_greeting",
            "notification_contact",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "system_instruction": forms.Textarea(attrs={"class": "form-control", "rows": 8}),
            "initial_greeting": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "notification_contact": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "name": "Nombre del flujo",
            "system_instruction": "Instrucción de sistema",
            "initial_greeting": "Saludo inicial",
            "notification_contact": "Contacto de notificación (actividad no recogida)",
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


class BlockedCallerForm(forms.ModelForm):
    """
    Form for manually blocking a phone number from reaching the company IVR.
    The 'blocked_until' field defaults to 24 hours if left blank (handled by model save).
    ---
    Formulario para bloquear manualmente un número de teléfono en el IVR de la empresa.
    El campo 'blocked_until' tiene por defecto 24 horas si se deja vacío
    (gestionado por el método save del modelo).
    """

    class Meta:
        model = BlockedCaller
        fields = ["phone_number", "reason", "blocked_until"]
        widgets = {
            "phone_number": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "+34XXXXXXXXX",
            }),
            "reason": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Motivo del bloqueo (opcional).",
            }),
            "blocked_until": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }
        labels = {
            "phone_number": "Número de teléfono (E.164)",
            "reason": "Motivo",
            "blocked_until": "Bloqueado hasta (vacío = 24 horas)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # blocked_until is optional in the form — model.save() applies the 24h default.
        # blocked_until es opcional en el formulario — model.save() aplica el default de 24h.
        self.fields["blocked_until"].required = False
