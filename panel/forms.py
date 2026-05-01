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
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

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
    DataCaptureSet,
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
    Updated 2026-04-16 (Step 37.C — Estrategia B): call_flow field added
    to allow assigning a section-specific IVR CallFlow from the panel.
    The call_flow queryset is restricted to the company's active CallFlows
    by the view layer (SectionCreateView / SectionUpdateView).
    ---
    Formulario para crear y actualizar un registro de Section.
    Incluye el campo is_24h añadido en la sesión 2026-04-13.
    Actualización 2026-04-16 (Paso 37.C — Estrategia B): campo call_flow
    añadido para asignar un CallFlow IVR específico de sección desde el panel.
    El queryset de call_flow se restringe a los CallFlows activos de la empresa
    desde la capa de vistas (SectionCreateView / SectionUpdateView).
    """

    class Meta:
        model = Section
        fields = ["name", "description", "contacts", "call_flow", "data_capture_set", "is_24h", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "contacts": forms.SelectMultiple(attrs={"class": "form-select", "size": "6"}),
            "call_flow": forms.Select(attrs={"class": "form-select"}),
            "data_capture_set": forms.Select(attrs={"class": "form-select"}),
            "is_24h": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "name": "Nombre",
            "description": "Descripción",
            "contacts": "Contactos",
            "call_flow": "Flujo IVR de sección",
            "data_capture_set": "Conjunto de captura de datos",
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
    Updated 2026-04-16 (Step 37.C — Estrategia B): fallback_section field
    added to designate a last-resort section when no qualifying section can
    attend the caller. The fallback_section queryset is restricted to the
    company's active Sections by the view layer (CallFlowCreateView /
    CallFlowUpdateView).
    The notification_contact queryset is restricted to the company's contacts
    by the view layer (CallFlowCreateView / CallFlowUpdateView).
    ---
    Formulario para crear y actualizar un registro de CallFlow.
    Incluye el campo notification_contact añadido en la sesión 2026-04-13.
    Actualización 2026-04-16 (Paso 37.C — Estrategia B): campo fallback_section
    añadido para designar una sección de último recurso cuando ninguna sección
    cualificada pueda atender al llamante. El queryset de fallback_section se
    restringe a las Sections activas de la empresa desde la capa de vistas
    (CallFlowCreateView / CallFlowUpdateView).
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
            "fallback_section",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "system_instruction": forms.Textarea(attrs={"class": "form-control", "rows": 8}),
            "initial_greeting": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "notification_contact": forms.Select(attrs={"class": "form-select"}),
            "fallback_section": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "name": "Nombre del flujo",
            "system_instruction": "Instrucción de sistema",
            "initial_greeting": "Saludo inicial",
            "notification_contact": "Contacto de notificación (actividad no recogida)",
            "fallback_section": "Sección de fallback (último recurso)",
            "is_active": "Activo",
        }


class CorporateVoiceProfileForm(forms.ModelForm):
    """
    Form for creating and updating a CorporateVoiceProfile record.
    Includes voice_name selector for choosing the Gemini Live agent voice.
    ---
    Formulario para crear y actualizar un registro de CorporateVoiceProfile.
    Incluye selector voice_name para elegir la voz del agente Gemini Live.
    """

    class Meta:
        model = CorporateVoiceProfile
        fields = [
            "voice_name",
            "tone_guidelines",
            "sample_responses",
            "forbidden_phrases",
            "is_active",
        ]
        widgets = {
            "voice_name": forms.Select(attrs={"class": "form-select"}),
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
            "voice_name": "Voz del agente IVR",
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


class CompanyUserCreateForm(forms.Form):
    """
    Form for creating a new CompanyUser from the panel.
    The ADMIN provides username, full name, role and an initial password.
    must_change_password is set to True automatically by the view.
    ---
    Formulario para crear un nuevo CompanyUser desde el panel.
    El ADMIN introduce nombre de usuario, nombre completo, rol y contraseña inicial.
    must_change_password se activa automáticamente en la vista.
    """

    username = forms.CharField(
        max_length=150,
        label="Nombre de usuario",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "nombre.apellido",
            "autofocus": True,
        }),
    )
    first_name = forms.CharField(
        max_length=150,
        label="Nombre",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    last_name = forms.CharField(
        max_length=150,
        label="Apellidos",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    role = forms.ChoiceField(
        choices=CompanyUser.ROLE_CHOICES,
        label="Rol",
        initial=CompanyUser.ROLE_OPERATOR,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    initial_password = forms.CharField(
        max_length=128,
        label="Contraseña inicial",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Dejar vacío para usar '1234'",
        }),
        help_text=(
            "El usuario deberá cambiarla en su primer acceso. "
            "Si se deja vacío se asigna '1234' como contraseña inicial."
        ),
    )

    def clean_username(self):
        """
        Validates that the username is not already taken by another auth.User.
        ---
        Valida que el nombre de usuario no esté ya en uso por otro auth.User.
        """
        username = self.cleaned_data.get("username")
        if User.objects.filter(username=username).exists():
            raise ValidationError(
                "Este nombre de usuario ya está en uso. Elige otro."
            )
        return username

    def get_initial_password(self):
        """
        Returns the initial password, defaulting to '1234' if blank.
        ---
        Retorna la contraseña inicial, usando '1234' por defecto si está vacía.
        """
        return self.cleaned_data.get("initial_password") or "1234"


class PanelPasswordChangeForm(PasswordChangeForm):
    """
    Custom password change form for the panel with Bootstrap CSS classes.
    Used for voluntary password changes where the user knows their current password.
    Inherits full validation from Django's PasswordChangeForm (requires old_password).
    ---
    Formulario de cambio de contraseña para el panel con clases CSS Bootstrap.
    Se usa para cambios voluntarios de contraseña donde el usuario conoce la actual.
    Hereda la validación completa de PasswordChangeForm de Django (requiere old_password).
    """

    def __init__(self, *args, **kwargs):
        """
        Applies Bootstrap form-control CSS class to all three password fields.
        ---
        Aplica la clase CSS form-control de Bootstrap a los tres campos de contraseña.
        """
        super().__init__(*args, **kwargs)
        for field_name in ("old_password", "new_password1", "new_password2"):
            self.fields[field_name].widget.attrs.update({"class": "form-control"})
        self.fields["old_password"].label  = "Contraseña actual"
        self.fields["new_password1"].label = "Nueva contraseña"
        self.fields["new_password2"].label = "Confirmar nueva contraseña"
        self.fields["new_password1"].help_text = (
            "Mínimo 8 caracteres. No puede ser completamente numérica "
            "ni demasiado similar a tu nombre de usuario."
        )


class PanelSetPasswordForm(SetPasswordForm):
    """
    Password set form for forced password changes (must_change_password=True).
    Does NOT require the current password — the user arriving here for the first
    time does not know their system-assigned initial password ('1234').
    Inherits full validation from Django's SetPasswordForm (new_password1 +
    new_password2 only).
    ---
    Formulario de establecimiento de contraseña para cambios forzados
    (must_change_password=True). NO requiere la contraseña actual — el usuario
    que llega aquí por primera vez desconoce la contraseña inicial asignada
    por el sistema ('1234').
    Hereda la validación completa de SetPasswordForm de Django (solo new_password1
    y new_password2).
    """

    def __init__(self, *args, **kwargs):
        """
        Applies Bootstrap form-control CSS class to both new-password fields.
        ---
        Aplica la clase CSS form-control de Bootstrap a los dos campos de nueva contraseña.
        """
        super().__init__(*args, **kwargs)
        for field_name in ("new_password1", "new_password2"):
            self.fields[field_name].widget.attrs.update({"class": "form-control"})
        self.fields["new_password1"].label = "Nueva contraseña"
        self.fields["new_password2"].label = "Confirmar nueva contraseña"
        self.fields["new_password1"].help_text = (
            "Mínimo 8 caracteres. No puede ser completamente numérica "
            "ni demasiado similar a tu nombre de usuario."
        )


class DataCaptureSetForm(forms.ModelForm):
    """
    Form for creating and updating a DataCaptureSet record.
    The 'fields' JSONField is intentionally excluded from the Meta fields list:
    it is populated via a hidden input ('fields_json') managed by the JS dynamic
    row builder in the template, which serialises the field definitions to a JSON
    string before the form is submitted. The view's form_valid() deserialises
    this value and assigns it to form.instance.fields before saving.
    ---
    Formulario para crear y actualizar un registro de DataCaptureSet.
    El JSONField 'fields' se excluye intencionalmente de la lista Meta.fields:
    se rellena mediante un campo oculto ('fields_json') gestionado por el constructor
    de filas JS dinámico del template, que serializa las definiciones de campos a una
    cadena JSON antes del submit. El form_valid() de la vista deserializa este valor
    y lo asigna a form.instance.fields antes de guardar.
    """

    class Meta:
        model = DataCaptureSet
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Captura de datos de asistencia",
            }),
        }
        labels = {
            "name": "Nombre del conjunto",
        }
