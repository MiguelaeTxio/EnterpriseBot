# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/DOCS_ATTACHED_2_ANNEX_V03/V03DOC_DATA_MODEL.md

# MODELO DE DATOS IVR MULTIEMPRESA
# MULTICOMPANY IVR DATA MODEL
---
# Especificación técnica completa de los modelos Django del Hito 3.
# Complete technical specification of the Django models for Milestone 3.

## 1. Diagrama de Relaciones / Relationship Diagram

    Company
      ├── CompanyUser (FK→auth.User)
      │     └── PresenceStatus
      ├── CorporateVoiceProfile
      ├── DataCaptureSet
      ├── Section (M2M→Contact, FK→DataCaptureSet)
      ├── Contact (FK→CompanyUser nullable)
      ├── CallFlow
      └── PhoneNumber (FK→CallFlow)

## 2. Especificación de Campos / Field Specification

### Company
    name            CharField(max_length=200)
    slug            SlugField(unique=True)          # generado automáticamente desde name
    logo            ImageField(nullable)
    is_active       BooleanField(default=True)
    created_at      DateTimeField(auto_now_add=True)
    updated_at      DateTimeField(auto_now=True)

### CompanyUser
    company         ForeignKey(Company, on_delete=CASCADE)
    user            OneToOneField(auth.User, on_delete=CASCADE)
    role            CharField(choices=[('ADMIN','Admin'),('OPERATOR','Operador')])
    is_active       BooleanField(default=True)
    created_at      DateTimeField(auto_now_add=True)
    updated_at      DateTimeField(auto_now=True)

    Constraint: user.is_staff MUST be False para CompanyUser.
    El acceso a /admin/ se bloquea via middleware CompanyUserAdminBlockMiddleware.

### Contact
    company         ForeignKey(Company, on_delete=CASCADE)
    name            CharField(max_length=200)
    phone_number    CharField(max_length=20)        # formato E.164: +34XXXXXXXXX
    is_internal     BooleanField(default=False)
    company_user    ForeignKey(CompanyUser, null=True, blank=True, on_delete=SET_NULL)
    created_at      DateTimeField(auto_now_add=True)
    updated_at      DateTimeField(auto_now=True)

    Constraint: si is_internal=True, company_user no puede ser null.

### Section
    company         ForeignKey(Company, on_delete=CASCADE)
    name            CharField(max_length=200)
    description     TextField(blank=True)
    contacts        ManyToManyField(Contact, blank=True)
    data_capture_set ForeignKey(DataCaptureSet, null=True, blank=True, on_delete=SET_NULL)
    is_active       BooleanField(default=True)
    created_at      DateTimeField(auto_now_add=True)
    updated_at      DateTimeField(auto_now=True)

### PhoneNumber
    company         ForeignKey(Company, on_delete=CASCADE)
    number          CharField(max_length=20, unique=True)  # formato E.164
    friendly_name   CharField(max_length=200, blank=True)
    call_flow       ForeignKey(CallFlow, null=True, blank=True, on_delete=SET_NULL)
    is_active       BooleanField(default=True)
    created_at      DateTimeField(auto_now_add=True)
    updated_at      DateTimeField(auto_now=True)

### CallFlow
    company         ForeignKey(Company, on_delete=CASCADE)
    name            CharField(max_length=200)
    system_instruction  TextField()
    initial_greeting    TextField()
    is_active       BooleanField(default=True)
    created_at      DateTimeField(auto_now_add=True)
    updated_at      DateTimeField(auto_now=True)

### PresenceStatus
    company_user    ForeignKey(CompanyUser, on_delete=CASCADE)
    status          CharField(choices=[
                        ('AVAILABLE','Disponible'),
                        ('IN_MEETING','Reunido'),
                        ('BUSY_UNTIL','Ocupado hasta'),
                        ('ABSENT_SCHEDULED','Ausente programado'),
                        ('ABSENT_VACATION','Vacaciones'),
                    ])
    starts_at       DateTimeField(default=now)
    ends_at         DateTimeField(null=True, blank=True)
    reminder_sent_at DateTimeField(null=True, blank=True)
    created_at      DateTimeField(auto_now_add=True)

    Constraint: solo un PresenceStatus activo por CompanyUser en cada momento.
    Un PresenceStatus es activo si: starts_at <= now AND (ends_at IS NULL OR ends_at > now).

### CorporateVoiceProfile
    company         ForeignKey(Company, on_delete=CASCADE, unique=True)
    tone_guidelines TextField()
    sample_responses JSONField(default=list)
    forbidden_phrases JSONField(default=list)
    is_active       BooleanField(default=True)
    created_at      DateTimeField(auto_now_add=True)
    updated_at      DateTimeField(auto_now=True)

### DataCaptureSet
    company         ForeignKey(Company, on_delete=CASCADE)
    section         ForeignKey(Section, null=True, blank=True, on_delete=SET_NULL)
    name            CharField(max_length=200)
    fields          JSONField(default=list)         # PENDIENTE: estructura a definir con piloto
    created_at      DateTimeField(auto_now_add=True)
    updated_at      DateTimeField(auto_now=True)

## 3. Migraciones / Migrations

Orden de creación obligatorio para respetar dependencias FK:
1. Company
2. CompanyUser
3. CorporateVoiceProfile
4. DataCaptureSet (sin FK a Section aún)
5. Section
6. Contact
7. CallFlow
8. PhoneNumber
9. PresenceStatus

Nota: DataCaptureSet se crea sin FK a Section para evitar dependencia circular.
Section tiene FK a DataCaptureSet. La relación inversa se navega desde Section.
