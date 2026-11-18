// Popup of the PRODUCCION layout extension (S152).
// ---
// Ventana de la extensión: guarda la disposición del grupo y la vuelve a
// abrir con un clic; activa o desactiva que se abra sola al arrancar
// Chrome.

import {
  getAutoOpen, openLayout, readLayout, saveLayout, setAutoOpen,
} from "./layout.js";

const groupInput = document.getElementById("group");
const savedLine = document.getElementById("saved");
const statusLine = document.getElementById("status");
const autoOpenBox = document.getElementById("autoOpen");

function show(result) {
  statusLine.textContent = result.text;
  statusLine.className = result.ok ? "" : "error";
}

async function refreshSaved() {
  autoOpenBox.checked = await getAutoOpen();
  const layout = await readLayout();
  if (!layout) {
    savedLine.textContent = "Todavía no hay ninguna disposición guardada.";
    return;
  }
  groupInput.value = layout.title;
  const splits = layout.tabs.filter((t) => t.splitWithNext).length;
  savedLine.textContent =
    `Guardada el ${new Date(layout.savedAt).toLocaleString("es-ES")}: ` +
    `${layout.tabs.length} pestañas, ${splits} vistas divididas.`;
}

async function currentWindowId() {
  return (await chrome.windows.getCurrent()).id;
}

document.getElementById("save").addEventListener("click", async () => {
  try {
    show(await saveLayout(await currentWindowId(), groupInput.value));
    await refreshSaved();
  } catch (e) {
    show({ ok: false, text: `Error al guardar: ${e.message}` });
  }
});

document.getElementById("open").addEventListener("click", async () => {
  try {
    show({ ok: true, text: "Abriendo…" });
    show(await openLayout(await currentWindowId()));
  } catch (e) {
    show({ ok: false, text: `Error al abrir: ${e.message}` });
  }
});

autoOpenBox.addEventListener("change", async () => {
  await setAutoOpen(autoOpenBox.checked);
  show({ ok: true, text: autoOpenBox.checked
    ? "Se abrirá sola al arrancar Chrome."
    : "Ya no se abrirá sola al arrancar Chrome." });
});

refreshSaved();
