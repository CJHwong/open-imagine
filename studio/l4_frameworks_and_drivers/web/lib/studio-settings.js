// Settings collects browser preferences and server-owned controls without duplicating them.
import "./theme.js";
import "./locale.js";
import { closeMenus } from "../components/popup-menu.js";
import { t } from "./i18n.js";

const tr = (key, values) => t("settings." + key, values);
const trigger = document.getElementById("theme-toggle");
const dialog = document.createElement("dialog");
dialog.id = "settings-dialog";
dialog.setAttribute("aria-labelledby", "settings-title");
const sections = [
  ["appearance", "aperture"],
  ["generation", "sparkle"],
  ["phone", "qr"],
  ["library", "image"],
  ["storage", "download"],
];
const icon = (name) =>
  `<svg class="icon" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
dialog.innerHTML = `<header class="settings-header"><div><span class="settings-eyebrow">OPEN IMAGINE / ${tr("eyebrow")}</span><h2 id="settings-title">${tr("title")}</h2></div><button type="button" class="settings-close" aria-label="${tr("close")}">${icon("x")}</button></header>
<div class="settings-layout"><nav class="settings-nav" role="tablist" aria-label="${tr("sections")}">${sections.map(([id, glyph]) => `<button type="button" role="tab" id="settings-tab-${id}" aria-controls="settings-panel-${id}" aria-selected="false" data-section="${id}">${icon(glyph)}<span>${tr(id)}</span><span class="settings-nav-arrow">›</span></button>`).join("")}<p>${tr("sidebarNote")}</p></nav>
<div class="settings-content">
<section role="tabpanel" id="settings-panel-appearance" aria-labelledby="settings-tab-appearance" hidden><div class="settings-section-heading"><span class="settings-scope">${tr("browser")}</span><h3>${tr("appearanceTitle")}</h3><p>${tr("appearanceNote")}</p></div><h4>${tr("theme")}</h4><div class="settings-theme-grid" role="radiogroup" aria-label="${tr("theme")}"></div><div class="settings-card"><div><h4>${tr("language")}</h4><p>${tr("languageNote")}</p></div><div class="settings-languages" role="radiogroup" aria-label="${tr("language")}"></div></div></section>
<section role="tabpanel" id="settings-panel-generation" aria-labelledby="settings-tab-generation" hidden><div class="settings-section-heading"><span class="settings-scope shared">${tr("everyone")}</span><h3>${tr("generationTitle")}</h3><p>${tr("generationNote")}</p></div><div class="settings-card"><div><h4>${tr("memoryTitle")}</h4><p>${t("settings.memory.help")}</p></div><button type="button" id="require-memory-estimate-toggle" role="switch" aria-checked="true" aria-label="${t("settings.memory.require")}" disabled><span></span></button></div><p class="settings-note">${tr("memoryNote")}</p><div id="settings-reset" class="settings-tools"></div></section>
<section role="tabpanel" id="settings-panel-library" aria-labelledby="settings-tab-library" hidden><div class="settings-section-heading"><span class="settings-scope">${tr("browser")}</span><h3>${tr("libraryTitle")}</h3><p>${tr("libraryNote")}</p></div><div id="settings-library-controls" class="settings-tools"></div></section>
<section role="tabpanel" id="settings-panel-storage" aria-labelledby="settings-tab-storage" hidden><div class="settings-section-heading"><span class="settings-scope shared">${tr("everyone")}</span><h3>${tr("storageTitle")}</h3><p>${tr("storageNote")}</p></div><div class="settings-storage-summary"><div><span>${tr("diskUsage")}</span><strong id="settings-storage-total">${tr("loading")}</strong></div><button type="button" id="settings-storage-refresh">${tr("refresh")}</button></div><div id="settings-storage-models"></div><label class="settings-runtime"><input type="checkbox" id="settings-include-runtime">${tr("includeRuntime")}</label><p class="settings-note">${tr("protectedNote")}</p><button type="button" class="settings-primary" id="settings-review" disabled>${tr("review")}</button><div id="settings-cleanup-preview" hidden><h4>${tr("reviewTitle")}</h4><div id="settings-cleanup-items"></div><p class="settings-note">${tr("reinstallNote")}</p><button type="button" class="settings-danger" id="settings-remove">${tr("remove")}</button><button type="button" id="settings-back">${tr("back")}</button></div></section>
<section role="tabpanel" id="settings-panel-phone" aria-labelledby="settings-tab-phone" hidden><div class="settings-section-heading"><span class="settings-scope shared">${tr("everyone")}</span><h3>${tr("phoneTitle")}</h3><p>${tr("phoneNote")}</p></div><div class="settings-card"><div><h4>${tr("phoneCode")}</h4><p>${tr("phoneCodeNote")}</p></div><button type="button" id="settings-phone-open">${tr("phoneOpen")}</button></div></section>
<p id="settings-status" role="status" aria-live="polite"></p><p id="settings-error" role="alert" hidden></p></div></div>
<footer class="settings-footer"><span>${tr("footer")}</span><div id="settings-api"></div><button type="button" id="settings-done">${tr("done")}</button></footer>`;
document.body.append(dialog);
const find = (selector) => dialog.querySelector(selector);
const menu = document.getElementById("theme-menu");
let target = find("#settings-library-controls");
// Existing controls keep their IDs, saved values and event handlers.
for (const node of [...menu.children]) {
  if (node.matches("[data-theme]")) {
    node.setAttribute("role", "radio");
    node.tabIndex = node.getAttribute("aria-checked") === "true" ? 0 : -1;
    const name = node.textContent.trim();
    node.replaceChildren();
    const swatch = document.createElement("span");
    swatch.className = "settings-theme-preview";
    swatch.setAttribute("aria-hidden", "true");
    swatch.innerHTML = "<i></i><i></i><i></i><i></i>";
    const label = document.createElement("span");
    label.textContent = name;
    node.append(swatch, label);
    find(".settings-theme-grid").append(node);
  } else if (node.matches("[data-locale], #locale-automatic")) {
    node.setAttribute("role", "radio");
    node.tabIndex = node.getAttribute("aria-checked") === "true" ? 0 : -1;
    find(".settings-languages").append(node);
  } else if (node.id === "api-spec") {
    node.setAttribute("role", "button");
    find("#settings-api").append(node);
  } else if (node.matches(".menu-head")) {
    if (node.textContent === t("page.reset.menu"))
      target = find("#settings-reset");
    else if (
      node.textContent === t("page.keep.images") ||
      node.textContent === t("page.gallery.file")
    ) {
      target = find("#settings-library-controls");
      target.append(node);
    }
  } else if (node.matches("button")) {
    if (node.getAttribute("role") === "menuitemcheckbox")
      node.setAttribute("role", "switch");
    else node.setAttribute("role", "button");
    target.append(node);
  }
}
let section = "appearance",
  saving = false,
  revision = 0,
  inventory = null,
  plan = null,
  planSelection = null,
  storageRevision = 0;
const selected = new Set();
function notice(message, error = false) {
  find("#settings-status").textContent = error ? "" : message;
  find("#settings-error").textContent = error ? tr("requestError", {message}) : "";
  find("#settings-error").hidden = !error;
}
function selectSection(id, focus = false) {
  section = id;
  for (const [name] of sections) {
    const tab = find("#settings-tab-" + name);
    tab.setAttribute("aria-selected", String(name === id));
    tab.tabIndex = name === id ? 0 : -1;
    find("#settings-panel-" + name).hidden = name !== id;
  }
  try {
    sessionStorage.setItem("studio-settings-section", id);
  } catch (_) {}
  notice("");
  if (focus) find("#settings-tab-" + id).focus();
  if (id === "storage") refreshStorage();
}
async function json(path, body) {
  const response = await fetch(
    "/api/v1/" + path,
    body === undefined
      ? { cache: "no-store" }
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || response.statusText);
  return result;
}
const memory = find("#require-memory-estimate-toggle");
async function refreshMemory() {
  if (saving) return;
  const request = ++revision;
  try {
    const settings = await json("settings");
    if (request === revision) {
      memory.setAttribute(
        "aria-checked",
        String(settings.require_memory_estimate),
      );
      memory.disabled = false;
    }
  } catch (error) {
    if (request === revision) {
      memory.disabled = true;
      notice(error.message, true);
    }
  }
}
memory.addEventListener("click", async () => {
  if (saving) return;
  saving = true;
  revision++;
  memory.disabled = true;
  try {
    const settings = await json("settings", {
      require_memory_estimate: memory.getAttribute("aria-checked") !== "true",
    });
    memory.setAttribute(
      "aria-checked",
      String(settings.require_memory_estimate),
    );
    notice(tr("saved"));
  } catch (error) {
    notice(error.message, true);
  } finally {
    saving = false;
    memory.disabled = false;
  }
});
function open() {
  closeMenus();
  dialog.showModal();
  trigger.setAttribute("aria-expanded", "true");
  selectSection(section);
  refreshMemory();
  find(".settings-close").focus();
}
function close() {
  dialog.close();
}
trigger.addEventListener("click", open);
find(".settings-close").addEventListener("click", close);
find("#settings-done").addEventListener("click", close);
dialog.addEventListener("close", () => {
  trigger.setAttribute("aria-expanded", "false");
  try {
    sessionStorage.removeItem("studio-settings-section");
  } catch (_) {}
  trigger.focus();
});
dialog.addEventListener("click", (event) => {
  if (event.target === dialog) {
    const box = dialog.getBoundingClientRect();
    if (
      event.clientX < box.left ||
      event.clientX > box.right ||
      event.clientY < box.top ||
      event.clientY > box.bottom
    )
      close();
  }
});
for (const [id] of sections)
  find("#settings-tab-" + id).addEventListener("click", () =>
    selectSection(id),
  );
dialog.addEventListener("keydown", (event) => {
  const tab = event.target.closest("[role=tab]"),
    radio = event.target.closest("[role=radio]");
  if (!tab && !radio) return;
  if (
    ![
      "ArrowLeft",
      "ArrowRight",
      "ArrowUp",
      "ArrowDown",
      "Home",
      "End",
    ].includes(event.key)
  )
    return;
  event.preventDefault();
  const items = [
    ...(tab ? find(".settings-nav") : radio.parentElement).querySelectorAll(
      tab ? "[role=tab]" : "[role=radio]",
    ),
  ];
  const index = items.indexOf(tab || radio);
  const next =
    event.key === "Home"
      ? 0
      : event.key === "End"
        ? items.length - 1
        : (index +
            (["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1) +
            items.length) %
          items.length;
  items[next].click();
  items[next].focus();
});
function bytes(value) {
  const unit =
    value >= 1024 ** 3
      ? "GB"
      : value >= 1024 ** 2
        ? "MB"
        : value >= 1024
          ? "KB"
          : "B";
  return (
    new Intl.NumberFormat(document.documentElement.lang, {
      maximumFractionDigits: 1,
    }).format(
      value /
        (unit === "GB"
          ? 1024 ** 3
          : unit === "MB"
            ? 1024 ** 2
            : unit === "KB"
              ? 1024
              : 1),
    ) +
    " " +
    unit
  );
}
function resetPlan() {
  storageRevision++;
  plan = null;
  planSelection = null;
  find("#settings-cleanup-preview").hidden = true;
  find("#settings-review").hidden = false;
  find("#settings-review").disabled = !selected.size;
}
async function refreshStorage() {
  if (saving) return;
  find("#settings-storage-refresh").disabled = true;
  resetPlan();
  const request = storageRevision;
  try {
    const result = await json("model-storage");
    if (request !== storageRevision) return;
    inventory = result;
    selected.clear();
    resetPlan();
    find("#settings-storage-total").textContent = bytes(
      inventory.assets.reduce((sum, asset) => sum + asset.bytes, 0),
    );
    const list = find("#settings-storage-models");
    list.replaceChildren();
    const installed = inventory.models.filter((model) =>
      inventory.assets.some((asset) => asset.models.includes(model.id)),
    );
    if (!inventory.available || !installed.length) {
      const empty = document.createElement("p");
      empty.className = "settings-empty";
      empty.textContent = tr(inventory.available ? "noModels" : "stubStorage");
      list.append(empty);
    }
    for (const model of installed) {
      const assets = inventory.assets.filter((asset) =>
        asset.models.includes(model.id),
      );
      const row = document.createElement("label");
      row.className = "settings-model-row";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = model.id;
      checkbox.addEventListener("change", () => {
        checkbox.checked ? selected.add(model.id) : selected.delete(model.id);
        resetPlan();
      });
      const copy = document.createElement("span"),
        title = document.createElement("strong"),
        detail = document.createElement("small");
      title.textContent = model.name;
      const workspace = tr("workspace." + model.workspace);
      detail.textContent = assets.some((asset) => asset.models.length > 1)
        ? tr("sharedWorkspace", {workspace, shared: tr("shared")})
        : workspace;
      copy.append(title, detail);
      const size = document.createElement("span");
      size.className = "settings-model-size";
      size.textContent = bytes(
        assets.reduce((sum, asset) => sum + asset.bytes, 0),
      );
      row.append(checkbox, copy, size);
      list.append(row);
    }
  } catch (error) {
    notice(error.message, true);
  } finally {
    find("#settings-storage-refresh").disabled = false;
  }
}
find("#settings-storage-refresh").addEventListener("click", refreshStorage);
find("#settings-include-runtime").addEventListener("change", resetPlan);
find("#settings-back").addEventListener("click", resetPlan);
find("#settings-review").addEventListener("click", async () => {
  const button = find("#settings-review");
  button.disabled = true;
  notice("");
  const request = storageRevision;
  const selection = {
    models: [...selected],
    include_runtime: find("#settings-include-runtime").checked,
  };
  try {
    const result = await json("model-storage/plan", selection);
    if (request !== storageRevision) return;
    plan = result;
    planSelection = selection;
    const list = find("#settings-cleanup-items");
    list.replaceChildren();
    for (const [action, items] of [
      ["remove", plan.remove],
      ["retain", plan.retain],
    ])
      for (const asset of items) {
        const row = document.createElement("p");
        row.className = "settings-plan-row";
        const models = asset.models
            .map(
              (id) =>
                inventory.models.find((model) => model.id === id)?.name || id,
            )
            .join(", ");
        row.textContent = tr("planAsset", {
          action: tr(action === "remove" ? "willRemove" : "willRetain"),
          models, asset: asset.label, location: asset.location, size: bytes(asset.bytes),
        }) + (asset.reason ? " " + tr("planReason", {reason: tr("reason." + asset.reason)}) : "");
        list.append(row);
      }
    find("#settings-remove").textContent = tr("removeSized", {action: tr("remove"), size: bytes(plan.bytes)});
    find("#settings-remove").disabled = !plan.remove.length;
    find("#settings-cleanup-preview").hidden = false;
    button.hidden = true;
  } catch (error) {
    notice(error.message, true);
  } finally {
    button.disabled = false;
  }
});
find("#settings-remove").addEventListener("click", async () => {
  if (!plan || !planSelection || saving) return;
  saving = true;
  const selection = planSelection;
  for (const input of find("#settings-panel-storage").querySelectorAll(
    "input,button",
  ))
    input.disabled = true;
  const button = find("#settings-remove");
  button.disabled = true;
  try {
    await json("model-storage/remove", {
      ...selection,
      revision: plan.revision,
    });
    saving = false;
    await refreshStorage();
    notice(tr("removed"));
  } catch (error) {
    notice(error.message, true);
  } finally {
    saving = false;
    for (const input of find("#settings-panel-storage").querySelectorAll(
      "input,button",
    ))
      input.disabled = false;
    button.disabled = !plan?.remove.length;
    find("#settings-review").disabled = !selected.size;
  }
});
try {
  const restored = sessionStorage.getItem("studio-settings-section");
  if (sections.some(([id]) => id === restored)) {
    section = restored;
    open();
  }
} catch (_) {}
