# SISTEMA DE GESTIÓN DE PRESENCIA
# PRESENCE MANAGEMENT SYSTEM
---
# Especificación del sistema de estados de presencia y ausencias de usuarios.
# Specification of the user presence states and absence management system.

## 1. Estados y Transiciones / States and Transitions

    AVAILABLE ──────────────────────────────────────────┐
        │                                               │
        ├──[activar IN_MEETING]──► IN_MEETING           │
        │       │                    │                  │
        │       │               [3h sin ends_at]        │
        │       │                    │                  │
        │       │              REMINDER enviado         │
        │       │              vía SMS/WhatsApp         │
        │       │                    │                  │
        │       └──[ends_at alcanzado o usuario OK]─────┤
        │                                               │
        ├──[activar BUSY_UNTIL]──► BUSY_UNTIL           │
        │       │                    │                  │
        │       └──[ends_at alcanzado]──────────────────┤
        │                                               │
        ├──[activar ABSENT_SCHEDULED]──► ABSENT_SCHED   │
        │       └──[ends_at alcanzado]──────────────────┤
        │                                               │
        └──[activar ABSENT_VACATION]──► ABSENT_VAC      │
                └──[ends_at alcanzado]──────────────────┘
                                                   AVAILABLE

## 2. Lógica de Presencia Activa / Active Presence Logic

Un PresenceStatus es ACTIVO si:
    starts_at <= now() AND (ends_at IS NULL OR ends_at > now())

Solo puede existir un registro activo por CompanyUser en cada momento.
Al crear un nuevo PresenceStatus, se cierra el anterior estableciendo
su ends_at = now() si estaba abierto.

Método de consulta canónico:
    PresenceStatus.objects.filter(
        company_user=user,
        starts_at__lte=now(),
    ).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=now())
    ).order_by('-starts_at').first()

## 3. Tareas Celery de Presencia / Presence Celery Tasks

### Tarea: check_in_meeting_reminders
Periodicidad: cada 15 minutos (Celery Beat).
Lógica:
    - Busca todos los PresenceStatus activos con status=IN_MEETING,
      ends_at=None y reminder_sent_at=None.
    - Para cada uno, comprueba si han pasado 3 horas desde starts_at.
    - Si es así, envía SMS/WhatsApp vía Twilio al company_user contact phone_number
      con el mensaje: "¿Sigues reunido? Responde: 1h / 2h / disponible"
    - Actualiza reminder_sent_at = now().

### Tarea: expire_presence_statuses
Periodicidad: cada 5 minutos (Celery Beat).
Lógica:
    - Busca todos los PresenceStatus activos con ends_at IS NOT NULL
      y ends_at <= now().
    - Para cada uno, crea un nuevo PresenceStatus con status=AVAILABLE
      y starts_at=now() para el mismo company_user.
    - El registro expirado queda inactivo por la lógica de consulta canónica.

## 4. Respuesta al Recordatorio / Reminder Response Handling

El usuario responde al SMS/WhatsApp con: "1h", "2h" o "disponible".
Se implementa un webhook Twilio SMS en /api/sms/presence/ que:
    - Identifica al CompanyUser por el número de teléfono remitente.
    - Si responde "1h" o "2h": actualiza ends_at del PresenceStatus activo.
    - Si responde "disponible": cierra el PresenceStatus activo y crea
      uno nuevo con status=AVAILABLE.
PENDIENTE: Este webhook se implementará en el hito de integración WhatsApp/SMS.

## 5. Impacto en el IVR / IVR Impact

Cuando el IVR recibe una llamada y construye el SYSTEM_INSTRUCTION dinámico,
consulta el PresenceStatus activo de todos los Contact internos de la Company
e inserta en el prompt la información de disponibilidad:

    "Miguel está actualmente reunido."
    "Ana está de vacaciones hasta el 15 de abril."
    "Carlos está disponible."

Esto permite que Alia informe al llamante del estado real de cada persona
sin necesidad de intervención humana.
