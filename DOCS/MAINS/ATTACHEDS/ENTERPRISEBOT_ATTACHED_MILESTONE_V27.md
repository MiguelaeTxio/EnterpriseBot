# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V27.md

# Anexo de Hito V27 — Ingesta de Documentación vía Correo Electrónico
# Proyecto: EnterpriseBot
# Fecha de inicio: 2026-07-17 (S024)

---

## 1. Visión General del Hito

Grupo Álvarez recibe documentación oficial de máquinas/centros de gasto
(y, previsiblemente, de personal) por correo electrónico — facturas,
certificados, pólizas renovadas, etc. — sin ningún vínculo hoy con la
plataforma. Este hito construye una cuenta de correo dedicada y un
mecanismo de lectura de esa cuenta vía API que examine los correos
entrantes, clasifique la documentación que traigan como adjunto, y la
persista siguiendo el mismo patrón ya construido en H23 (Google Cloud
Storage + registro en BD, `document_management` de H26).

Origen: sesión S024, durante la planificación de la interfaz de H23 —
Miguel Ángel identificó esta necesidad como pieza importante pero de
peso propio, y pidió abrirla como hito independiente en vez de
colgarla de H23.

---

## 2. Principios Rectores

1. **Reutilización, nunca duplicación (DRY).** El motor de
   clasificación por contenido (Gemini Vision) ya construido en H23
   (`machine_documents/document_classification_service.py`) se
   reutiliza para los adjuntos de correo — no se construye un segundo
   clasificador. Si el servicio actual está acoplado en exceso a la
   vía de subida manual, extraer la parte reutilizable a un módulo
   común antes de duplicar nada (a valorar al empezar la sesión de
   código de este hito).
2. **Máxima modularización**, premisa explícita de Miguel Ángel
   (S024): archivos pequeños, de responsabilidad única. Evitar
   archivos grandes que mezclen lectura de correo + clasificación +
   persistencia en un solo módulo — separar por responsabilidad
   (cliente de la API de correo, extracción de adjuntos, orquestación,
   persistencia), igual que la documentación de este hito debe
   mantenerse igualmente ligera y no acumular todo en una sola
   sección.
3. **Persistencia doble**, mismo patrón que H23/H26: Google Cloud
   Storage (`spare_parts/gcs_service.py`) + registro en BD.
4. **Fidelidad a las instrucciones explícitas** (directriz 4.8 del
   master document) — ninguna decisión de diseño de este hito
   (proveedor de correo, mecanismo de detección de máquina/
   trabajador, flujo exacto) se da por cerrada sin confirmación
   explícita de Miguel Ángel.

---

## 3. Contexto Técnico — Punto de Partida (a confirmar/ajustar al inicio de la sesión que retome este hito)

- **Cuenta de correo dedicada:** por crear — proveedor, dominio y
  credenciales a definir con Miguel Ángel al empezar. Verificar en
  línea (directriz 4.4/SINE QUA NON del master document) la API
  disponible para el proveedor elegido antes de implementar nada
  (IMAP genérico vs. API propietaria tipo Gmail API/Microsoft Graph —
  cada una con requisitos de autenticación distintos).
- **Detección de máquina/trabajador destinatario:** a diseñar — posible
  combinación de remitente/asunto + contenido de los propios adjuntos
  (mismo clasificador de H23 ya extrae metadatos que podrían apuntar a
  una máquina/matrícula/persona concreta). Sin decisión cerrada
  todavía.
- **Reutilización de servicios existentes:**
  - `machine_documents/document_classification_service.py` (H23) —
    clasificación Gemini Vision.
  - `spare_parts/gcs_service.py` (H26) — persistencia en GCS.
  - Modelo `MachineDocument` (H23) / futuro modelo de documentación de
    personal (H25) como destino final del registro en BD — a confirmar
    si un correo puede generar documentación de ambos dominios a la
    vez o si se tratan por separado.
- **Sin decisión tomada sobre:** frecuencia de lectura del buzón
  (polling periódico vía Celery Beat vs. webhook si el proveedor lo
  soporta), y qué ocurre con un correo cuyo adjunto no se puede
  clasificar ni asignar a ninguna máquina/trabajador con confianza
  suficiente (mismo problema del estado "sin asignar" previsto en H23,
  posible reutilización directa del mismo mecanismo).

---

## 4. Preguntas Abiertas — Resolver al Empezar la Sesión que Retome Este Hito

1. **Proveedor de la cuenta de correo** y método de acceso (IMAP vs.
   API propietaria) — condiciona toda la arquitectura de lectura.
2. **Mecanismo de detección de máquina/trabajador destinatario** —
   ¿por remitente, por asunto, por contenido del adjunto, combinación
   de varios?
3. **Frecuencia/mecanismo de lectura del buzón** — polling vs. webhook.
4. **Alcance de persistencia:** ¿este hito cubre solo documentación de
   centros de gasto (H23) o también de personal (H25) desde el
   principio?
5. **Tratamiento de adjuntos no clasificables/no asignables** —
   ¿reutilizar tal cual el bloque "sin asignado" previsto en H23, o
   necesita un tratamiento propio?

---

## 5. Hoja de Ruta para la Sesión que Retome Este Hito

Ninguna todavía — hito recién creado en S024, sin sesión de código
propia. La primera sesión que lo retome debe empezar por las
preguntas abiertas de la sección 4, con Miguel Ángel, antes de escribir
ningún modelo o servicio nuevo.

---

## 6. Registro de Sesiones

| Sesión | Fecha | Trabajo realizado |
|---|---|---|
| S024 | 2026-07-17 | Hito creado (Caso C del enrutador de anexos), a petición explícita de Miguel Ángel durante la planificación de la interfaz de H23. Sin trabajo de código todavía — ver sección 4 (preguntas abiertas) y sección 5 (hoja de ruta) para el punto de partida de la siguiente sesión que lo retome. |
