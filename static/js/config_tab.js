/* ═══════════════════════════════════════════════════════════
   SETUP & SYSTEM CONFIG EDITOR TAB (AUTO-SAVE)
   ═══════════════════════════════════════════════════════════ */

const CONFIG_LABELS = {
    // 📂 Folders & Paths
    watch_dir: "Central Inbox Folder",
    target_base_dir: "Cases Archive Folder",
    dashboard_port: "Dashboard Web Port",

    // 🗂️ Archiving & Directory Structure
    folder_structure: "Subfolder Hierarchy (comma separated)",
    folder_delimiter: "Folder Delimiter",

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
        keys: ["watch_dir", "target_base_dir", "dashboard_port"]
    },
    {
        title: "🗂️ Archiving & Directory Structure",
        keys: ["folder_structure", "folder_delimiter"]
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
        } else if (key === "folder_structure") {
            val = el.value ? el.value.split(",").map(s => s.trim()).filter(Boolean) : [];
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
            if ("folder_structure" in payload || "folder_delimiter" in payload) {
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

function browseSystemPath(key) {
    const pCfg = PATH_CONFIG[key];
    if (!pCfg) return;
    const inputEl = document.getElementById(`cfg_${key}`);
    const currentVal = inputEl ? inputEl.value.trim() : "";

    _activePathPicker = {
        key: key,
        type: pCfg.type,
        title: pCfg.title,
        filter: pCfg.filter || "",
        currentPath: currentVal,
        selectedPath: currentVal,
        inputEl: inputEl
    };

    const modal = document.getElementById("systemPathPickerModal");
    const titleEl = document.getElementById("pathPickerTitle");
    const inputPathEl = document.getElementById("pathPickerSelectedInput");
    if (titleEl) {
        titleEl.textContent = (pCfg.type === "file" ? "📄 " : "📁 ") + pCfg.title;
    }
    if (inputPathEl) {
        inputPathEl.value = currentVal;
    }
    if (modal) {
        modal.classList.add("active");
        modal.classList.add("show");
    }

    loadPathPickerDirectory(currentVal);
}

async function loadPathPickerDirectory(targetPath = "") {
    if (!_activePathPicker) return;
    const listEl = document.getElementById("pathPickerList");
    const drivesEl = document.getElementById("pathPickerDrives");
    const quickEl = document.getElementById("pathPickerQuick");
    const breadcrumbsEl = document.getElementById("pathPickerBreadcrumbs");
    const inputPathEl = document.getElementById("pathPickerSelectedInput");

    if (listEl) {
        listEl.innerHTML = '<div class="path-picker-empty">Lade Verzeichnis...</div>';
    }

    try {
        const queryParams = new URLSearchParams({
            path: targetPath || "",
            type: _activePathPicker.type || "folder",
            filter: _activePathPicker.filter || ""
        });
        const res = await api(`/api/system/fs_list?${queryParams.toString()}`);
        if (!res || res.status !== "ok") {
            if (listEl) listEl.innerHTML = '<div class="path-picker-empty path-picker-error">Directory could not be loaded</div>';
            return;
        }

        _activePathPicker.currentPath = res.current_path;
        if (!_activePathPicker.selectedPath || _activePathPicker.type === "folder") {
            _activePathPicker.selectedPath = res.current_path;
            if (inputPathEl) inputPathEl.value = res.current_path;
        }

        // Render Drives
        if (drivesEl) {
            drivesEl.innerHTML = (res.drives || []).map(d => {
                const isActive = res.current_path && res.current_path.toUpperCase().startsWith(d.toUpperCase());
                return `<button type="button" class="path-picker-pill-btn ${isActive ? "active" : ""}" onclick="loadPathPickerDirectory('${escapeHtml(d.replace(/\\/g, "\\\\"))}')">💾 ${escapeHtml(d)}</button>`;
            }).join("");
        }

        // Render Quick Shortcuts
        if (quickEl) {
            quickEl.innerHTML = (res.quick_locations || []).map(q => {
                return `<button type="button" class="path-picker-pill-btn" onclick="loadPathPickerDirectory('${escapeHtml(q.path.replace(/\\/g, "\\\\"))}')">📍 ${escapeHtml(q.name)}</button>`;
            }).join("");
        }

        // Render Breadcrumbs
        if (breadcrumbsEl) {
            let crumbsHtml = "";
            (res.breadcrumbs || []).forEach((c, idx) => {
                if (idx > 0) crumbsHtml += '<span class="path-crumb-sep">\\</span>';
                const isLast = idx === res.breadcrumbs.length - 1;
                crumbsHtml += `<span class="path-crumb ${isLast ? "current" : ""}" onclick="loadPathPickerDirectory('${escapeHtml(c.path.replace(/\\/g, "\\\\"))}')">${escapeHtml(c.name)}</span>`;
            });
            breadcrumbsEl.innerHTML = crumbsHtml;
        }

        // Render Items
        if (listEl) {
            let itemsHtml = "";
            if (res.parent_path) {
                itemsHtml += `
                    <div class="path-picker-item" onclick="loadPathPickerDirectory('${escapeHtml(res.parent_path.replace(/\\/g, "\\\\"))}')">
                        <div class="path-picker-item-left">
                            <span class="path-picker-item-icon">📁</span>
                            <span class="path-picker-item-name">.. (Übergeordneter Ordner)</span>
                        </div>
                    </div>`;
            }

            if (!res.entries || res.entries.length === 0) {
                itemsHtml += `<div class="path-picker-empty">${_activePathPicker.type === "file" ? "Keine passenden Dateien gefunden" : "Dieser Ordner ist leer"}</div>`;
            } else {
                for (const entry of res.entries) {
                    const isSelected = _activePathPicker.selectedPath === entry.path;
                    const icon = entry.is_dir ? "📁" : (entry.name.endsWith(".gguf") ? "🤖" : "📄");
                    const clickAction = entry.is_dir
                        ? `ondblclick="loadPathPickerDirectory('${escapeHtml(entry.path.replace(/\\/g, "\\\\"))}')" onclick="selectPathPickerItem('${escapeHtml(entry.path.replace(/\\/g, "\\\\"))}', true, this)"`
                        : `onclick="selectPathPickerItem('${escapeHtml(entry.path.replace(/\\/g, "\\\\"))}', false, this)" ondblclick="confirmSystemPathPicker()"`;

                    itemsHtml += `
                        <div class="path-picker-item ${isSelected ? "selected" : ""}" ${clickAction}>
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
            listEl.innerHTML = itemsHtml;
        }
    } catch (e) {
        console.error("loadPathPickerDirectory error:", e);
        if (listEl) listEl.innerHTML = '<div class="path-picker-empty path-picker-error">Error loading directory</div>';
    }
}

function selectPathPickerItem(path, isDir, el) {
    if (!_activePathPicker) return;
    _activePathPicker.selectedPath = path;
    const inputPathEl = document.getElementById("pathPickerSelectedInput");
    if (inputPathEl) inputPathEl.value = path;

    const listEl = document.getElementById("pathPickerList");
    if (listEl) {
        listEl.querySelectorAll(".path-picker-item").forEach(item => item.classList.remove("selected"));
    }
    if (el) {
        el.classList.add("selected");
    }
}

function confirmSystemPathPicker() {
    if (!_activePathPicker) return;
    const inputPathEl = document.getElementById("pathPickerSelectedInput");
    const chosen = inputPathEl ? inputPathEl.value.trim() : (_activePathPicker.selectedPath || _activePathPicker.currentPath);

    if (chosen && _activePathPicker.inputEl) {
        _activePathPicker.inputEl.value = chosen;
        _activePathPicker.inputEl.dispatchEvent(new Event("change", { bubbles: true }));
    }
    closeSystemPathPicker();
}

function closeSystemPathPicker() {
    const modal = document.getElementById("systemPathPickerModal");
    if (modal) {
        modal.classList.remove("active");
        modal.classList.remove("show");
    }
    _activePathPicker = null;
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
