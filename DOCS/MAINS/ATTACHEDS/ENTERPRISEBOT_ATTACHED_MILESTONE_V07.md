# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md

# Anexo de Hito V07 — Partes Diarios de Reparación: Entrada Digital desde el Panel
# Proyecto: EnterpriseBot
# Estado: EN PROGRESO
# Fecha de inicio: 2026-04-27

---

## 1. Visión General del Hito

El Hito 7 digitaliza el origen de los partes de reparación. Hasta ahora el flujo
exigía que un encargado escaneara los partes manuscritos en papel y los subiera
como PDF para que Gemini Vision los procesara. Este hito elimina el papel como
origen obligatorio: el propio operario de taller rellena su parte directamente
desde el panel de EnterpriseBot, eligiendo la vía que mejor se adapta a su
contexto en cada momento.

El objetivo estratégico es la adopción orgánica del formulario web estructurado
(Form) como vía principal, sin imponer nada. La fricción deliberada del flujo
Upload (validación campo a campo de datos ilegibles) y la comodidad del dictado
por voz (STT) actúan como catalizadores naturales del abandono progresivo del
manuscrito en papel.

---

## 2. Arquitectura Técnica

### 2.1. Nuevo rol OPERATOR en CompanyUser

Se añade el valor `OPERATOR` a `CompanyUser.role` (TextChoices). Un operario
con este rol tiene acceso al panel restringido a una única sección: la entrada
de partes diarios. No puede acceder a ninguna otra vista del panel.

El mixin `CompanyUserRequiredMixin` ya gestiona la autenticación. Se añade un
nuevo mixin `OperatorRequiredMixin` (o se extiende el existente) que restringe
el acceso a las vistas de operario a los roles `OPERATOR` y `ADMIN`.

La gestión de operarios (crear, editar, activar/desactivar) se integra en el
apartado de Usuarios del panel de administración existente, accesible solo para
`ADMIN`. El formulario de creación `CompanyUserCreateForm` se extiende para
soportar el nuevo rol.

### 2.2. Tres vías de entrada convergentes

Las tres vías pre-rellenan el mismo formulario de confirmación. El formulario
de confirmación es el único punto de persistencia en BD — ninguna vía persiste
datos sin pasar por él.

#### Vía A — Form (formulario web estructurado)

El operario rellena directamente los campos del parte en un formulario web:
- Fecha del parte (date picker — por defecto hoy).
- Código de máquina (selector con autocompletado desde MachineAsset de su empresa).
- Descripción de avería (textarea).
- Reparación realizada (textarea).
- H.C. — hora de comienzo (time picker, redondeada a media hora).
- H.F. — hora de finalización (time picker, redondeada a media hora).
- O.R. — referencia de orden de reparación (opcional).

El formulario puede tener múltiples bloques de trabajo (hasta 4, como el modelo
WorkOrderEntryLine define). El operario añade bloques con un botón "+ Añadir
bloque". Al confirmar, se crea un WorkOrder sintético (status=DONE directamente,
sin pipeline Celery) + WorkOrderEntry + N WorkOrderEntryLine. Sin llamada a IA.
Coste cero.

#### Vía B — STT (Speech-to-Text via Web Speech API)

El operario pulsa un botón de micrófono y dicta el parte. La Web Speech API
del navegador (nativa, sin coste, sin IA externa) transcribe la voz a texto
en tiempo real. El texto transcrito se procesa client-side con un parser
JavaScript ligero que identifica campos por palabras clave y pre-rellena
el formulario de confirmación. El operario revisa, corrige si es necesario,
y confirma. La persistencia es idéntica a la Vía A.

El parser STT reconoce patrones como:
- "máquina A-54" → campo código de máquina.
- "avería: ruido en motor" → campo descripción de avería.
- "reparación: sustitución de rodamiento" → campo reparación.
- "comienzo las ocho y media" / "H.C. 8:30" → campo H.C.
- "fin a las doce" / "H.F. 12:00" → campo H.F.
- "OR 1234" / "orden 1234" → campo O.R.

#### Vía C — Upload (foto/PDF manuscrito con Gemini Vision)

El operario sube una foto o PDF de su parte manuscrito. El sistema lanza el
pipeline Gemini Vision existente (work_order_processor/services.py) de forma
síncrona (sin Celery — es una sola página) para extraer los datos del manuscrito.
Los datos extraídos pre-rellenan el formulario de confirmación. El operario
valida campo a campo, completando los datos faltantes o ilegibles marcados
con flags de incidencia. Solo al confirmar se persiste en BD.

La fricción deliberada de esta vía (tiempo de espera de Gemini + validación
exhaustiva de campos dudosos) incentiva orgánicamente la adopción de Vía A o B.

### 2.3. Formulario de confirmación (punto de convergencia)

