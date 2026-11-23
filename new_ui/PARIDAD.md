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

## Diseño acordado (S163, 23/11) — manda sobre lo de abajo

Miguel Ángel, tras ver el panel por apartados: las pestañas de arriba no
son «otra vista» cada una; son **temas**. Lo que se *crea y configura* para
toda la empresa va en **Empresa** (antes «Documentos», la clave sigue
siendo `doc`); lo que se *hace a* trabajadores o máquinas va en
**Personal** y **Centros de gasto**, como acciones. Ninguna vista que en
realidad sea una acción (fuera «Horarios», «Alta en el fichaje»...).
Permisos, aparte.

**Regla del tema (Personal y Centros de gasto).** Filtros y grupos de
selección, como están, para todo. La lista de abajo es siempre la de
trabajadores (o máquinas). El tema elegido arriba decide tres cosas:
1. las columnas de la lista (Fichaje: horario, ficha, recordatorios,
   tipos de fichaje, alta en el fichaje...);
2. las acciones del panel, para uno o para los marcados (sin pestañas
   propias en el panel);
3. a dónde lleva el **clic izquierdo** en un trabajador: General → su
   Ficha; Fichaje → su control de fichaje (pestaña *Fichajes*: todos sus
   fichajes, las correcciones con un filtro; pestaña *Calendario*: por
   meses, pulsar un día abre la jornada para cambiarla, como en la
   antigua); Documentación → sus documentos; Vacaciones → su desglose;
   Bajas → sus bajas; EPIs → sus entregas; Comunicaciones → lo que se le
   ha pedido y las circulares recibidas. El botón derecho sigue siendo el
   menú propio de la app.

**Empresa** (cerrada el 23/11; se retocará al usarla):
1. Documentación: Requisitos de documentación, Avisos, Dosieres.
2. Circulares: crear y modificar plantillas; enviadas y quién las leyó
   (el envío, desde Personal).
3. Firmas.
4. Seguros.
5. Fichaje: Tipos de fichaje, Horarios (crear y modificar), Ajustes de
   fichaje de la empresa.
6. Vacaciones: reglas por sección y tipos de ausencia.
7. EPIs: catálogo (lotes y fichas técnicas).

Fuera: Bandeja de entrada (los documentos entran por el agente de H28 y
desde cada ficha) y Calendario (eran las ausencias, repetidas de
Personal). Se quedan en la interfaz antigua, sin pasar de momento:
Usuarios del panel y secciones y Ajustes de la empresa (Administración),
Plantillas de exportación de partes (Taller), Puestos de trabajo y Obras.

**Personal** (lo ya decidido; el resto de temas, pendiente de repasar
uno a uno):
- Fichaje: asignar horario, tipos de fichaje, recordatorios, ficha o no
  ficha, alta en el fichaje (crear usuario, reenviar), visar días,
  registro de jornada, albaranes.
- Comunicaciones (todo lo que va por WhatsApp, un mismo «Enviar por
  WhatsApp»): pedir documentos y enviar una circular.
- Nóminas, tema aparte (permiso especial).
- Documentación: poner o quitar requisitos (varios a la vez) y dosier de
  los marcados eligiendo qué lleva. Lo mismo en Centros de gasto (pedir
  documentos no: allí los ponemos nosotros).

Hilera de Personal acordada (23/11): General · Documentación ·
Comunicaciones · Fichaje · Vacaciones · Bajas y ausencias · Partes ·
Repostajes · Nóminas · EPIs · Horas y pagos (Partes y Repostajes,
separados: son dos cosas distintas). Cada tema, pendiente de
repasar uno a uno.

**Horas y pagos** (función nueva, 23/11; hoy solo existe para los partes
digitales de Taller y Taller Huelva, en un Excel con el precio a mano):
- Horas extra. Lo que se paga lo decide el supervisor: qué tipos de hora
  (trabajo efectivo, presencia, desplazamiento y cualquier otro tipo).
