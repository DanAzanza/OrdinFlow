/* ═══════════════════════════════════════════════════════════
   SETUP & SYSTEM CONFIG EDITOR TAB (AUTO-SAVE)
   ═══════════════════════════════════════════════════════════ */

const CONFIG_LABELS = {
    // 📂 Folders & Paths
    watch_dir: "Central Inbox Folder",
    target_base_dir: "Cases Archive Folder",
    keep_inbox_files: "Keep processed files in Inbox (mark as done in .meta)",
    dashboard_port: "Dashboard Web Port",

    // 🗂️ Archiving & Directory Structure
    folder_structure: "Subfolder Hierarchy (comma separated)",
    folder_delimiter: "Folder Delimiter",
    match_folder_by: "Match Existing Folders By (comma separated, e.g. Nachname, Vorname)",

    // 🤖 AI Detection & Acceleration
    llm_backend: "LLM Backend (llama_cpp / server)",
    llm_model_path: "AI Vision Model Path (.gguf)",
    mmproj_path: "Vision Projector Path (.gguf)",
    n_gpu_layers: "GPU Acceleration Layers (-1 = all)",
    n_batch: "Prompt Batch Size",
    type_k: "KV-Cache K Quantization (8=Q8_0, 1=F16)",
    type_v: "KV-Cache V Quantization (8=Q8_0, 1=F16)",
    vision_api_timeout: "AI Response Timeout (seconds)",
    vision_api_retries: "AI Retry Attempts on Error"
};

const CONFIG_GROUPS = [
    {
        title: "📂 Folders & System Paths",
        keys: ["watch_dir", "target_base_dir", "keep_inbox_files", "dashboard_port"]
    },
    {
        title: "🗂️ Archiving & Directory Structure",
        keys: ["folder_structure", "folder_delimiter", "match_folder_by"]
    },
    {
        title: "🤖 AI Detection & Acceleration",
        keys: [
            "llm_backend",
            "llm_model_path",
            "mmproj_path",
            "n_gpu_layers",
            "n_batch",
            "type_k",
            "type_v",
            "vision_api_timeout",
            "vision_api_retries"
        ]
    }
];

const PATH_CONFIG = {
    watch_dir: { type: "folder", title: "Inbox-Ordner auswählen" },
    target_base_dir: { type: "folder", title: "Vorgänge-Archivordner auswählen" },
    llm_model_path: { type: "file", title: "GGUF Vision-Modelldatei auswählen", filter: ".gguf" },
    mmproj_path: { type: "file", title: "GGUF mmproj-Projektordatei auswählen", filter: ".gguf" }
};

const CONFIG_INT_KEYS = new Set([
    "dashboard_port",
    "n_gpu_layers",
    "n_batch",
    "n_ubatch",
    "n_ctx",
    "type_k",
    "type_v",
    "max_tokens",
    "vision_api_retries"
]);

const CONFIG_FLOAT_KEYS = new Set([
    "vision_api_timeout",
    "contrast_limit"
]);

// ── Auto-Save Controller State ──
const _autoSaveState = {
    timer: null,
    statusTimer: null,
    inFlight: false,
    queued: false,
    lastSaved: {},
    abortController: null
};

function updateConfigStatus(status, errorMsg = "") {
    const el = document.getElementById("configSaveStatus");
    if (!el) return;

    if (_autoSaveState.statusTimer) {
        clearTimeout(_autoSaveState.statusTimer);
        _autoSaveState.statusTimer = null;
    }

    el.className = `config-save-status ${status}`.trim();
    if (status === "saving") {
        el.innerHTML = '<span class="config-save-spinner"></span> Saving...';
        el.title = "Persisting settings to server...";
    } else if (status === "saved") {
        el.innerHTML = "✓ Saved";
        el.title = "All settings persisted";
        _autoSaveState.statusTimer = setTimeout(() => {
            el.className = "config-save-status";
            el.innerHTML = "";
            el.title = "";
        }, 2500);
    } else if (status === "error") {
        el.innerHTML = '⚠️ Save failed <button type="button" class="config-save-retry-btn" onclick="triggerConfigAutoSave(true)">Retry</button>';
        el.title = errorMsg || "Failed to persist settings";
    } else {
        el.innerHTML = "";
        el.title = "";
    }
}

