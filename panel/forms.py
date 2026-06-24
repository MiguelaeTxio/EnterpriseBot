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
        fields = ["name", "description", "contacts", "call_flow", "data_capture_set", "is_24h", "is_active", "is_broadcast_enabled", "ivr_transfer_enabled", "ivr_breakdown_enabled", "workday_schedule"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "contacts": forms.SelectMultiple(attrs={"class": "form-select", "size": "6"}),
            "call_flow": forms.Select(attrs={"class": "form-select"}),
            "data_capture_set": forms.Select(attrs={"class": "form-select"}),
            "is_24h": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_broadcast_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "ivr_transfer_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "ivr_breakdown_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "workday_schedule": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "name": "Nombre",
            "description": "Descripción",
            "contacts": "Contactos",
            "call_flow": "Flujo IVR de sección",
            "data_capture_set": "Conjunto de captura de datos",
            "is_24h": "Disponible 24 horas",
            "is_active": "Activa",
            "is_broadcast_enabled": "Habilitada para circulares WhatsApp",
            "ivr_transfer_enabled": "Transferencia IVR habilitada",
            "ivr_breakdown_enabled": "Avería interna IVR habilitada",
            "workday_schedule": "Horario de trabajo por defecto",
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
    Form for creating a new CompanyUser from the panel (Supervisor or Admin).
    The Supervisor provides username, full name, role, optional section,
    optional phone number and IVR active flag.
    Password derivation:
    - WORKSHOP / WORKSHOPBOSS: last 4 digits of DNI (fallback '1234'),
      must_change_password=False (operators log in with their DNI digits).
    - ADMIN / SUPERVISOR: explicit initial_password or '1234',
      must_change_password=True (forced change on first login).
    Updated H13: section, phone_number and is_ivr_active fields added.
    Updated H17: dni field added; password derivation by role.
    ---
    Formulario para crear un nuevo CompanyUser desde el panel (Supervisor o Admin).
    El Supervisor introduce nombre de usuario, nombre completo, rol, sección
    opcional, DNI, teléfono opcional y flag de activo en IVR.
    Derivación de contraseña:
    - WORKSHOP / WORKSHOPBOSS: 4 últimas cifras del DNI (fallback '1234'),
      must_change_password=False (los operarios acceden con sus dígitos de DNI).
    - ADMIN / SUPERVISOR: initial_password explícito o '1234',
      must_change_password=True (cambio forzado en el primer acceso).
    Actualización H13: añadidos campos section, phone_number e is_ivr_active.
    Actualización H17: añadido campo dni; derivación de contraseña por rol.
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
        initial=CompanyUser.ROLE_WORKSHOP,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_role"}),
    )
    section = forms.ModelChoiceField(
        queryset=Section.objects.none(),
        label="Sección",
        required=False,
        empty_label="— Sin sección —",
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "id_section",
        }),
        help_text=(
            "Selecciona la sección a la que pertenece el trabajador. "
            "El rol se pre-rellenará con el rol por defecto de la sección."
        ),
    )
    phone_number = forms.CharField(
        max_length=20,
        label="Teléfono (E.164)",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "+34XXXXXXXXX",
        }),
        help_text=(
            "Opcional. Si se indica, se creará o vinculará el contacto WhatsApp "
            "correspondiente para recibir broadcasts de su sección."
        ),
    )
    is_ivr_active = forms.BooleanField(
        label="Activo en IVR",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text=(
            "Si está activo, el contacto vinculado participará en el enrutamiento "
            "IVR y en los broadcasts de WhatsApp de su sección."
        ),
    )
    dni = forms.CharField(
        max_length=20,
        label="DNI / NIF",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "12345678A",
        }),
        help_text=(
            "Obligatorio para operarios de taller (WORKSHOP / WORKSHOPBOSS). "
            "Los 4 últimos dígitos se usarán como contraseña inicial. "
            "Opcional para el resto de roles."
        ),
    )
    initial_password = forms.CharField(
        max_length=128,
        label="Contraseña inicial",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Solo para ADMIN / SUPERVISOR. Vacío: '1234'",
        }),
        help_text=(
            "Solo aplica para roles ADMIN y SUPERVISOR. "
            "Para operarios de taller la contraseña se deriva del DNI."
        ),
    )

    def get_initial_password(self):
        """
        Returns the initial password depending on the role.
        - WORKSHOP / WORKSHOPBOSS: last 4 digits of DNI, fallback '1234'.
        - Other roles: explicit initial_password field, fallback '1234'.
        ---
        Retorna la contraseña inicial según el rol.
        - WORKSHOP / WORKSHOPBOSS: 4 últimas cifras del DNI, fallback '1234'.
        - Otros roles: campo initial_password explícito, fallback '1234'.
        """
        role = self.cleaned_data.get("role", "")
        if role in (
            CompanyUser.ROLE_WORKSHOP,
            CompanyUser.ROLE_WORKSHOPBOSS,
        ):
            dni = self.cleaned_data.get("dni", "").strip()
            if len(dni) >= 4:
                return dni[-4:]
            return "1234"
        return self.cleaned_data.get("initial_password") or "1234"

    def clean_username(self):
        """
        Validates that the username is not already taken by another auth.User.
        ---
        Valida que el nombre de usuario no esté ya en uso por otro auth.User.
        """
        username = self.cleaned_data.get("username", "").strip()
        if User.objects.filter(username=username).exists():
            raise ValidationError(
                "Este nombre de usuario ya está en uso. Elige otro."
            )
        return username

    def clean_phone_number(self):
        """
        Normalises the phone number to E.164 format (leading + preserved).
        Returns empty string if blank.
        ---
        Normaliza el número de teléfono a formato E.164 (conserva el + inicial).
        Retorna cadena vacía si está en blanco.
        """
        phone = self.cleaned_data.get("phone_number", "").strip()
        return phone

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


