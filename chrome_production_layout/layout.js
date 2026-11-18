// Shared logic of the PRODUCCION layout extension (S152).
// ---
// Lógica común de la extensión: leer, guardar y abrir la disposición del
// grupo. La usan la ventana (popup.js) y el arranque de Chrome
// (background.js).

// S152: the layout lives in Chrome's synced storage, so it follows the
// user's Google account to any PC where the extension is installed. A
// synced item holds at most 8 KB, so each tab is an item of its own.
// ---
// La disposición va al almacenamiento sincronizado de Chrome y sigue a la
// cuenta de Google a cualquier PC con la extensión. Un elemento
// sincronizado admite como mucho 8 KB, así que cada pestaña va aparte.
const LOCAL_KEY = "layout";
const META_KEY = "layout_meta";
const TAB_PREFIX = "layout_tab_";
const AUTO_OPEN_KEY = "auto_open";

export function normalize(text) {
  return (text || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .trim()
    .toUpperCase();
}

export async function findGroup(windowId, title) {
  const groups = await chrome.tabGroups.query({ windowId });
  return groups.find((g) => normalize(g.title) === normalize(title));
}

export async function readLayout() {
  const { [META_KEY]: meta } = await chrome.storage.sync.get(META_KEY);
  if (!meta) {
    // Disposición guardada en este PC por la versión 1.0.0: se pasa a la
    // sincronizada.
    const { [LOCAL_KEY]: local } = await chrome.storage.local.get(
      LOCAL_KEY);
    if (local) {
      await writeLayout(local);
      await chrome.storage.local.remove(LOCAL_KEY);
    }
    return local || null;
  }
  const keys = Array.from({ length: meta.count }, (_, i) => TAB_PREFIX + i);
  const items = await chrome.storage.sync.get(keys);
  return { ...meta, tabs: keys.map((k) => items[k]) };
}

export async function writeLayout(layout) {
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

// S152: PRODUCCION opens by itself when Chrome starts, unless turned off.
// ---
// PRODUCCIÓN se abre sola al arrancar Chrome, salvo que se desactive.
export async function getAutoOpen() {
  const { [AUTO_OPEN_KEY]: value } = await chrome.storage.sync.get(
    AUTO_OPEN_KEY);
  return value !== false;
}

export async function setAutoOpen(value) {
  await chrome.storage.sync.set({ [AUTO_OPEN_KEY]: Boolean(value) });
}

// Save: read the group's tabs in order and which ones are split together.
// Guardar: lee las pestañas del grupo en orden y cuáles van divididas.
export async function saveLayout(windowId, title) {
  const group = await findGroup(windowId, title);
  if (!group) {
    return { ok: false, text: `No hay ningún grupo «${title}» en esta ventana.` };
  }
  const tabs = (await chrome.tabs.query({ windowId }))
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
  // Una pestaña ya unida a la anterior no empieza otro par.
  for (let i = 1; i < saved.length; i++) {
    if (saved[i - 1].splitWithNext) saved[i].splitWithNext = false;
  }
  await writeLayout({
    title: group.title, color: group.color, tabs: saved,
    savedAt: Date.now(),
  });
  return { ok: true, text: "Disposición guardada." };
}

// Open: create the tabs, group them and rebuild the split views.
// Abrir: crea las pestañas, las agrupa y vuelve a montar las vistas
// divididas. Si el grupo ya está en la ventana no lo duplica.
export async function openLayout(windowId) {
  const layout = await readLayout();
  if (!layout) {
    return { ok: false, text: "Primero monta el grupo a mano y pulsa " +
                               "«Guardar disposición actual»." };
  }
  const existing = await findGroup(windowId, layout.title);
  if (existing) {
    await chrome.tabGroups.update(existing.id, { collapsed: false });
    return { ok: true, text: `El grupo «${layout.title}» ya está abierto ` +
                             "en esta ventana; no se abre otra vez." };
  }
  const created = [];
  for (const item of layout.tabs) {
    created.push(await chrome.tabs.create({
      windowId, url: item.url, active: false, pinned: item.pinned,
    }));
  }
  const groupId = await chrome.tabs.group({
    tabIds: created.map((t) => t.id), createProperties: { windowId },
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
  return {
    ok: failures.length === 0,
    text: `Abiertas ${created.length} pestañas y ${splits} vistas ` +
          "divididas." + (failures.length
            ? `\nNo se pudieron dividir:\n${failures.join("\n")}` : ""),
  };
}