function cancelPendingAutoSave() {
    if (_autoSaveState.timer) {
        clearTimeout(_autoSaveState.timer);
        _autoSaveState.timer = null;
    }
    _autoSaveState.queued = false;
    if (_autoSaveState.abortController) {
        _autoSaveState.abortController.abort();
        _autoSaveState.abortController = null;
    }
    _autoSaveState.inFlight = false;
}

function flushPendingConfigSave() {
    if (_autoSaveState.timer) {
        clearTimeout(_autoSaveState.timer);
        _autoSaveState.timer = null;
        executeConfigAutoSave();
    }
}

function buildConfigDeltaPayload(lastSaved) {
    const payload = {};
    let hasChanges = false;
    let hasValidationError = false;

    const allKeys = CONFIG_GROUPS.flatMap(g => g.keys);
    for (const key of allKeys) {
        const el = document.getElementById(`cfg_${key}`);
        if (!el) continue;

        let val;
        if (el.type === "checkbox") {
            val = el.checked;
        } else if (key === "folder_structure" || key === "match_folder_by") {
            val = el.value ? el.value.split(",").map(s => s.trim().replace(/^\{+|\}+$/g, "")).filter(Boolean) : [];
        } else if (CONFIG_INT_KEYS.has(key)) {
            const raw = el.value.trim();
            if (raw === "" || (isNaN(Number(raw)) && raw !== "-")) {
                el.classList.add("input-invalid-intermediate");
                hasValidationError = true;
                continue;
            }
            if (raw === "-") {
                hasValidationError = true;
                continue;
            }
            el.classList.remove("input-invalid-intermediate");
            val = parseInt(raw, 10);
        } else if (CONFIG_FLOAT_KEYS.has(key)) {
            const raw = el.value.trim();
            if (raw === "" || (isNaN(Number(raw)) && raw !== "-")) {
                el.classList.add("input-invalid-intermediate");
                hasValidationError = true;
                continue;
            }
            if (raw === "-") {
                hasValidationError = true;
                continue;
            }
            el.classList.remove("input-invalid-intermediate");
            val = parseFloat(raw);
        } else {
            val = el.value.trim();
        }

        const prevVal = lastSaved ? lastSaved[key] : undefined;
        if (JSON.stringify(val) !== JSON.stringify(prevVal)) {
            payload[key] = val;
            hasChanges = true;
        }
    }

    return { payload, hasChanges, hasValidationError };
}

function triggerConfigAutoSave(immediate = false) {
    if (_autoSaveState.timer) {
        clearTimeout(_autoSaveState.timer);
        _autoSaveState.timer = null;
    }

    if (immediate) {
        executeConfigAutoSave();
    } else {
        _autoSaveState.timer = setTimeout(executeConfigAutoSave, 500);
    }
}

async function executeConfigAutoSave() {
    if (_autoSaveState.inFlight) {
        _autoSaveState.queued = true;
        return;
    }

    const { payload, hasChanges, hasValidationError } = buildConfigDeltaPayload(_autoSaveState.lastSaved);
    if (!hasChanges) {
        if (!hasValidationError && !_autoSaveState.queued) {
            // Already in sync
        }
        return;
    }

    _autoSaveState.inFlight = true;
    _autoSaveState.queued = false;
    updateConfigStatus("saving");

    try {
        _autoSaveState.abortController = new AbortController();
        const res = await api("/api/config", {
            method: "PUT",
            body: JSON.stringify(payload),
            signal: _autoSaveState.abortController.signal
        });

        if (res && (res.status === "ok" || res.changed !== undefined)) {
            Object.assign(_autoSaveState.lastSaved, payload);
            if (state.config) {
                Object.assign(state.config, payload);
            }
            updateConfigStatus("saved");

            // Broadcast config refresh only if directory/routing structural settings changed
            if ("folder_structure" in payload || "folder_delimiter" in payload || "match_folder_by" in payload) {
                AppEvents.emit("config:refresh");
            }
        } else {
            throw new Error(res?.error || "Failed to persist configuration");
        }
    } catch (e) {
        if (e.name !== "AbortError") {
            console.error("[ConfigAutoSave] Error saving configuration:", e);
            updateConfigStatus("error", e.message);
            toast("Error saving settings: " + e.message, "error");
        }
    } finally {
        _autoSaveState.inFlight = false;
        _autoSaveState.abortController = null;
        if (_autoSaveState.queued) {
            _autoSaveState.queued = false;
            executeConfigAutoSave();
        }
    }
}

