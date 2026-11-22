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
- ✅ Ver documento · ✅ descargar con su nombre desde la fila (S163)
- ✅ Actualizar (subir nueva versión) · ✅ Historial de un tipo (S163)
- ✅ Cambiar tipo · ✅ Separar páginas · ✅ Eliminar (a la papelera) (S163)
- ✅ Subir documentos y su formulario en Acciones (S163)
- ⬜ Crear un tipo documental al vuelo
- ⬜ Descargar varios (elegir) y papelera de descargas
- ⬜ Selección de documentos: vista previa, PDF único, ZIP, enviar por correo
- ✅ Dosieres (S163): plantillas (crear, modificar, borrar) en Documentos ›
  Dosieres; dosier de los documentos marcados (Personal/Centros de gasto ›
  Documentos); dosier de los marcados con plantilla, todo junto, para
  descargar o en un correo, y «¿A quién le falta algo?» (› General)

## Personal
- ✅ Ficha sin acordeones: datos, contacto, empresa y puesto, caducidades,
  observaciones, periodos de contratación, accesorios; Modificar en el sitio
- ✅ Foto de perfil (subir)
- ✅ (S163) Foto para plataformas (entera o recuadro) · sacar la foto de
  un documento · girar · modo automático · cola de fotos (General) ·
  elegir una imagen como foto («Esta fila» en Documentos)
- ✅ (S163) Alta de trabajador (guiada por documentos o a mano; reactiva si está de baja) · baja · deshacer baja · recontratar
- ✅ (S163) Exportar con plantillas de columnas (guardar, aplicar, borrar; en todas las vistas) y separar en hojas por una columna (empresa, sección...) y por los grupos de selección marcados
- ✅ (S163) Requisitos de documentación: añadir/quitar a los marcados
  (Personal y Centros de gasto); crear, modificar, activar, borrar y
  categoría de un tipo (Documentos › Requisitos)
- ✅ (S163) Contrato revisado (correcto, deshacer, anular) en «Del trabajador»
- ✅ (S163) Avisar de una circular a los marcados: WhatsApp o correos (.eml)
- ✅ (S163) Acceso al panel (preparar, crear o enlazar, reenviar el alta)
- ✅ (S163) Empresa, horario, sección y base en masa (sección de uno: marcarlo en Horarios)
- ✅ (S163) Bajas médicas: añadir a la persona abierta, dar el alta y borrar (Personal › Salud)
- ✅ (S163) Preparar Docuten (General › Acciones: circular con firma, obra, los tres archivos)
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
- ✅ (S163) Trabajadores que fichan, recordatorios, ficha desde, tipo de
  fichaje de cada uno, sección desde una fecha (Personal › Horarios o
  Fichajes › Acciones) · ⬜ tope de horas extra, ajustes de sección
- ✅ (S163) Tipos de fichaje: crear y modificar (Personal › Tipos de fichaje)
- ✅ (S163) Horarios: crear, modificar, borrar (Personal › Lista de
  horarios), asignar o quitar a los marcados; vista Horarios con el que
  le toca y de dónde le viene

## Vacaciones y ausencias
- ⬜ Saldo, detalle, registrar, editar/borrar periodo, ausencia (crear,
  borrar), asignar sección, ajustes, días libres, reglas, importar

## Pedir documentos y solicitudes
- ✅ (S163) Pedir documentos (pedir, cancelar; cancelar peticiones marcadas) · ⬜ pedir al trabajador desde avisos
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
- ⬜ Alta de máquina · ✅ requisito en masa (S163) · ✅ grupos de selección
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
