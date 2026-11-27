# Disposición PRODUCCIÓN — ficha para la Chrome Web Store

Paquete: `disposicion_produccion_<versión>.zip` (manifest.json, popup.html,
popup.js e icons/ de la carpeta `chrome_production_layout`; esta carpeta
`store/` no va dentro).

## Pestaña «Ficha de Play Store» / «Store listing»

- **Nombre:** Disposición PRODUCCIÓN (sale del manifest)
- **Resumen:** Guarda y vuelve a abrir el grupo de pestañas PRODUCCIÓN con
  sus vistas divididas. (sale del manifest)
- **Descripción:**

  Guarda un grupo de pestañas de Chrome tal como lo tienes montado —el
  orden de las pestañas, su nombre, su color y qué pares van en vista
  dividida— y vuelve a abrirlo igual con un clic.

  Cómo se usa:
  1. Monta el grupo a mano una vez y pulsa «Guardar disposición actual».
  2. Cada mañana, pulsa «Abrir PRODUCCIÓN»: se abren las pestañas, se
     agrupan y cada par vuelve a su vista dividida.

  Si el grupo ya está abierto en la ventana, no lo duplica. La disposición
  se guarda en el almacenamiento sincronizado de tu cuenta de Chrome, así
  que sirve en cualquier equipo con la misma cuenta.

- **Categoría:** Productividad / Herramientas
- **Idioma:** Español
- **Icono de la tienda:** icons/icon128.png (va en el paquete)
- **Captura:** store/captura_1280x800.png

## Pestaña «Prácticas de privacidad»

- **Propósito único:** Guardar la disposición de un grupo de pestañas de
  Chrome (pestañas, orden y vistas divididas) y volver a abrirla.
- **Justificación de `tabs`:** Leer las direcciones y el orden de las
  pestañas del grupo para guardarlas, y crearlas de nuevo al abrir la
  disposición.
- **Justificación de `tabGroups`:** Encontrar el grupo por su nombre,
  crearlo y ponerle su nombre y color.
- **Justificación de `storage`:** Guardar la disposición en el
  almacenamiento sincronizado de Chrome del propio usuario.
- **Justificación de `identity` e `identity.email`:** Saber si hay una
  cuenta con la sesión iniciada en Chrome: sin sesión, la disposición no
  se abre. No se lee ni se envía nada más de la cuenta.
- **Justificación de `browsingData`:** Al cerrar la sesión de Chrome (o
  si Chrome arranca sin sesión), borrar las cookies y los datos de
  sesión de los sitios del perfil, para que las cuentas abiertas en
  otros servicios no queden accesibles. No borra historial, contraseñas
  ni marcadores.
- **¿Código remoto?:** No.
- **Uso de datos:** guarda «Actividad web» (las direcciones de las
  pestañas del grupo) solo en el almacenamiento de Chrome del propio
  usuario; no se envía a ningún servidor ni a terceros. Marcar las tres
  certificaciones (no se venden, no se usan para fines ajenos al
  propósito único, no se usan para solvencia).

## Pestaña «Distribución»

- **Visibilidad:** No listada (solo con el enlace).
- **Pago:** Gratis.
- **Regiones:** todas, o solo España.
