// Popup of the PRODUCCION layout extension (S152).
// ---
// Ventana de la extensión: guarda la disposición del grupo (pestañas,
// orden, vistas divididas, color) y la vuelve a abrir con un clic.

const STORAGE_KEY = "layout";
// S152: the layout lives in Chrome's synced storage, so it follows the
// user's Google account to any PC where the extension is installed. A
// synced item holds at most 8 KB, so each tab is an item of its own.
// ---
// La disposición va al almacenamiento sincronizado de Chrome y sigue a la
// cuenta de Google a cualquier PC con la extensión. Un elemento
// sincronizado admite como mucho 8 KB, así que cada pestaña va aparte.
const META_KEY = "layout_meta";
const TAB_PREFIX = "layout_tab_";

async function readLayout() {
  const { [META_KEY]: meta } = await chrome.storage.sync.get(META_KEY);
  if (!meta) {
    // Disposición guardada antes en este PC (versión 1.0.0): se pasa a
    // la sincronizada.
    const { [STORAGE_KEY]: local } = await chrome.storage.local.get(
      STORAGE_KEY);
    if (local) {
      await writeLayout(local);
      await chrome.storage.local.remove(STORAGE_KEY);
    }
    return local || null;
  }
  const keys = Array.from({ length: meta.count }, (_, i) => TAB_PREFIX + i);
  const items = await chrome.storage.sync.get(keys);
  return { ...meta, tabs: keys.map((k) => items[k]) };
}

async function writeLayout(layout) {
  const old = await chrome.storage.sync.get(null);
  const stale = Object.keys(old).filter((k) => k.startsWith(TAB_PREFIX));
  if (stale.length) await chrome.storage.sync.remove(stale);
  const items = {};
  layout.tabs.forEach((tab, i) => {
    items[TAB_PREFIX + i] = { ...tab, title: (tab.title || "").slice(0, 80) };
  });
  items[META_KEY] = {
    title: layout.title, color: layout.color, savedAt: layout.savedAt,
    count: layout.tabs.length,
  };
  await chrome.storage.sync.set(items);
}

const groupInput = document.getElementById("group");
const savedLine = document.getElementById("saved");
const statusLine = document.getElementById("status");

function show(text, isError = false) {
  statusLine.textContent = text;
  statusLine.className = isError ? "error" : "";
}

function normalize(text) {
  return (text || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .trim()
    .toUpperCase();
}

async function findGroup(windowId, title) {
  const groups = await chrome.tabGroups.query({ windowId });
  return groups.find((g) => normalize(g.title) === normalize(title));
}

async function refreshSaved() {
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

// Save: read the group's tabs in order and which ones are split together.
// Guardar: lee las pestañas del grupo en orden y cuáles van divididas.
async function saveLayout() {
  const win = await chrome.windows.getCurrent();
  const group = await findGroup(win.id, groupInput.value);
  if (!group) {
    show(`No hay ningún grupo «${groupInput.value}» en esta ventana.`, true);
    return;
  }
  const tabs = (await chrome.tabs.query({ windowId: win.id }))
    .filter((t) => t.groupId === group.id)
    .sort((a, b) => a.index - b.index);
  const saved = tabs.map((tab, i) => {
    const next = tabs[i + 1];
    return {
      url: tab.url || tab.pendingUrl,
      title: tab.title,
      pinned: tab.pinned,
      splitWithNext: Boolean(
        next && tab.splitViewId !== -1 && tab.splitViewId !== undefined
        && next.splitViewId === tab.splitViewId),
    };
  });
  // A tab already joined to the previous one never starts another pair.
  // Una pestaña ya unida a la anterior no empieza otro par.
  for (let i = 1; i < saved.length; i++) {
    if (saved[i - 1].splitWithNext) saved[i].splitWithNext = false;
  }
  const layout = {
    title: group.title,
    color: group.color,
    tabs: saved,
    savedAt: Date.now(),
  };
  await writeLayout(layout);
  await refreshSaved();
  show("Disposición guardada.");
}

// Open: create the tabs, group them and rebuild the split views.
// Abrir: crea las pestañas, las agrupa y vuelve a montar las vistas
// divididas.
async function openLayout() {
  const layout = await readLayout();
  if (!layout) {
    show("Primero monta el grupo a mano y pulsa «Guardar disposición " +
         "actual».", true);
    return;
  }
  const win = await chrome.windows.getCurrent();
  const existing = await findGroup(win.id, layout.title);
  if (existing) {
    await chrome.tabGroups.update(existing.id, { collapsed: false });
    show(`El grupo «${layout.title}» ya está abierto en esta ventana; ` +
         "no se abre otra vez.");
    return;
  }
  show(`Abriendo ${layout.tabs.length} pestañas…`);
  const created = [];
  for (const item of layout.tabs) {
    created.push(await chrome.tabs.create({
      windowId: win.id, url: item.url, active: false, pinned: item.pinned,
    }));
  }
  const groupId = await chrome.tabs.group({
    tabIds: created.map((t) => t.id), createProperties: { windowId: win.id },
  });
  await chrome.tabGroups.update(groupId, {
    title: layout.title, color: layout.color, collapsed: false,
  });
  const failures = [];
  let splits = 0;
  for (let i = 0; i < layout.tabs.length - 1; i++) {
    if (!layout.tabs[i].splitWithNext) continue;
    try {
      await chrome.tabs.createSplit([created[i].id, created[i + 1].id]);
      splits++;
    } catch (error) {
      failures.push(`${layout.tabs[i].title}: ${error.message}`);
    }
  }
  await chrome.tabs.update(created[0].id, { active: true });
  show(`Abiertas ${created.length} pestañas y ${splits} vistas divididas.` +
       (failures.length ? `\nNo se pudieron dividir:\n${failures.join("\n")}`
                        : ""),
       failures.length > 0);
}

document.getElementById("save").addEventListener("click", () =>
  saveLayout().catch((e) => show(`Error al guardar: ${e.message}`, true)));
document.getElementById("open").addEventListener("click", () =>
  openLayout().catch((e) => show(`Error al abrir: ${e.message}`, true)));
refreshSaved();