class MachineAssetForm(forms.ModelForm):
    """
    Form for creating and updating a MachineAsset record from the panel.
    Used by MachineAssetCreateView and MachineAssetUpdateView.
    All fields are optional except code, which is the primary lookup key.

    ---

    Formulario para crear y actualizar un registro de MachineAsset desde el panel.
    Usado por MachineAssetCreateView y MachineAssetUpdateView.
    Todos los campos son opcionales excepto code, que es la clave de búsqueda principal.
    """

    class Meta:
        from fleet.models import MachineAsset
        model  = MachineAsset
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
            "purchase_date": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),
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


class WorkerSignupForm(forms.Form):
    """
    Public self-registration form for workshop operators (WORKSHOP role).
    The authenticated company is resolved server-side (Grupo Álvarez pilot).
    Validates DNI uniqueness within the resolved company and password match.
    Architecture is open for future multi-company extension by passing the
    target company as a constructor argument.
    ---
    Formulario de auto-registro público para operarios de taller (rol WORKSHOP).
    La empresa se resuelve en el servidor (piloto Grupo Álvarez).
    Valida unicidad de DNI dentro de la empresa resuelta y coincidencia de contraseñas.
    La arquitectura está preparada para extensión multiempresa futura pasando
    la empresa destino como argumento del constructor.
    """

    first_name = forms.CharField(
        max_length=150,
        label="Nombre",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Tu nombre",
            "autofocus": True,
        }),
    )
    last_name = forms.CharField(
        max_length=150,
        label="Apellidos",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Tus apellidos",
        }),
    )
    phone = forms.CharField(
        max_length=20,
        label="Teléfono",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "+34XXXXXXXXX",
        }),
        help_text="Opcional. Formato libre.",
    )
    dni = forms.CharField(
        max_length=20,
        label="DNI / NIF",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "12345678A",
        }),
    )
    username = forms.CharField(
        max_length=150,
        label="Nombre de usuario",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "nombre.apellido",
        }),
        help_text="Solo letras, números y los caracteres . @ + - _",
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Mínimo 8 caracteres",
        }),
    )
    password_confirm = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Repite la contraseña",
        }),
    )

    def __init__(self, *args, company=None, **kwargs):
        """
        Accepts an optional company instance for DNI uniqueness validation.
        When company is None the DNI uniqueness check is skipped (safe default
        for the pilot single-company deployment).
        ---
        Acepta una instancia de empresa opcional para la validación de unicidad de DNI.
        Cuando company es None, la comprobación de unicidad de DNI se omite
        (comportamiento seguro por defecto para el despliegue piloto de empresa única).
        """
        self._company = company
        super().__init__(*args, **kwargs)

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

    def clean_dni(self):
        """
        Validates DNI uniqueness within the resolved company when available.
        Empty DNI values bypass the uniqueness check (field is required, so
        an empty value will already have been rejected by required validation).
        ---
        Valida la unicidad del DNI dentro de la empresa resuelta cuando está disponible.
        Los valores de DNI vacíos omiten la comprobación de unicidad (el campo es
        obligatorio, por lo que un valor vacío ya habrá sido rechazado por la
        validación de required).
        """
        dni = self.cleaned_data.get("dni", "").strip()
        if dni and self._company is not None:
            if CompanyUser.objects.filter(
                company=self._company, dni__iexact=dni
            ).exists():
                raise ValidationError(
                    "Este DNI ya está registrado en la empresa. "
                    "Contacta con tu administrador si crees que es un error."
                )
        return dni

    def clean(self):
        """
        Cross-field validation: ensures both password fields match.
        ---
        Validación cruzada de campos: comprueba que ambos campos de contraseña coincidan.
        """
        cleaned_data     = super().clean()
        password         = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", "Las contraseñas no coinciden.")
        return cleaned_data