Independientemente de la vía elegida, el operario siempre llega a un formulario
de confirmación con todos los campos pre-rellenados (o vacíos si la extracción
falló). El formulario muestra:
- Badges de confianza por campo (solo en Vía C).
- Campos con fondo amarillo si están vacíos o tienen flag de incidencia.
- Botón "Confirmar y guardar" → persiste WorkOrder + WorkOrderEntry +
  WorkOrderEntryLine en BD.
- Botón "Cancelar" → descarta sin persistir.

### 2.4. Persistencia directa (Vías A y B)

Para las Vías A y B se crea un WorkOrder sintético con estas particularidades:
- `status = DONE` desde el momento de creación (no pasa por PENDING/PROCESSING).
- `source_pdf` = null (no hay fichero PDF asociado).
- `total_pages = 1`, `processed_pages = 1`.
- `uploaded_by` = CompanyUser del operario autenticado.
- Se genera el Excel automáticamente tras la persistencia (llamada directa a
  `generate_work_order_excel()` sin Celery).

### 2.5. Apps Django involucradas

- `ivr_config` — modificación de `CompanyUser.role` para añadir `OPERATOR`.
- `panel` — nuevas vistas OperatorDashboardView, WorkOrderEntryFormView,
  WorkOrderEntrySTTView, WorkOrderEntryUploadView, WorkOrderEntryConfirmView.
  Nuevo mixin OperatorRequiredMixin. Extensión de CompanyUserCreateForm.
- `work_order_processor` — reutilización de services.py (Gemini Vision) y
  generate_work_order_excel() en modo síncrono para Vía C.

### 2.6. Navegación del operario en el panel

El operario con rol OPERATOR ve en el panel únicamente:
- Cabecera con su nombre y estado de presencia.
- Sidebar simplificado con un único ítem: "Nuevo parte".
- Selector de vía: tres tarjetas (Form / Voz / Foto) con descripción breve.
- Historial de sus propios partes del día en curso (solo lectura).

### 2.7. Stack tecnológico

- Web Speech API (nativa en Chrome/Edge) — STT sin coste ni dependencias.
- google-genai 1.69.0 / Vertex AI — Gemini Vision para Vía C (reutilizado).
- openpyxl — generación Excel síncrona post-persistencia.
- Django 5.2.12 — vistas síncronas estándar (sin Celery para Vías A y B).
- Bootstrap 5.3 + Bootstrap Icons — UI del formulario de confirmación.

---

## 3. Hoja de Ruta

### Paso 1 — Nuevo rol OPERATOR en CompanyUser
- Añadir `OPERATOR` a `CompanyUser.role` TextChoices en `ivr_config/models.py`.
- Migración ivr_config correspondiente.
- Extender `CompanyUserCreateForm` en `panel/forms.py` para incluir el rol OPERATOR.
- Extender `CompanyUserListView` para mostrar operarios en el listado de usuarios.
- Estado: COMPLETADO (2026-04-28).

### Paso 2 — Mixin y navegación restringida del operario
- Nuevo `OperatorRequiredMixin` en `panel/mixins.py`.
- `OperatorDashboardView`: vista de selector de vía (tres tarjetas).
- Template `panel/operator/dashboard.html`: sidebar simplificado + selector de vía.
- Modificación de `_nav_items.html` y `base.html` para renderizar sidebar
  reducido cuando el rol es OPERATOR.
- Estado: COMPLETADO (2026-04-28).

### Paso 3 — Vía A: formulario web estructurado (Form)
- `WorkOrderEntryFormView` en `panel/views.py`.
- Template `panel/operator/form_entry.html`: formulario multi-bloque con
  autocompletado de MachineAsset, time pickers y botón "+ Añadir bloque".
- `WorkOrderEntryConfirmView`: punto de confirmación y persistencia síncrona.
- Template `panel/operator/confirm_entry.html`: formulario de confirmación
  con badges de confianza y campos de alerta.
- Lógica de creación de WorkOrder sintético (status=DONE) + generación Excel.
- Estado: PENDIENTE.

### Paso 4 — Vía B: dictado por voz (STT)
- `WorkOrderEntrySTTView` en `panel/views.py`.
- Template `panel/operator/stt_entry.html`: interfaz de micrófono con
  visualización de transcripción en tiempo real y botón de confirmación.
- Parser JavaScript client-side de patrones de voz → campos del formulario.
- Pre-relleno del formulario de confirmación con los datos parseados.
- Estado: PENDIENTE.

### Paso 5 — Vía C: subida de foto/PDF (Upload)
- `WorkOrderEntryUploadView` en `panel/views.py`.
- Template `panel/operator/upload_entry.html`: interfaz de subida con
  preview de imagen y spinner de procesamiento.
- Llamada síncrona a Gemini Vision (services.py) para extracción de datos.
- Pre-relleno del formulario de confirmación con badges de confianza y
  campos con flag de incidencia resaltados en amarillo.
