# Nueva interfaz — paridad de funciones con la antigua

S163 (sesión invasora de UX). Miguel Ángel: *"Queremos una interfaz nueva,
pero con todas las funcionalidades de la anterior. [...] el primer objetivo
es no perder absolutamente ninguna funcionalidad."*

Lista de TODO lo que se puede hacer hoy en la interfaz antigua (fichas de
persona y de centro de gasto y pestañas de Documentación), sacada de sus
rutas (`panel/urls.py`). Cada función se pasa a la nueva copiando su código
con otro nombre (`new_ui/`, regla de separación en la directriz 4.27 del
documento maestro) y se pone en su sitio:

- **Entrada** (arriba): «Qué ver» (la vista), Buscar y filtrar, Filtros de la
  vista, Columnas; Selección (marcados y grupos); Acciones (De la vista ·
  Esta fila · Del trabajador/centro de gasto · Exportar).
- **Salida** (abajo): el listado de la vista y los seleccionados. Sin nada
  que elegir.

Estado: ✅ hecho y comprobado en producción · ⬜ pendiente.

## Comunes a las vistas
- ✅ Listados con filtros comunes, periodo rápido y fechas, filtros propios,
  columnas, orden múltiple, selección, grupos de selección, exportar.
- ✅ Botón derecho propio sobre persona/máquina/fila.

## Documentos de una persona o máquina
- ✅ Ver documento · ⬜ descargar con su nombre desde la fila
- ⬜ Actualizar (subir nueva versión) · ⬜ Historial de un tipo
- ⬜ Cambiar tipo · ⬜ Separar páginas · ⬜ Eliminar (a la papelera)
- ✅ Subir documentos (ruta copiada) · ⬜ su formulario en Acciones
- ⬜ Crear un tipo documental al vuelo
- ⬜ Descargar varios (elegir) y papelera de descargas
- ⬜ Selección de documentos: vista previa, PDF único, ZIP, enviar por correo
- ⬜ Dosieres: plantillas (crear, editar, borrar), aplicar a una persona o
  máquina, comprobar los que faltan en masa, enviar lote por correo

## Personal
- ✅ Ficha sin acordeones: datos, contacto, empresa y puesto, caducidades,
  observaciones, periodos de contratación, accesorios; Modificar en el sitio
- ✅ Foto de perfil (subir)
- ⬜ Foto para plataformas · ⬜ sacar la foto del DNI · ⬜ girar · ⬜ cola de
  fotos · ⬜ elegir un documento como foto
- ⬜ Alta de trabajador (con extracción del DNI) · ⬜ baja · ⬜ reactivar
- ⬜ Exportar Personal con plantillas (guardar/borrar plantillas)
- ⬜ Requisitos de documentación: asignar en masa, puestos (crear, editar,
  activar, borrar, categoría)
- ⬜ Contrato revisado
- ⬜ Avisar / notificar (uno, en masa, WhatsApp)
- ⬜ Acceso al panel (vista previa, crear, reenviar)
- ⬜ Empresa, horario, sección y base en masa · ⬜ sección de uno
- ⬜ Bajas médicas
- ⬜ Preparar Docuten (ruta copiada; falta su sitio en Acciones)
- ⬜ EPIs: entrega por lotes, plantillas de lote, historial, ficha técnica
- ⬜ Parte del día (detalle de jornada)

## Circulares
- ✅ Ver las entregadas (vista Circulares)
- ✅ Plantillas de circular (vista), crear nueva, editar contenido, importar
  Word/PDF, descargar PDF/Word, generar para una persona, con/sin firma
  certificada

## Fichajes y horarios
- ⬜ Fichajes: detalle, jornadas del trabajador, acciones de jornada, bolsa
  de horas, kilómetros, visado, pendiente, corregir, exportar
- ⬜ Albaranes del fichaje (cargas, archivos, estado, ver)
- ⬜ Informe de alta y su exportación
- ⬜ Ajustes: trabajadores que fichan, recordatorios, tope de horas extra,
  sección, **tipos de fichaje**
- ⬜ Horarios: **crear**, lista, **asignar**, por sección

## Vacaciones y ausencias
- ⬜ Saldo, detalle, registrar, editar/borrar periodo, ausencia (crear,
  borrar), asignar sección, ajustes, días libres, reglas, importar

## Pedir documentos y solicitudes
- ⬜ Pedir documentos (pedir, cancelar) · ⬜ pedir al trabajador desde avisos
- ⬜ Solicitudes de los trabajadores (detalle, acciones, en masa)

## Avisos
- ⬜ Avisos de documentos: reglas por requisito, destinatarios, WhatsApp,
  pendientes, subir desde el aviso, cita, antelación de revisiones

## Bandeja de entrada
- ⬜ Subir, estado, reclasificar

## Nóminas
- ⬜ Nueva remesa, subir, leer, acciones, exportar, descargar

## Firmas y seguros
- ⬜ Firmas: guardar, borrar, imagen, certificado, generar firmados, lotes
  (estado, cancelar, descargar), agentes de firma, descargas, acciones
- ⬜ Seguros: lista, libro mayor (subir, empresa), nuevo, acciones, exportar

## Centros de gasto
- ✅ Ficha técnica, Modificar, foto, exportar tarjeta (5 formatos)
- ✅ QR: código, descarga, observaciones, fotos y vídeos, contraseña editor
- ⬜ Alta de máquina, requisito en masa, grupos (✅ grupos de selección)
- ⬜ Revisiones: nueva, borrar, plan en masa, guardar fila, exportar,
  revisiones que faltan
- ⬜ Lecturas de contador: nueva, borrar
- ⬜ Libro historial: generar, externo
- ⬜ Taller: partes, averías, libros (ZIP), revisiones (escaneo,
  reconstruir, a firma, quitar) y sus Excel
- ⬜ Especificaciones: exportar
- ⬜ Repostajes: unidad, preguntar, contador, exportar con plantillas
- ⬜ Accesorios de elevación: alta, estado, revisión, entrega y devolución
  (uno y en masa), certificado, tipos y modelos
- ⬜ Equipos: nuevo, acciones, exportar
