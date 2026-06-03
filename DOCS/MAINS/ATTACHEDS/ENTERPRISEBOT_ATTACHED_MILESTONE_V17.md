# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V17.md

# Anexo de Hito V17 -- Albaranes y Ordenes de Trabajo ASISTENCIA
# Proyecto: EnterpriseBot
# Fecha de creacion: 2026-05-29

---

## 1. Vision General del Hito

La seccion de ASISTENCIA necesita digitalizar el flujo completo de trabajo
desde que se acepta un presupuesto (o se genera una orden directa) hasta que
el operario entrega el servicio al cliente y este firma el albaran. El objetivo
es eliminar el papel, reducir errores de transcripcion y dejar el albaran
listo para facturacion con un solo clic desde el panel de administracion.

**Vias de entrada:**
1. Presupuesto aceptado -> se convierte automaticamente en Orden de Trabajo.
2. Orden de Trabajo nueva directa -> sin presupuesto previo.

**Flujo de salida:**
El albaran digital firmado queda en el sistema listo para revision ADMIN
y exportacion a facturacion.

---

## 2. Arquitectura Tecnica -- DISENO REVISADO EN S001

### 2.1. Decisiones de diseno tomadas en S001

**Arquitectura de N vehiculos por servicio:**
Un servicio puede requerir multiples vehiculos simultaneos (grua, coche taller,
plataforma, etc.). Cada vehiculo genera su propio albaran individual. El modelo
original contemplaba unicamente dos fases/operarios -- redisenado para N unidades.

**Estrategia offline:**
La PWA con Service Worker fue descartada. Solucion adoptada: app Android nativa
(AlbaranApp) distribuida desde la app web Django, con persistencia offline via
SharedPreferences y sincronizacion al recuperar cobertura.

**Prototipo AlbaranApp:**
App Android nativa compilada y desplegada. Package: com.miguelaetxio.albaran.
Distribuida desde /panel/budgets/albaran-demo/. Codigo fuente en GitHub repo AlbaranApp.

**Campos adicionales identificados desde PDF Allianz Partners (pendiente validacion):**
- codigo_proveedor, num_poliza, tiempo_llegada, tipo_servicio
- averia, cod_averia, reparacion_in_situ (bool)
- nombre_asegurado, segundo_servicio (bool), gestion_propia_grua (bool)
- accidente (bool), comentarios (cobertura autorizada por la aseguradora)
- diferido (bool -- pendiente confirmar si es sinonimo de is_overnight)
- rueda_gemela (bool), num_pasajeros, anchura, cp_recogida

### 2.2. Modelos Django -- Arquitectura definitiva

WorkOrderAssistance -- Expediente del servicio completo.
  FK a Budget (nullable), Insurer, CompanyUser (gestor), Base.
  Campos de servicio: expediente, num_poliza, codigo_proveedor, tiempo_llegada,
  tipo_servicio, averia, cod_averia, reparacion_in_situ, nombre_asegurado,
  segundo_servicio, gestion_propia_grua, accidente, comentarios, diferido.
  Campos de vehiculo: vehicle_plate, vehicle_brand, vehicle_model, vehicle_color,
  vehicle_height, vehicle_length, vehicle_width, vehicle_pma, rueda_gemela, num_pasajeros.
  Campos de localizacion: vehicle_locality, vehicle_province, pickup_location, cp_recogida.
  status: PENDING / IN_PROGRESS / COMPLETED / INVOICED.
  service_date, created_at, updated_at.

WorkOrderAssistanceUnit -- Un albaran individual por vehiculo que asiste.
  FK a WorkOrderAssistance.
  unit_number -- ordinal (1,2,3...). Albaran impreso: work_order_number-unit_number.
  FK a CompanyUser (operario), machine (matricula), FK nullable a Base.
  is_overnight (bool).
  Datos de servicio: km_phase1, km_phase2, horas espera, horas rescate, departure_fee.
  status: PENDING / IN_PROGRESS / COMPLETED.
  synced_at (DateTimeField nullable) -- momento de sincronizacion offline.
  created_at, updated_at.

