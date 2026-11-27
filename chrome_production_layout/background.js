// Opens the PRODUCCION layout when Chrome starts (S152).
// ---
// Abre la disposición PRODUCCIÓN al arrancar Chrome, en la primera
// ventana normal, salvo que se haya desactivado en la ventana de la
// extensión. Si Chrome ya ha restaurado el grupo, no lo duplica.

import {
  chromeSignedIn, getAutoOpen, openLayout, wipeSiteSessions,
} from "./layout.js";

// S156 (1.3.0): al cerrar la sesión de Chrome se cierran también las de
// todos los sitios; y si Chrome arranca sin sesión, igual (por si se
// cerró con Chrome apagado o la extensión no llegó a enterarse).
chrome.identity.onSignInChanged.addListener(async (_account, signedIn) => {
  if (!signedIn) await wipeSiteSessions();
});

// Chrome may still be restoring the last session when it starts: wait a
// moment so a restored PRODUCCION group is found and not duplicated.
// ---
// Chrome puede estar aún restaurando la sesión anterior: se espera un
// poco para encontrar el grupo restaurado y no duplicarlo.
const RESTORE_WAIT_MS = 5000;

async function openInWindow(windowId) {
  if (!(await getAutoOpen())) return;
  await new Promise((resolve) => setTimeout(resolve, RESTORE_WAIT_MS));
  const result = await openLayout(windowId);
  if (!result.ok) console.warn("Disposición PRODUCCIÓN:", result.text);
}

chrome.runtime.onStartup.addListener(async () => {
  if (!(await chromeSignedIn())) {
    await wipeSiteSessions();
    return;
  }
  const windows = await chrome.windows.getAll({ windowTypes: ["normal"] });
  if (windows.length) {
    await openInWindow(windows[0].id);
    return;
  }
  // Sin ventana todavía: se espera a la primera que se abra.
  const onCreated = async (win) => {
    if (win.type !== "normal") return;
    chrome.windows.onCreated.removeListener(onCreated);
    await openInWindow(win.id);
  };
  chrome.windows.onCreated.addListener(onCreated);
});
