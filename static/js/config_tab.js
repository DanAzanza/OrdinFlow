/* ═══════════════════════════════════════════════════════════
   SETUP & SYSTEM CONFIG EDITOR TAB
   ═══════════════════════════════════════════════════════════ */

const CONFIG_LABELS = {
    // 📂 Folders & Paths
    watch_dir: "Central Inbox Folder",
    target_base_dir: "Cases Archive Folder",
    dashboard_port: "Dashboard Web Port",

    // 🗂️ Archiving & Directory Structure
    folder_structure: "Subfolder Hierarchy (comma separated)",
    folder_delimiter: "Folder Delimiter",

    // 🤖 AI Detection & Thresholds
    model_name: "AI Vision Model Path / Name (.gguf)",
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
        title: "🤖 AI Detection & Thresholds",
        keys: ["model_name", "vision_api_timeout", "vision_api_retries"]
    }
];

function markConfigDirty(dirty = true) {
    state.configDirty = dirty;
    const btn = document.getElementById("btnSaveConfig");
    if (!btn) return;
    if (dirty) {
        btn.classList.add("unsaved");
        btn.innerHTML = "🔴 Save Unsaved Changes";
    } else {
        btn.classList.remove("unsaved");
        btn.innerHTML = "💾 Save Settings";
    }
}

function attachConfigInputListeners() {
    const inputs = document.querySelectorAll("#setupConfigContainer input, #setupConfigContainer select, #setupConfigContainer textarea");
    inputs.forEach(el => {
        el.addEventListener("input", () => markConfigDirty(true));
        el.addEventListener("change", () => markConfigDirty(true));
    });
}

async function loadConfigTab() {
    try {
        const cfg = await api("/api/config");
        state.config = cfg;

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
        markConfigDirty(false);
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

async function saveConfigFromForm() {
    try {
        const payload = {};
        const allKeys = CONFIG_GROUPS.flatMap(g => g.keys);

        for (const key of allKeys) {
            const el = document.getElementById(`cfg_${key}`);
            if (!el) continue;

            if (el.type === "checkbox") {
                payload[key] = el.checked;
            } else {
                let val = el.value.trim();
                if (key === "folder_structure") {
                    payload[key] = val ? val.split(",").map(s => s.trim()).filter(Boolean) : [];
                } else if (["vision_api_timeout", "dashboard_port", "vision_api_retries"].includes(key)) {
                    payload[key] = Number(val) || 0;
                } else {
                    payload[key] = val;
                }
            }
        }

        await api("/api/config", {
            method: "PUT",
            body: JSON.stringify(payload),
        });

        toast("Settings saved successfully!");
        markConfigDirty(false);
        await loadConfigTab();
        AppEvents.emit("config:refresh");
    } catch (e) {
        console.error("Error saving config:", e);
        toast("Error saving settings: " + e.message, "error");
    }
}