function attachConfigInputListeners() {
    const inputs = document.querySelectorAll("#setupConfigContainer input, #setupConfigContainer select, #setupConfigContainer textarea");
    inputs.forEach(el => {
        el.addEventListener("input", () => triggerConfigAutoSave(false));
        el.addEventListener("change", () => triggerConfigAutoSave(true));
    });
}

// ── Path Picker Integration ──
let _activePathPicker = null;
let _pathPickerAbortController = null;
let _activeSelectedItemEl = null;
let _pathPickerEventsInitialized = false;

function initPathPickerEvents() {
    if (_pathPickerEventsInitialized) return;
    const listEl = document.getElementById("pathPickerList");
    const modalEl = document.getElementById("systemPathPickerModal");

    if (listEl) {
        listEl.addEventListener("click", (e) => {
            if (!_activePathPicker) return;
            const openBtn = e.target.closest('[data-action="open"]');
            if (openBtn) {
                e.stopPropagation();
                const item = openBtn.closest(".path-picker-item");
                const targetPath = openBtn.dataset.path || (item ? item.dataset.path : "");
                if (targetPath) loadPathPickerDirectory(targetPath);
                return;
            }

            const item = e.target.closest(".path-picker-item");
            if (!item) return;

            const targetPath = item.dataset.path;
            const isDir = item.dataset.isDir === "true";
            const isParent = item.dataset.isParent === "true";

            if (isParent) {
                if (targetPath) loadPathPickerDirectory(targetPath);
                return;
            }

            selectPathPickerItem(targetPath, isDir, item);
        });

        listEl.addEventListener("dblclick", (e) => {
            if (!_activePathPicker) return;
            const item = e.target.closest(".path-picker-item");
            if (!item) return;

            const targetPath = item.dataset.path;
            const isDir = item.dataset.isDir === "true";

            if (isDir) {
                if (targetPath) loadPathPickerDirectory(targetPath);
            } else {
                selectPathPickerItem(targetPath, false, item);
                confirmSystemPathPicker();
            }
        });
    }

    if (modalEl) {
        modalEl.addEventListener("keydown", (e) => {
            if (!_activePathPicker) return;
            const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : "";
            const isInputFocused = activeTag === "input" || activeTag === "textarea";

            if (e.key === "Escape") {
                e.preventDefault();
                closeSystemPathPicker();
                return;
            }

            if (!isInputFocused) {
                if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                    e.preventDefault();
                    navigatePathPickerItems(e.key === "ArrowDown" ? 1 : -1);
                } else if (e.key === "Enter") {
                    e.preventDefault();
                    if (_activeSelectedItemEl) {
                        const isDir = _activeSelectedItemEl.dataset.isDir === "true";
                        const p = _activeSelectedItemEl.dataset.path;
                        if (isDir) {
                            loadPathPickerDirectory(p);
                        } else {
                            confirmSystemPathPicker();
                        }
                    }
                } else if (e.key === "Backspace") {
                    e.preventDefault();
                    const parentEl = document.querySelector('.path-picker-item[data-is-parent="true"]');
                    if (parentEl && parentEl.dataset.path) {
                        loadPathPickerDirectory(parentEl.dataset.path);
                    }
                }
            }
        });
    }

    _pathPickerEventsInitialized = true;
}