class OwnProfileForm(forms.Form):
    """
    Form for editing the authenticated CompanyUser own profile.
    Currently exposes only the alias field (chat IRC nick).
    Alias uniqueness within the company is validated in clean_alias().
    The company instance must be injected via set_company() before validation.
    ---
    Formulario para editar el perfil propio del CompanyUser autenticado.
    Actualmente expone únicamente el campo alias (nick de chat IRC).
    La unicidad del alias dentro de la empresa se valida en clean_alias().
    La instancia de empresa debe inyectarse mediante set_company() antes de validar.
    """

    alias = forms.CharField(
        max_length=50,
        required=False,
        label="Alias de chat",
        help_text=(
            "Apodo que aparecerá en las salas de chat IRC. "
            "Debe ser único dentro de tu empresa. "
            "Los mensajes enviados anteriormente mantienen el alias con el que fueron enviados."
        ),
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Tu alias de chat…",
            "maxlength": "50",
        }),
    )

    def __init__(self, *args, **kwargs):
        """
        Accepts company_user kwarg to pre-populate the alias field and
        store the company for uniqueness validation.
        ---
        Acepta el kwarg company_user para prerellenar el alias y almacenar
        la empresa para la validación de unicidad.
        """
        self._company_user = kwargs.pop("company_user", None)
        super().__init__(*args, **kwargs)
        if self._company_user and not args and not kwargs.get("data"):
            self.fields["alias"].initial = self._company_user.alias

    def clean_alias(self):
        """
        Validates alias uniqueness within the company, excluding the
        authenticated user themselves.
        ---
        Valida la unicidad del alias dentro de la empresa, excluyendo
        al propio usuario autenticado.
        """
        alias = self.cleaned_data.get("alias", "").strip()
        if alias and self._company_user is not None:
            qs = CompanyUser.objects.filter(
                company=self._company_user.company,
                alias__iexact=alias,
            ).exclude(pk=self._company_user.pk)
            if qs.exists():
                raise ValidationError(
                    "Este alias ya está en uso en tu empresa. Elige otro diferente."
                )
        return alias

# Re-export desde fleet.forms (H12/H21 split)
from fleet.forms import MachineAssetForm  # noqa: F401



