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
- ✅ (S163) EPIs: entregar (a los marcados o a la persona abierta, con lotes), lotes (crear, modificar, borrar), historial de un EPI, documento de entrega, fichas técnicas (Catálogo de EPIs)
- ⬜ Parte del día (detalle de jornada)

## Circulares
- ✅ Ver las entregadas (vista Circulares)
- ✅ Plantillas de circular (vista), crear nueva, editar contenido, importar
  Word/PDF, descargar PDF/Word, generar para una persona, con/sin firma
  certificada

## Fichajes y horarios
- ✅ (S163) Fichajes: detalle y jornadas del trabajador (Personal › Jornadas, con el periodo del filtro; vistas Jornadas, Calendario de cuatro años y Correcciones), editar la jornada, añadir o corregir la pausa de comida (con la comida de su horario), intercalar un tipo (viendo los tramos), anular el día, visado, pendiente de revisar, kilómetros, bolsa de horas, historial de correcciones, exportar el registro de jornada con plantillas de columnas (las mismas que la antigua: elegir, guardar, modificar, borrar, por defecto, de la empresa; Excel de la persona abierta o de las marcadas: trabajadores, jornadas, pulsaciones, correcciones; membrete con uno solo)
- ✅ (S163) Albaranes del fichaje: cargar (de la persona abierta o de varios, carpeta o archivos, lectura en segundo plano), estado, cargas recientes («Ver»), y en Jornadas cada albarán del día (ver el archivo) y la marca «Comparado/Corregido por IA» o «por el parte»
- ✅ (S163) Informe del alta en el fichaje (Personal › Alta en el fichaje: resumen por situación que filtra, sección, buscador común) y su exportación a Excel, PDF o HTML con plantillas de columnas (las mismas que la antigua)
- ✅ (S163) Trabajadores que fichan, recordatorios, ficha desde, tipo de
  fichaje de cada uno, sección desde una fecha (Personal › Horarios o
  Fichajes › Acciones) · ✅ (S163) tope de horas extra, recordatorios de la empresa, ajustes de cada sección (ficha, por tipos, casilla de comida) y visado en masa de los marcados (Personal › Acciones)
- ✅ (S163) Tipos de fichaje: crear y modificar (Personal › Tipos de fichaje)
- ✅ (S163) Horarios: crear, modificar, borrar (Personal › Lista de
  horarios), asignar o quitar a los marcados; vista Horarios con el que
  le toca y de dónde le viene

## Vacaciones y ausencias
- ✅ (S163) Personal › Saldo de vacaciones (año y sección como botones, filtros comunes, orden): registrar a los marcados, sección desde una fecha, importar saldos (plantilla y carga), reglas por sección (crear, borrar) y tipos de ausencia (crear, modificar, activar/desactivar)
- ✅ (S163) Personal › Desglose de vacaciones (persona abierta, por año): tramos, periodos (cambiar fechas, borrar), ausencias (registrar con horas, borrar), ajustes, días libres por horas acumuladas e historial de secciones (borrar)

## Pedir documentos y solicitudes
- ✅ (S163) Pedir documentos (pedir, cancelar; cancelar peticiones marcadas) · ⬜ pedir al trabajador desde avisos
- ✅ (S163) Solicitudes de los trabajadores: «Gestionar» de cada fila (en Acciones: aprobar, denegar, entregar un documento subido o de su ficha, responder, justificante, deshacer), las marcadas (aprobar, denegar, justificante válido) y sus archivos

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
- ✅ (S163) Alta de máquina (por documentos o a mano; reactiva si está de baja) · baja/reactivar/borrar en masa · ✅ requisito en masa · ✅ grupos de selección
- ✅ (S163) Revisiones: nueva, borrar, estado del plan («Del centro de gasto») · ✅ revisiones que faltan · ⬜ plan en masa, guardar fila
- ✅ (S163) Lecturas de contador: nueva, borrar (vista Lecturas)
- ✅ (S163) Libro historial: generar, externo («Del centro de gasto»)
- ✅ (S163) Taller: listados de partes, averías y libro (vistas Taller, Averías y Libro historial; Excel con Exportar), libros en ZIP (Documentos › Descargar los marcados), revisiones del libro (escaneo, reconstruir, a firma, quitar) y revisiones que faltan («Del centro de gasto» y página aparte)
- ⬜ Partes de trabajo del taller: subir el escaneo, modificar el parte y
  sus líneas (guardar, insertar, ordenar, recuperar, borrar), fotos de
  tareas, revisión de partes, duplicados, borradores, exportar (también
  con plantillas y la del administrador), historial, periodos de trabajo
  (cerrar, bloquear)
- ⬜ Avisos por máquina (reglas de cada centro de gasto) y analítica de la
  máquina
- ✅ (S163) Especificaciones: exportar (Exportar común, como todas las vistas)
- ✅ (S163) Repostajes: unidad, preguntar (vehículo y, en Personal, chófer), contador; exportar con plantillas (Exportar y Columnas comunes)
- ✅ (S163) Accesorios de elevación: alta (con certificado), estado (retirar/reactivar), revisión, entrega, devolución y otro certificado
  (uno y en masa), certificado, tipos y modelos
- ✅ (S163) Equipos: nuevo (máquina abierta + personas), terminar y borrar los marcados; exportar con el Exportar común

## No recogido hasta ahora (repaso S163, 23/11)
- ⬜ Puestos de trabajo: gestionar, crear, modificar, activar/borrar en
  masa, categoría por tipo; puesto en masa a los marcados (Personal)
- ⬜ Obras: lista y borrar
- ⬜ Usuarios del panel: lista, crear, modificar, borrar en masa, quitar
  de una sección; secciones (lista, crear, modificar, rol por defecto)
- ⬜ Ajustes de la empresa
- ⬜ Plantillas de exportación de partes (lista, crear, modificar, borrar)