function navigatePathPickerItems(direction) {
    const listEl = document.getElementById("pathPickerList");
    if (!listEl) return;
    const items = Array.from(listEl.querySelectorAll(".path-picker-item")).filter(
        (el) => el.style.display !== "none" && el.dataset.isParent !== "true"
    );
    if (!items.length) return;

    let currentIndex = items.indexOf(_activeSelectedItemEl);
    let nextIndex = 0;
    if (currentIndex === -1) {
        nextIndex = direction > 0 ? 0 : items.length - 1;
    } else {
        nextIndex = (currentIndex + direction + items.length) % items.length;
    }

    const nextEl = items[nextIndex];
    if (nextEl) {
        selectPathPickerItem(nextEl.dataset.path, nextEl.dataset.isDir === "true", nextEl);
        nextEl.scrollIntoView({ block: "nearest" });
    }
}

function filterPathPickerEntries(query) {
    const listEl = document.getElementById("pathPickerList");
    if (!listEl) return;
    const q = (query || "").trim().toLowerCase();
    const items = listEl.querySelectorAll(".path-picker-item");
    items.forEach((item) => {
        if (item.dataset.isParent === "true") {
            item.style.display = "flex";
            return;
        }
        const name = (item.dataset.name || "").toLowerCase();
        item.style.display = !q || name.includes(q) ? "flex" : "none";
    });
}