WorkOrderAssistanceSignature -- Firma digital del cliente.
  OneToOneField a WorkOrderAssistanceUnit.
  signature_data (TextField, base64 PNG, app Android).
  signed_at (DateTimeField auto).
  signer_name (CharField, opcional).
  signed_offline (bool) -- firma capturada sin cobertura.

WorkOrderAssistanceIncidence -- Delta de incidencias por unidad.
  FK a WorkOrderAssistanceUnit.
  Todos los campos de servicio de la unidad, todos nullable/blank.
  Solo se rellena lo que cambio respecto al albaran original.
  memo (TextField) -- memoriamdum de justificacion obligatorio.
  recorded_by FK a CompanyUser.
  recorded_at (DateTimeField auto).

### 2.3. Grafo de modelos

WorkOrderAssistance (expediente)
    WorkOrderAssistanceUnit x N (un albaran por vehiculo)
        WorkOrderAssistanceSignature (1:1, firma del conductor)
        WorkOrderAssistanceIncidence (0:1, delta de incidencias + memo)

---

## 3. Hoja de Ruta

### Paso 1 -- Modelos y migracion
- Estado: PENDIENTE
- PREREQUISITO: validar con responsables los campos del PDF Allianz antes de makemigrations.
- Confirmar si diferido es sinonimo de is_overnight o campo independiente.
- Crear los cuatro modelos en budgets/models.py.
- Ejecutar makemigrations + migrate.

### Paso 2 -- Vistas y URLs
- Estado: PENDIENTE
- WorkOrderCreateFromBudgetView, WorkOrderCreateDirectView,
  WorkOrderAlbaranView, WorkOrderDetailView, WorkOrderPdfView.

### Paso 3 -- Template movil operario
- Estado: PENDIENTE
- albaran_operario.html: mobile-first, integracion con app Android nativa.

### Paso 4 -- Notificacion WhatsApp al operario
- Estado: PENDIENTE

### Paso 5 -- Exportacion PDF
- Estado: PENDIENTE
- albaran_pdf.html + WorkOrderPdfView con weasyprint.

### Paso 6 -- Boton en BudgetResultView
- Estado: PENDIENTE
- Boton Generar orden de trabajo en result.html cuando budget.status == ACCEPTED.

---

## 4. Registro de Sesiones

Sesion | Fecha      | Pasos trabajados | Resumen
S001   | 2026-06-02 | Ninguno (diseno) | Hito iniciado. Rediseno completo arquitectura modelos: N vehiculos por servicio, estrategia offline Android nativa, identificacion campos adicionales PDF Allianz. Incidencias paralelas: fix nocturno/festivo wizard, fix redirect operario, prototipo AlbaranApp Android compilado y desplegado, 6 skills Android creadas, PEE y PICP actualizados.

---

## 5. Hoja de Ruta para la Siguiente Sesion (S002)

PREREQUISITO OBLIGATORIO antes de arrancar el Paso 1:
Validar con los responsables los campos del PDF de Allianz identificados en S001,
especialmente el campo diferido (posible sinonimo de is_overnight). Esta validacion
debe completarse antes de ejecutar makemigrations para evitar migraciones adicionales.

Una vez validados los campos, arrancar el Paso 1 en este orden estricto:

1. Solicitar el archivo budgets/models.py completo para obtener anclas reales.
2. Anadir los cuatro modelos nuevos al final del archivo mediante PMA:
   WorkOrderAssistance, WorkOrderAssistanceUnit,
   WorkOrderAssistanceSignature, WorkOrderAssistanceIncidence.
   Seguir exactamente la arquitectura de la seccion 2.2 de este anexo.
3. Ejecutar makemigrations y migrate. Verificar que no hay errores.
4. Registrar las migraciones generadas en el PROJECT_DIRECTORY.
5. Continuar con el Paso 2 -- Vistas y URLs.
