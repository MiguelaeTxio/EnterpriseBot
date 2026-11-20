# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V11.md
# Anexo H11 — Albaranes a Clientes (albaranes de trabajo de las grúas)

---

## 1. Objetivo

Sustituir el albarán de trabajo de papel de las grúas («PARTE DE
PRODUCCIÓN» + «ALBARÁN» de Grúas Adolfo Álvarez / Grualdi / Transgrual)
por un albarán digital: la oficina lo prepara (a mano o con el planning
en Excel), se lo envía al gruista por WhatsApp, el gruista lo rellena en
su aplicación de fichaje con las horas de sus fichajes, firma él y firma
el cliente en la pantalla, y el PDF firmado se le entrega al cliente
automáticamente.

## 2. Decisiones de Miguel Ángel (S162, 20/11/2026, verbatim)

- **Dos orígenes:** *"tenemos que tener las dos opciones, porque habrá
  veces que se tenga que construir el gruista desde cero y otras veces
  se lo enviaremos desde la oficina."*
- **Entrega:** *"tendríamos que tener varios tipos de entrega. Entrega
  por WhatsApp, entrega por correo [...] mejor por correo. Lo
  enviaríamos por correo de forma automática."*
- **Casillas que faltaban en la lista:** horas mínimas y tonelaje.
- **Muestras:** los albaranes de papel que carga Juan para cotejar los
  fichajes (hr_calendar.AlbaranSheet, S149/S153).
- **Pipeline:** *"enviar el albarán relleno con el cliente, obra,
  máquina y gruista, que lo enviamos por WhatsApp. Ese albarán le llega
  al gruista, lo abre en su aplicación y él solamente tiene que
  rellenar, o incluso [...] quedar rellenado con los fichajes del
  gruista."*
- **Planning:** *"Carlos Núñez cargaría el planning con un Excel de
  dónde va a trabajar cada gruista, en qué obras va a trabajar."*
- **Obras:** *"cómo se definen las obras por clientes, con su
  ubicación, su número, el número de proyecto, etcétera."*
- **Vídeo de demostración** del proceso completo, con las pantallas del
  móvil y del panel, *"para que lo vean los jefes y que ellos tomen la
  decisión de implantarlo o no."*

## 3. Contexto técnico

- **El albarán de papel actual** (leído de los albaranes de muestra en
  BD, `AlbaranSheet.full_text`): EMPRESA, MÁQUINA, TONELADAS, nº de
  albarán; DATOS CLIENTE (nº pedido, fecha, cliente, teléfono,
  domicilio, localidad, N.I.F., provincia); SERVICIO GRÚA (lugar de
  trabajo, localidad, trabajo realizado, horas trabajadas, salida /
  desplazamiento, kilómetros, importe, conforme cliente con nombre y
  D.N.I.); MERCANCÍA TRANSPORTADA (carga, descarga, propietaria);
  OPERARIO / CONDUCTOR con su firma; y el PARTE DE PRODUCCIÓN (salida
  de base, llegada al trabajo, salida del trabajo, llegada a base,
  continuación del día anterior, vehículo en obra, observaciones).
- **Modelos:** `worksites.Client` (nuevo) y `worksites.Worksite`
  ampliada (migración worksites 0004); app `crane_albaranes`
  (`CraneAlbaran`, `PlanningImport`, migración 0001).
- **Horas desde el fichaje** (`crane_albaranes/services.clock_times`),
  sobre los fichajes por tipos del gruista: salida de base = entrada;
  llegada al trabajo = primer tramo que no es desplazamiento ni pausa;
  salida del trabajo = fin del último de esos tramos; llegada a base =
  salida; horas trabajadas = suma de esos tramos. Con la hora redondeada
  del parte (clock_rounding).
- **PDF** en el cubo, en `ALBARANES DE TRABAJO` del gruista (la misma
  carpeta que los de papel, S153), tipo `ALBARAN_TRABAJO`.
- **Correo:** buzón SMTP desde el `.env` (`EMAIL_HOST`, `EMAIL_PORT`,
  `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`,
  `DEFAULT_FROM_EMAIL`). Sin `EMAIL_HOST` no se envía y el albarán queda
  en «Entrega fallida» con el motivo.
- **WhatsApp al gruista:** plantilla `crane_albaran_notice` (variables
  {{1}} gruista, {{2}} número, {{3}} fecha y hora, {{4}} obra y
  cliente, {{5}} máquina, {{6}} final del enlace del botón,
  `/fichaje/albaranes/{{6}}`); dentro de la ventana de 24 h sale como
  texto libre. La plantilla no está creada ni aprobada.

## 4. Hoja de ruta (al abrir el hito, S162)

1. Plantilla de WhatsApp `crane_albaran_notice`: Miguel Ángel aprueba
   el texto, se crea en Twilio y se espera la aprobación de Meta.
2. Buzón de salida del correo: decidir la cuenta y ponerla en el `.env`
   del servidor; prueba de entrega real a un correo de prueba.
3. Entrega por WhatsApp al cliente (plantilla con el PDF).
4. Decisión de los jefes tras el vídeo; si se implanta, prueba real con
   un gruista y una obra.

## 5. COMPLETADAS EN S162 (sesión invasora, 20/11/2026, PEE PC)

Sesión invasora en paralelo con S156 (H31 EN PROGRESO, que no se
mueve). Hito abierto en esta sesión (Caso C del enrutador: H11 ya
figuraba en la tabla y en el documento maestro; el anexo no existía).

- `58f2fab` — Clientes, obras ampliadas y modelo del albarán de grúa
  (migraciones worksites 0004 y crane_albaranes 0001, aplicadas en
  producción el 20/11 a las 06:15 UTC, comprobado en `django_migrations`).
- `94c2aa3` — Página «Grúas» (misma puerta que Documentación) con
  Albaranes, Obras y Clientes en el formato único de listados; carga
  del planning en Excel con plantilla; envío por WhatsApp; horas de los
  fichajes; reenvío; exportación.
- `92feb7b` — El gruista dentro del fichaje: «Mis albaranes», el
  albarán con sus horas, «Hacer un albarán nuevo» desde cero, firmas en
  pantalla, PDF, cubo y correo al cliente; la tarjeta «Mis albaranes» en
  la página de fichaje.
- `5ff23ec` — Sin el botón «Solo los filtrados» duplicado; estados en
  dos columnas.
- Vídeo de demostración (3:40) grabado en un servidor de prueba con
  datos ficticios; el WhatsApp y la bandeja del cliente son
  recreaciones rotuladas como tales, y en él la búsqueda de coordenadas
  de Google y el envío por Twilio estaban simulados (sin red).