function handlePathPickerInputKey(e) {
    if (e.key === "Enter") {
        e.preventDefault();
        const inputPathEl = document.getElementById("pathPickerSelectedInput");
        const val = inputPathEl ? inputPathEl.value.trim().replace(/^["']+|["']+$/g, "") : "";
        if (!val) return;

        if (_activePathPicker && _activePathPicker.selectedPath && val === _activePathPicker.selectedPath) {
            confirmSystemPathPicker();
        } else {
            loadPathPickerDirectory(val);
        }
    } else if (e.key === "Escape") {
        closeSystemPathPicker();
    }
}

function browseSystemPath(key) {
    const pCfg = PATH_CONFIG[key];
    if (!pCfg) return;
    initPathPickerEvents();

    const inputEl = document.getElementById(`cfg_${key}`);
    const currentVal = inputEl ? inputEl.value.trim().replace(/^["']+|["']+$/g, "") : "";

    _activePathPicker = {
        key: key,
        type: pCfg.type,
        title: pCfg.title,
        filter: pCfg.filter || "",
        currentPath: currentVal,
        selectedPath: currentVal,
        inputEl: inputEl,
    };
    _activeSelectedItemEl = null;

    const modal = document.getElementById("systemPathPickerModal");
    const titleEl = document.getElementById("pathPickerTitle");
    const inputPathEl = document.getElementById("pathPickerSelectedInput");
    let filterInputEl = document.getElementById("pathPickerFilter");

    if (!filterInputEl) {
        const breadcrumbsEl = document.getElementById("pathPickerBreadcrumbs");
        if (breadcrumbsEl) {
            const bar = document.createElement("div");
            bar.className = "path-picker-search-bar";
            bar.innerHTML = '<input type="text" class="path-picker-filter-input" id="pathPickerFilter" placeholder="🔍 Schnellsuchfilter in diesem Ordner..." oninput="filterPathPickerEntries(this.value)" autocomplete="off" />';
            breadcrumbsEl.after(bar);
            filterInputEl = document.getElementById("pathPickerFilter");
        }
    }

    let loaderBar = document.getElementById("pathPickerLoaderBar");
    if (!loaderBar) {
        const wrapper = document.getElementById("pathPickerListWrapper") || document.querySelector(".path-picker-list-wrapper");
        if (wrapper) {
            loaderBar = document.createElement("div");
            loaderBar.className = "path-picker-loader-bar";
            loaderBar.id = "pathPickerLoaderBar";
            wrapper.prepend(loaderBar);
        }
    }

    if (inputPathEl && !inputPathEl._pickerKeydownAttached) {
        inputPathEl.addEventListener("keydown", handlePathPickerInputKey);
        inputPathEl._pickerKeydownAttached = true;
    }

    if (titleEl) {
        titleEl.textContent = (pCfg.type === "file" ? "📄 " : "📁 ") + pCfg.title;
    }
    if (inputPathEl) {
        inputPathEl.value = currentVal;
    }
    if (filterInputEl) {
        filterInputEl.value = "";
    }
    if (modal) {
        modal.classList.add("active");
        modal.classList.add("show");
    }

    loadPathPickerDirectory(currentVal);
}

async function loadPathPickerDirectory(targetPath = "") {
    if (!_activePathPicker) return;
    const cleanPath = (targetPath || "").trim().replace(/^["']+|["']+$/g, "");

    const listEl = document.getElementById("pathPickerList");
    const wrapperEl = document.getElementById("pathPickerListWrapper");
    const drivesEl = document.getElementById("pathPickerDrives");
    const quickEl = document.getElementById("pathPickerQuick");
    const breadcrumbsEl = document.getElementById("pathPickerBreadcrumbs");
    const inputPathEl = document.getElementById("pathPickerSelectedInput");
    const filterInputEl = document.getElementById("pathPickerFilter");

    if (filterInputEl) {
        filterInputEl.value = "";
    }

    // Cancel any in-flight request to prevent race conditions
    if (_pathPickerAbortController) {
        _pathPickerAbortController.abort();
    }
    _pathPickerAbortController = new AbortController();

    // Non-destructive loading state: keep current items visible while dimming
    const hasExistingItems = listEl && listEl.querySelectorAll(".path-picker-item").length > 0;
    if (listEl) {
        listEl.classList.add("loading");
        if (!hasExistingItems) {
            listEl.innerHTML = '<div class="path-picker-empty">Lade Verzeichnis...</div>';
        }
    }
    if (wrapperEl) {
        wrapperEl.classList.add("is-loading");
    }

    try {
        const queryParams = new URLSearchParams({
            path: cleanPath || "",
            type: _activePathPicker.type || "folder",
            filter: _activePathPicker.filter || "",
        });

        const res = await api(`/api/system/fs_list?${queryParams.toString()}`, {
            signal: _pathPickerAbortController.signal,
        });

        if (!res || res.status !== "ok") {
            if (listEl) {
                listEl.innerHTML = '<div class="path-picker-empty path-picker-error">Directory could not be loaded</div>';
            }
            return;
        }

        _activePathPicker.currentPath = res.current_path;
        if (!_activePathPicker.selectedPath || _activePathPicker.type === "folder") {
            _activePathPicker.selectedPath = res.current_path;
            if (inputPathEl) inputPathEl.value = res.current_path;
        }

        // Render Drives
        if (drivesEl && Array.isArray(res.drives)) {
            drivesEl.innerHTML = res.drives
                .map((d) => {
                    const isActive = res.current_path && res.current_path.toUpperCase().startsWith(d.toUpperCase());
                    return `<button type="button" class="path-picker-pill-btn ${isActive ? "active" : ""}" data-path="${escapeHtml(d)}" onclick="loadPathPickerDirectory(this.dataset.path)">💾 ${escapeHtml(d)}</button>`;
                })
                .join("");
        }

        // Render Quick Shortcuts
        if (quickEl && Array.isArray(res.quick_locations)) {
            quickEl.innerHTML = res.quick_locations
                .map((q) => {
                    return `<button type="button" class="path-picker-pill-btn" data-path="${escapeHtml(q.path)}" onclick="loadPathPickerDirectory(this.dataset.path)">📍 ${escapeHtml(q.name)}</button>`;
                })
                .join("");
        }

        // Render Breadcrumbs
        if (breadcrumbsEl && Array.isArray(res.breadcrumbs)) {
            let crumbsHtml = "";
            res.breadcrumbs.forEach((c, idx) => {
                if (idx > 0) crumbsHtml += '<span class="path-crumb-sep">\\</span>';
                const isLast = idx === res.breadcrumbs.length - 1;
                crumbsHtml += `<span class="path-crumb ${isLast ? "current" : ""}" data-path="${escapeHtml(c.path)}" onclick="loadPathPickerDirectory(this.dataset.path)">${escapeHtml(c.name)}</span>`;
            });
            breadcrumbsEl.innerHTML = crumbsHtml;
        }

        // Render Items
        if (listEl) {
            let itemsHtml = "";

            if (res.truncated) {
                itemsHtml += '<div class="path-picker-truncation-note">⚠️ Mehr als 1.000 Einträge – Anzeige auf die ersten 1.000 begrenzt</div>';
            }

            if (res.parent_path) {
                itemsHtml += `
                    <div class="path-picker-item" data-path="${escapeHtml(res.parent_path)}" data-is-dir="true" data-is-parent="true">
                        <div class="path-picker-item-left">
                            <span class="path-picker-item-icon">📁</span>
                            <span class="path-picker-item-name">.. (Übergeordneter Ordner)</span>
                        </div>
                        <button type="button" class="path-picker-nav-btn" data-action="open" data-path="${escapeHtml(res.parent_path)}" title="In übergeordneten Ordner wechseln">➔ Öffnen</button>
                    </div>`;
            }

            if (!res.entries || res.entries.length === 0) {
                itemsHtml += `<div class="path-picker-empty">${_activePathPicker.type === "file" ? "Keine passenden Dateien gefunden" : "Dieser Ordner ist leer"}</div>`;
            } else {
                for (const entry of res.entries) {
                    const isSelected = _activePathPicker.selectedPath === entry.path;
                    const icon = entry.is_dir ? "📁" : entry.name.endsWith(".gguf") ? "🤖" : "📄";

                    if (entry.is_dir) {
                        itemsHtml += `
                            <div class="path-picker-item ${isSelected ? "selected" : ""}" data-path="${escapeHtml(entry.path)}" data-name="${escapeHtml(entry.name)}" data-is-dir="true">
                                <div class="path-picker-item-left">
                                    <span class="path-picker-item-icon">${icon}</span>
                                    <span class="path-picker-item-name" title="${escapeHtml(entry.name)}">${escapeHtml(entry.name)}</span>
                                </div>
                                <div class="path-picker-item-meta">
                                    <span>${escapeHtml(entry.modified_str || "")}</span>
                                    <button type="button" class="path-picker-nav-btn" data-action="open" data-path="${escapeHtml(entry.path)}" title="In Ordner wechseln">➔ Öffnen</button>
                                </div>
                            </div>`;
                    } else {
                        itemsHtml += `
                            <div class="path-picker-item ${isSelected ? "selected" : ""}" data-path="${escapeHtml(entry.path)}" data-name="${escapeHtml(entry.name)}" data-is-dir="false">
                                <div class="path-picker-item-left">
                                    <span class="path-picker-item-icon">${icon}</span>
                                    <span class="path-picker-item-name" title="${escapeHtml(entry.name)}">${escapeHtml(entry.name)}</span>
                                </div>
                                <div class="path-picker-item-meta">
                                    <span>${escapeHtml(entry.size_str || "")}</span>
                                    <span>${escapeHtml(entry.modified_str || "")}</span>
                                </div>
                            </div>`;
                    }
                }
            }

            listEl.innerHTML = itemsHtml;
            _activeSelectedItemEl = listEl.querySelector(".path-picker-item.selected");
            if (wrapperEl) wrapperEl.scrollTop = 0;
        }
    } catch (e) {
        if (e && (e.name === "AbortError" || e.message === "The user aborted a request.")) {
            return;
        }
        console.error("loadPathPickerDirectory error:", e);
        if (listEl) listEl.innerHTML = '<div class="path-picker-empty path-picker-error">Fehler beim Laden des Verzeichnisses</div>';
    } finally {
        if (listEl) listEl.classList.remove("loading");
        if (wrapperEl) wrapperEl.classList.remove("is-loading");
    }
}

function selectPathPickerItem(path, isDir, el) {
    if (!_activePathPicker) return;
    _activePathPicker.selectedPath = path;
    const inputPathEl = document.getElementById("pathPickerSelectedInput");
    if (inputPathEl) inputPathEl.value = path;

    if (_activeSelectedItemEl && _activeSelectedItemEl !== el) {
        _activeSelectedItemEl.classList.remove("selected");
    }
    if (el) {
        el.classList.add("selected");
        _activeSelectedItemEl = el;
    }
}

function confirmSystemPathPicker() {
    if (!_activePathPicker) return;
    const inputPathEl = document.getElementById("pathPickerSelectedInput");
    const rawVal = inputPathEl ? inputPathEl.value : (_activePathPicker.selectedPath || _activePathPicker.currentPath);
    const chosen = (rawVal || "").trim().replace(/^["']+|["']+$/g, "");

    if (chosen && _activePathPicker.inputEl) {
        _activePathPicker.inputEl.value = chosen;
        _activePathPicker.inputEl.dispatchEvent(new Event("change", { bubbles: true }));
    }
    closeSystemPathPicker();
}

function closeSystemPathPicker() {
    if (_pathPickerAbortController) {
        _pathPickerAbortController.abort();
        _pathPickerAbortController = null;
    }
    const modal = document.getElementById("systemPathPickerModal");
    if (modal) {
        modal.classList.remove("active");
        modal.classList.remove("show");
    }
    _activePathPicker = null;
    _activeSelectedItemEl = null;
}

// ── Tab Lifecycle ──
async function loadConfigTab() {
    cancelPendingAutoSave();
    updateConfigStatus("");

    try {
        const cfg = await api("/api/config");
        state.config = cfg;
        _autoSaveState.lastSaved = JSON.parse(JSON.stringify(cfg));

        const container = document.getElementById("setupConfigContainer");
        if (!container) return;

        let html = "";
        for (const group of CONFIG_GROUPS) {
            let groupHtml = "";
            for (const key of group.keys) {
                if (key in cfg) {
                    const val = cfg[key];
                    const label = CONFIG_LABELS[key] || key;
                    const strVal = Array.isArray(val) ? val.join(", ") : String(val);

                    if (typeof val === "boolean") {
                        groupHtml += `
                            <div class="config-group config-toggle-group">
                                <input type="checkbox" id="cfg_${key}" ${val ? "checked" : ""} class="config-checkbox">
                                <label for="cfg_${key}" class="config-checkbox-label">${escapeHtml(label)}</label>
                            </div>`;
                    } else if (key in PATH_CONFIG) {
                        groupHtml += `
                            <div class="config-group config-path-group">
                                <label class="doc-editor-label" for="cfg_${key}">${escapeHtml(label)}</label>
                                <div class="path-input-wrapper">
                                    <input type="text" class="doc-editor-input path-input-field" id="cfg_${key}" value="${escapeHtml(strVal)}" readonly onclick="browseSystemPath('${key}')">
                                    <button type="button" class="btn-picker" onclick="browseSystemPath('${key}')">
                                        📁 Durchsuchen...
                                    </button>
                                </div>
                            </div>`;
                    } else {
                        groupHtml += `
                            <div class="config-group config-text-group">
                                <label class="doc-editor-label" for="cfg_${key}">${escapeHtml(label)}</label>
                                <input type="text" class="doc-editor-input" id="cfg_${key}" value="${escapeHtml(strVal)}">
                            </div>`;
                    }
                }
            }

            if (groupHtml) {
                html += `
                    <div class="doc-editor-section config-editor-section">
                        <h4 class="config-section-title">${escapeHtml(group.title)}</h4>
                        <div class="config-section-body">${groupHtml}</div>
                    </div>`;
            }
        }

        container.innerHTML = html;
        attachConfigInputListeners();
        updateConfigInspector();
    } catch (e) {
        console.error("Error loading config:", e);
        toast("Error loading configuration", "error");
    }
}

function updateConfigInspector() {
    if (typeof closeAppInspector === "function") {
        closeAppInspector();
    }
}

window.addEventListener("beforeunload", () => {
    flushPendingConfigSave();
});