- Estado: PENDIENTE.

### Paso 6 — Validación E2E de las tres vías
- Prueba Form: creación de parte completo, verificación en BD y descarga Excel.
- Prueba STT: dictado de parte completo en Chrome, verificación de parser y
  pre-relleno del formulario de confirmación.
- Prueba Upload: foto de parte manuscrito, verificación de extracción Gemini,
  validación campo a campo y confirmación.
- Estado: PENDIENTE.

---

## 4. Registro de Sesiones

| Sesion | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| 001    | 2026-04-27 | —               | Creacion del anexo. Inicio formal del hito. |
| 002    | 2026-04-28 | Pasos 1 y 2     | Arquitectura de roles ampliada: WORKSHOP y DRIVER anadidos a CompanyUser.role. WorkshopRequiredMixin creado en panel/mixins.py. OperatorDashboardView implementada con redirección condicional desde PanelDashboardView. Navegacion restringida en _nav_items.html. Template operator/dashboard.html creado con selector de tres vias. Usuario de prueba taller_test_01 creado y validado E2E. Fix sidebar height:100vh en panel.css. Hito pausado para abrir H8. |

---

## 5. Hoja de Ruta para la Siguiente Sesion

### Objetivo principal
Paso 3 — Via A: formulario web estructurado.

### NOTA DE REACTIVACION
Este hito fue pausado en sesion 002 (2026-04-28) para abrir el H8
(Mejoras PDF->Excel + HTMX). Al reactivar, continuar desde el Paso 3.
Los Pasos 1 y 2 estan completados y validados E2E.

### PRIMERA ACCION — Leer archivos clave antes de implementar

Solicitar via SFTP antes de escribir ninguna linea de codigo:
- work_order_processor/models.py — WorkOrder, WorkOrderEntry, WorkOrderEntryLine.
- work_order_processor/services.py — generate_work_order_excel(), pipeline Vision.
- fleet/models.py — MachineAsset (campos codigo, marca_modelo).
- panel/templates/panel/work_orders/upload.html — formulario de subida actual.

### SEGUNDA ACCION — Paso 3: Via A formulario web estructurado

WorkOrderEntryFormView en panel/views.py:
- Hereda de WorkshopRequiredMixin, View.
- GET: renderiza formulario multi-bloque con un bloque inicial.
- POST: valida y persiste WorkOrder sintetico (status=DONE, source_pdf=null,
  total_pages=1, processed_pages=1) + WorkOrderEntry + N WorkOrderEntryLine.
- Tras persistir llama directamente a generate_work_order_excel() sin Celery.

WorkOrderEntryConfirmView en panel/views.py:
- Punto de confirmacion y persistencia sincrona.
- Renderiza formulario de confirmacion con todos los campos pre-rellenados.

Templates nuevos (Neonatos Puros):
- panel/operator/form_entry.html: formulario multi-bloque con autocompletado
  MachineAsset, time pickers redondeados a media hora, boton + Anadir bloque.
- panel/operator/confirm_entry.html: formulario de confirmacion con campos
  de alerta (fondo amarillo si vacios).

Autocompletado MachineAsset: endpoint JSON GET /panel/operator/assets/
que devuelve lista de {codigo, marca_modelo} de la empresa del usuario.
Vista WorkshopAssetAutocompleteView en panel/views.py.

### Estado de migraciones al inicio del hito (sin cambios desde sesion 002)

| App                    | Ultima migracion aplicada                              |
|------------------------|--------------------------------------------------------|
| fleet                  | 0002_maintenancelog_work_entry_line                    |
| work_order_processor   | 0002_remove_workorderentry_end_time_and_more           |
| ivr_config             | 0012_callflow_backup_name                              |
| panel                  | 0001_initial (AnalyticsProfile)                        |

### Estado de migraciones al inicio del hito

| App                    | Ultima migracion aplicada                              |
|------------------------|--------------------------------------------------------|
| fleet                  | 0002_maintenancelog_work_entry_line                    |
| work_order_processor   | 0002_remove_workorderentry_end_time_and_more           |
| ivr_config             | 0012_callflow_backup_name                              |
| panel                  | 0001_initial (AnalyticsProfile)                        |

### Archivos clave al inicio del hito

- `ivr_config/models.py` — CompanyUser.role a modificar (Paso 1).
- `panel/mixins.py` — OperatorRequiredMixin a crear (Paso 2).
- `panel/views.py` — nuevas vistas de operario (Pasos 2-5).
- `panel/forms.py` — extensión CompanyUserCreateForm (Paso 1).
- `work_order_processor/services.py` — reutilizado en Vía C (Paso 5).
- `work_order_processor/models.py` — WorkOrder.pdf_display_name property activa.