- Precio por trabajador y por tipo de hora; festivo y domingo, con el
  precio que indique el supervisor.
- Horas de los partes digitales para quien los hace y de los fichajes
  para todos los demás.
- Lista: totales por trabajador del periodo a liquidar; clic → su cómputo
  del periodo (día a día, de dónde sale cada hora, total a pagar).
- La bolsa de horas se gestiona aquí.
- Un periodo liquidado queda bloqueado.

**Lista y ficha (23/11).** La lista de trabajadores es para hacer cosas
a muchos a la vez; todo lo de uno solo, en su ficha. La ficha tiene sus
propias pestañas con los mismos temas (Datos, Documentación,
Comunicaciones, Fichaje, Vacaciones, Bajas y ausencias, Partes,
Repostajes, Nóminas, EPIs, Horas y pagos) y las mismas acciones, ya
solo para él. El clic en un trabajador abre su ficha en el tema que
estaba elegido arriba (General → Datos). Columnas de cada tema:
configurables, cada supervisor las suyas.
- Documentación (lista, con los marcados): solo requisitos de
  documentación y dosier. Sus documentos (ver, añadir, actualizar,
  separar, cambiar tipo, papelera), en su ficha.
- Comunicaciones: circular, pedir documentos y Docuten. Siempre con
  plantillas: nada de mensajes de texto libre (si hace falta uno, el
  supervisor desde su móvil).
- General (lista, con los marcados): baja o reactivar, empresa, base,
  volver a sacar la foto; nuevo: alta de un trabajador.
- Fichaje (23/11). Lista, con los marcados: asignar horario, tipos de
  fichaje, recordatorios, ficha o no ficha, alta en el fichaje (usuario
  y contraseña o reenviar el alta), visar días con incidencias, registro
  de jornada en Excel (con plantillas de columnas) y cargar albaranes de
  varios. Columnas para elegir: horario, ficha, recordatorios, tipos,
  usuario, alta enviada, último fichaje, días sin visar. En su ficha:
  Fichajes (lista con periodo y filtro «solo corregidos»; corregir,
  anular, revisar, con motivos) y Calendario (el mes; un día abre la
  jornada: comida, insertar, km, números de albarán), más lo mismo que
  en la lista solo para él (registro con membrete, sus albaranes). La
  bolsa de horas pasa a Horas y pagos.
- Vacaciones (23/11). Días en tres niveles: **empresa** (Empresa ›
  Vacaciones), **grupo de selección** (las secciones reales; la sección
  es herencia del SIME y no cuenta) e **individual**. Manda el más
  concreto: si el trabajador no tiene los suyos, los de su grupo; si el
  grupo no tiene, los de la empresa. Si está en dos grupos con días
  distintos y no tiene los suyos, los de la empresa. Los días de la
  empresa y de cada grupo se ponen en Empresa › Vacaciones. Lista, con los marcados: registrar
  vacaciones, poner días propios (o quitarlos), importar saldos de
  partida.
  Columnas para elegir: días que le tocan (y de dónde: propios,
  grupo o empresa), disfrutados, pendientes, del año anterior, próximo
  periodo. En su ficha: su desglose (periodos, cambiar o borrar; ajustes),
  su saldo explicado y lo mismo solo para él. Desaparecen las vistas
  «Vacaciones» y «Saldo» (pasan a columnas) y «Desglose» (a su ficha).
- Bajas y ausencias (23/11). Lista, con los marcados: nueva baja médica
  (inicio, motivo, parte de baja) y registrar una ausencia (del… al…,
  tipo; los tipos, en Empresa › Vacaciones). Columnas para elegir: de
  baja ahora, desde cuándo, días de baja en el año, próxima ausencia. En
  su ficha: sus bajas (dar el alta con fecha y parte, o borrar) y sus
  ausencias (cambiar o borrar), y lo mismo solo para él. Las vistas
  «Salud» y «Ausencias» desaparecen (a su ficha y a columnas).

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

