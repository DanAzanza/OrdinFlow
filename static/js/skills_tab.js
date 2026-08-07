/* ═══════════════════════════════════════════════════════════
   SKILLS MANAGEMENT JS (Master-Detail Editor & Skill Queue Inspector)
   ═══════════════════════════════════════════════════════════ */

let selectedSkillId = null;
let currentEditingSkill = null;
let currentEditingSteps = [];
let activeInputField = null;
let pendingApproveFolder = null;
let draggedQueueItemId = null;
let queuePollInterval = null;

document.addEventListener("focusin", (e) => {
	if (
		e.target &&
		(e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT")
	) {
		activeInputField = e.target;
	}
});

async function loadSkills() {
	try {
		const data = await api("/api/skills");
		state.skills = data.skills || [];
		renderSkillsSidebar(state.skills);

		if (selectedSkillId) {
			const found = state.skills.find((s) => s.id === selectedSkillId);
			if (found) {
				selectSkill(selectedSkillId);
				return;
			}
		}

		if (state.skills.length > 0) {
			selectSkill(state.skills[0].id);
		} else {
			showNoSkillSelected();
		}
	} catch (e) {
		console.error("Error loading skills:", e);
		toast("Fehler beim Laden der Skills: " + e.message, "error");
	}
}

function filterSkills() {
	const q = (document.getElementById("searchSkills")?.value || "")
		.toLowerCase()
		.trim();
	if (!state.skills) return;

	if (!q) {
		renderSkillsSidebar(state.skills);
		return;
	}

	const filtered = state.skills.filter((s) => {
		const name = (s.name || "").toLowerCase();
		const id = (s.id || "").toLowerCase();
		const desc = (s.description || "").toLowerCase();
		const win = (s.target_window || "").toLowerCase();
		return (
			name.includes(q) || id.includes(q) || desc.includes(q) || win.includes(q)
		);
	});

	renderSkillsSidebar(filtered, q);
}

function renderSkillsSidebar(skills, searchQuery = "") {
	const container = document.getElementById("skillsSidebarList");
	if (!container) return;

	if (skills.length === 0) {
		container.innerHTML = `
			<div style="padding: 16px; text-align: center; color: var(--text-dim); font-size: 0.82rem;">
				${searchQuery ? "Keine Treffer" : "Keine Skills vorhanden"}
			</div>
		`;
		return;
	}

	container.innerHTML = skills
		.map((skill) => {
			const isSelected = skill.id === selectedSkillId;
			const isImport = skill.type === "import";
			const stepCount = (skill.steps || []).length;
			const icon = isImport ? "📥" : "⚡";
			const badgeClass = isImport ? "badge-import-skill" : "badge-export-skill";
			const badgeText = isImport ? "Import" : `${stepCount} Schritte`;

			return `
				<div class="doc-type-item ${isSelected ? "active" : ""}" onclick="selectSkill('${escapeHtml(skill.id)}')">
					<div class="doc-type-item-name">
						<span>${icon}</span>
						<span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 135px;" title="${escapeHtml(skill.name || skill.id)}">
							${escapeHtml(skill.name || skill.id)}
						</span>
					</div>
					<span class="${badgeClass}">
						${badgeText}
					</span>
				</div>
			`;
		})
		.join("");
}

function showNoSkillSelected() {
	selectedSkillId = null;
	currentEditingSkill = null;
	currentEditingSteps = [];
	const emptyMsg = document.getElementById("noSkillSelectedMessage");
	const wrapper = document.getElementById("skillFormWrapper");
	if (emptyMsg) emptyMsg.style.display = "flex";
	if (wrapper) wrapper.style.display = "none";
	renderSkillsSidebar(state.skills || []);
	renderQueueInspector();
}

async function selectSkill(skillId) {
	const skillObj = (state.skills || []).find((s) => s.id === skillId);
	if (!skillObj) {
		showNoSkillSelected();
		return;
	}

	selectedSkillId = skillId;
	currentEditingSkill = skillObj;
	currentEditingSteps = skillObj.steps ? JSON.parse(JSON.stringify(skillObj.steps)) : [];

	renderSkillsSidebar(state.skills || []);

	const emptyMsg = document.getElementById("noSkillSelectedMessage");
	const wrapper = document.getElementById("skillFormWrapper");
	if (emptyMsg) emptyMsg.style.display = "none";
	if (wrapper) wrapper.style.display = "flex";

	document.getElementById("skillHeaderTitle").textContent = skillObj.name || skillObj.id;
	const isImport = skillObj.type === "import";
	document.getElementById("skillHeaderBadge").textContent = isImport ? "Import-Skill" : `${currentEditingSteps.length} Schritte`;

	document.getElementById("editorSkillId").value = skillObj.id || "";
	document.getElementById("editorSkillName").value = skillObj.name || "";
	document.getElementById("editorSkillDesc").value = skillObj.description || "";
	document.getElementById("editorSkillType").value = skillObj.type || "export";

	const allowedExts = skillObj.allowed_extensions
		? Array.isArray(skillObj.allowed_extensions)
			? skillObj.allowed_extensions.join(", ")
			: skillObj.allowed_extensions
		: ".pdf, .png, .jpg, .jpeg, .tif, .tiff";
	const allowedEl = document.getElementById("editorSkillAllowedExtensions");
	if (allowedEl) allowedEl.value = allowedExts;

	const splitEl = document.getElementById("editorSkillSplitMulti");
	if (splitEl) splitEl.checked = skillObj.split_multi_documents !== undefined ? skillObj.split_multi_documents : true;
	const saveEmptyEl = document.getElementById("editorSkillSaveEmpty");
	if (saveEmptyEl) saveEmptyEl.checked = skillObj.save_empty_pages !== undefined ? skillObj.save_empty_pages : false;

	document.getElementById("editorSkillTargetWindow").value = skillObj.target_window || "Remote Desktop*";
	document.getElementById("editorSkillRdpPrefix").value = skillObj.rdp_path_prefix || "\\\\tsclient\\C";

	const docTypesVal = skillObj.document_types
		? Array.isArray(skillObj.document_types)
			? skillObj.document_types.join(", ")
			: skillObj.document_types
		: "*";
	document.getElementById("editorSkillDocTypes").value = docTypesVal;
	document.getElementById("editorSkillUploadMode").value = skillObj.upload_mode || "single_file";

	onSkillTypeChange(skillObj.type || "export");
	renderEditorSteps();

	// Render Queue Inspector (Inspector is 100% dedicated to Skill Queue in Skills Tab)
	renderQueueInspector();

	if (!queuePollInterval) {
		queuePollInterval = setInterval(() => {
			const activeTab = document.querySelector(".nav-item.active")?.dataset?.tab;
			if (activeTab === "skills") {
				renderQueueInspector();
			}
		}, 3000);
	}
}

function onSkillTypeChange(type) {
	if (currentEditingSkill) {
		currentEditingSkill.type = type;
	}
	const importMeta = document.getElementById("importSkillMetaSection");
	const exportMeta = document.getElementById("exportSkillMetaSection");
	const exportSection = document.getElementById("exportSkillSection");
	const importSection = document.getElementById("importSkillSection");

	if (type === "import") {
		if (importMeta) importMeta.style.display = "block";
		if (exportMeta) exportMeta.style.display = "none";
		if (exportSection) exportSection.style.display = "none";
		if (importSection) importSection.style.display = "block";

		if (selectedSkillId) {
			loadSkillDocumentTypes(selectedSkillId);
		}
	} else {
		if (importMeta) importMeta.style.display = "none";
		if (exportMeta) exportMeta.style.display = "block";
		if (exportSection) exportSection.style.display = "block";
		if (importSection) importSection.style.display = "none";
	}
}

async function loadSkillDocumentTypes(importSkillId) {
	try {
		const res = await api(`/api/skills/${encodeURIComponent(importSkillId)}/documents`);
		state.editingDocTypes = res.document_types || {};
		state.selectedDocType = null;
		const formEl = document.getElementById("docTypeForm");
		const msgEl = document.getElementById("noDocSelectedMessage");
		if (formEl) formEl.style.display = "none";
		if (msgEl) msgEl.style.display = "flex";
		renderDocTypesSidebar();
	} catch (e) {
		console.error("Error loading document types for skill:", e);
	}
}

function renderDocTypesSidebar() {
	const container = document.getElementById("docTypesList");
	if (!container) return;

	const keys = Object.keys(state.editingDocTypes || {});
	if (keys.length === 0) {
		container.innerHTML = `
			<div style="padding: 16px; text-align: center; color: var(--text-dim); font-size: 0.82rem; background: rgba(0,0,0,0.15); border-radius: 8px;">
				Keine Kategorien im Skill vorhanden.
			</div>
		`;
		return;
	}

	container.innerHTML = keys
		.map((key) => {
			const isSelected = key === state.selectedDocType;
			const doc = state.editingDocTypes[key] || {};
			const emoji = doc.emoji || "📄";
			const fieldCount = Object.keys(doc.extraction_fields || {}).length;

			return `
				<div class="doc-type-item ${isSelected ? "active" : ""}" onclick="selectDocType('${escapeHtml(key)}')">
					<div class="doc-type-item-name">
						<span style="font-size: 1.1rem; width: 22px; text-align: center;">${emoji}</span>
						<span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 140px;" title="${escapeHtml(key)}">
							${escapeHtml(key)}
						</span>
					</div>
					<span class="doc-type-item-count">
						${fieldCount} Felder
					</span>
				</div>
			`;
		})
		.join("");
}

function selectDocType(typeName) {
	state.selectedDocType = typeName;
	renderDocTypesSidebar();

	const msgEl = document.getElementById("noDocSelectedMessage");
	const formEl = document.getElementById("docTypeForm");
	if (msgEl) msgEl.style.display = "none";
	if (formEl) {
		formEl.style.display = "block";
		renderDocTypeForm(typeName);
	}
}

function createNewDocType() {
	const name = prompt("Name of the new document category (e.g. Invoice, Report):");
	if (!name || !name.trim()) return;

	const cleanName = name.trim();
	if (!state.editingDocTypes) state.editingDocTypes = {};
	if (state.editingDocTypes[cleanName]) {
		toast("This document category already exists.", "error");
		return;
	}

	state.editingDocTypes[cleanName] = {
		emoji: "📄",
		classification_desc: "",
		extraction_fields: {
			Dokument: { description: "Category of the document", required: true }
		}
	};

	selectDocType(cleanName);
}

function deleteDocType(typeName) {
	if (!confirm(`Really delete document category '${typeName}'?`)) return;
	if (state.editingDocTypes && state.editingDocTypes[typeName]) {
		delete state.editingDocTypes[typeName];
	}
	state.selectedDocType = null;
	const msgEl = document.getElementById("noDocSelectedMessage");
	const formEl = document.getElementById("docTypeForm");
	if (msgEl) msgEl.style.display = "flex";
	if (formEl) formEl.style.display = "none";
	renderDocTypesSidebar();
}

function autoResizeTextarea(el) {
	if (!el) return;
	el.style.height = "auto";
	el.style.height = Math.max(38, el.scrollHeight + 2) + "px";
}

function renderDocTypeForm(typeName) {
	const container = document.getElementById("docTypeForm");
	if (!container) return;

	const doc = (state.editingDocTypes && state.editingDocTypes[typeName]) || { extraction_fields: {}, classification_desc: "", vision_rules: "", emoji: "📄" };
	const fields = doc.extraction_fields || {};
	const fieldKeys = Object.keys(fields);
	const emoji = doc.emoji || "📄";
	const descValue = doc.classification_desc || doc.vision_rules || "";

	let tableRowsHtml = fieldKeys
		.map((fKey) => {
			const fVal = fields[fKey] || {};
			const desc = typeof fVal === "string" ? fVal : fVal.description || "";
			const req = typeof fVal === "object" ? Boolean(fVal.required) : false;

			return `
				<tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05); transition: background 0.2s;">
					<td style="padding: 10px 12px; vertical-align: top;">
						<input type="text" class="doc-editor-input" value="${escapeHtml(fKey)}" readonly style="background: rgba(99, 102, 241, 0.08); border-color: rgba(99, 102, 241, 0.25); color: #a5b4fc; font-weight: 700;" />
					</td>
					<td style="padding: 10px 12px; vertical-align: top;">
						<textarea class="doc-editor-textarea auto-resize-ta" rows="1" placeholder="Beschreibung für die KI..." oninput="autoResizeTextarea(this)" onchange="updateDocTypeField('${escapeHtml(typeName)}', '${escapeHtml(fKey)}', 'desc', this.value)" style="resize: none; overflow: hidden; min-height: 38px;">${escapeHtml(desc)}</textarea>
					</td>
					<td style="padding: 10px 12px; vertical-align: top; text-align: center;">
						<input type="checkbox" ${req ? "checked" : ""} onchange="updateDocTypeField('${escapeHtml(typeName)}', '${escapeHtml(fKey)}', 'req', this.checked)" style="width: 18px; height: 18px; accent-color: #6366f1; cursor: pointer; margin-top: 8px;" />
					</td>
					<td style="padding: 10px 12px; vertical-align: top; text-align: center;">
						<button class="btn btn-sm btn-danger" onclick="removeExtractionField('${escapeHtml(typeName)}', '${escapeHtml(fKey)}')" title="Feld entfernen" style="padding: 6px 10px; margin-top: 4px;">🗑️</button>
					</td>
				</tr>
			`;
		})
		.join("");

	let tableHtml = `
		<table class="doc-fields-table" style="width: 100%; border-collapse: separate; border-spacing: 0; background: rgba(10, 13, 20, 0.5); border-radius: 10px; border: 1px solid rgba(255,255,255,0.08); overflow: hidden;">
			<thead>
				<tr style="background: rgba(255, 255, 255, 0.03); color: var(--text-dim); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em;">
					<th style="padding: 12px; text-align: left; width: 22%; border-bottom: 1px solid rgba(255,255,255,0.08);">Feldname</th>
					<th style="padding: 12px; text-align: left; width: 60%; border-bottom: 1px solid rgba(255,255,255,0.08);">Extraktionsprompt / Anweisung</th>
					<th style="padding: 12px; text-align: center; width: 10%; border-bottom: 1px solid rgba(255,255,255,0.08);">Pflicht</th>
					<th style="padding: 12px; text-align: center; width: 8%; border-bottom: 1px solid rgba(255,255,255,0.08);">Aktion</th>
				</tr>
			</thead>
			<tbody>
				${tableRowsHtml}
			</tbody>
		</table>
	`;

	if (fieldKeys.length === 0) {
		tableHtml = `<div style="padding: 20px; color: var(--text-dim); font-size: 0.85rem; text-align: center; background: rgba(0,0,0,0.15); border-radius: 8px;">Keine Extraktionsfelder definiert.</div>`;
	}

	container.innerHTML = `
		<div class="doc-form-header-card">
			<div class="doc-form-header-title">
				<div class="doc-form-header-emoji">${emoji}</div>
				<div>
					<h3 style="margin: 0; font-size: 1.15rem; font-weight: 700; color: var(--text);">${escapeHtml(typeName)}</h3>
					<span style="font-size: 0.78rem; color: var(--text-dim);">${fieldKeys.length} Extraktionsfelder konfiguriert</span>
				</div>
			</div>
			<button class="btn btn-sm btn-danger" onclick="deleteDocType('${escapeHtml(typeName)}')">🗑️ Kategorie löschen</button>
		</div>

		<div class="doc-editor-section" style="margin-top: 16px;">
			<h4>🧠 Erkennungs- & Klassifizierungsregeln (KI Vision)</h4>
			<span style="font-size: 0.8rem; color: var(--text-dim); margin-top: -8px; margin-bottom: 6px; display: block;">
				Legen Sie fest, an welchen optischen Text- oder Layoutmerkmalen die KI dieses Dokument erkennt.
			</span>
			<textarea class="doc-editor-textarea auto-resize-ta" rows="2" placeholder="Z.B. Dokument mit dem Text 'Befundbogen' im Kopfbereich..." oninput="autoResizeTextarea(this)" onchange="updateDocTypeRules('${escapeHtml(typeName)}', this.value)" style="resize: none; overflow: hidden; min-height: 52px;">${escapeHtml(descValue)}</textarea>
		</div>

		<div class="doc-editor-section" style="margin-top: 16px;">
			<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
				<h4 style="margin: 0;">📋 Extraktionsfelder & KI-Prompts</h4>
				<button class="btn btn-sm btn-accent" onclick="addExtractionField('${escapeHtml(typeName)}')">➕ Feld hinzufügen</button>
			</div>
			${tableHtml}
		</div>
	`;

	setTimeout(() => {
		container.querySelectorAll(".auto-resize-ta").forEach((ta) => autoResizeTextarea(ta));
	}, 0);
}

function updateDocTypeRules(typeName, value) {
	if (state.editingDocTypes && state.editingDocTypes[typeName]) {
		state.editingDocTypes[typeName].classification_desc = value;
		state.editingDocTypes[typeName].vision_rules = value;
	}
}

function updateDocTypeField(typeName, fieldKey, property, value) {
	if (!state.editingDocTypes || !state.editingDocTypes[typeName]) return;
	const fields = state.editingDocTypes[typeName].extraction_fields;
	if (!fields[fieldKey]) return;

	if (typeof fields[fieldKey] === "string") {
		fields[fieldKey] = { description: fields[fieldKey], required: false };
	}

	if (property === "desc") {
		fields[fieldKey].description = value;
	} else if (property === "req") {
		fields[fieldKey].required = Boolean(value);
	}
}

function addExtractionField(typeName) {
	const key = prompt("Feld-Schlüsselname (z.B. Rechnungsnummer, Datum, Summe):");
	if (!key || !key.trim()) return;

	const cleanKey = key.trim();
	if (!state.editingDocTypes || !state.editingDocTypes[typeName]) return;
	const fields = state.editingDocTypes[typeName].extraction_fields || {};

	if (fields[cleanKey]) {
		toast("Feld existiert bereits.", "error");
		return;
	}

	fields[cleanKey] = { description: "", required: false };
	state.editingDocTypes[typeName].extraction_fields = fields;
	renderDocTypeForm(typeName);
	renderDocTypesSidebar();
}

function removeExtractionField(typeName, fieldKey) {
	if (!state.editingDocTypes || !state.editingDocTypes[typeName]) return;
	delete state.editingDocTypes[typeName].extraction_fields[fieldKey];
	renderDocTypeForm(typeName);
	renderDocTypesSidebar();
}

/* ═══════════════════════════════════════════════════════════
   SKILL QUEUE INSPECTOR (REPLACES SKILLS INSPECTOR COMPLETELY)
   ═══════════════════════════════════════════════════════════ */

async function renderQueueInspector() {
	if (typeof openAppInspector !== "function") return;

	let qState = { is_running: false, items: [] };
	try {
		qState = await api("/api/skills/queue");
	} catch (e) {
		console.error("Error fetching queue:", e);
	}

	// Update Skills Tab Button Indicator Emoji
	const navBtnLabel = document.querySelector(".nav-item[data-tab='skills'] .nav-label");
	if (navBtnLabel) {
		navBtnLabel.textContent = qState.is_running ? "▶ Skills" : "Skills";
	}

	const skillOptions = (state.skills || [])
		.map((s) => `<option value="${escapeHtml(s.id)}">${s.type === "import" ? "📥" : "⚡"} ${escapeHtml(s.name || s.id)}</option>`)
		.join("");

	let queueListHtml = "";
	if (qState.items.length === 0) {
		queueListHtml = `
			<div style="padding: 24px; text-align: center; color: var(--text-dim); background: rgba(0,0,0,0.18); border: 1px dashed var(--border); border-radius: 10px; font-size: 0.82rem;">
				Warteliste ist leer.<br>Füge unten einen Skill hinzu.
			</div>
		`;
	} else {
		queueListHtml = qState.items
			.map((item, index) => {
				const isRunning = item.status === "running";
				const isFailed = item.status === "failed";
				const isCompleted = item.status === "completed";

				let statusBadge = `<span class="badge" style="background: rgba(99, 102, 241, 0.2); color: #a5b4fc;">Waiting</span>`;
				if (isRunning) {
					statusBadge = `<span class="badge" style="background: rgba(16, 185, 129, 0.25); color: #34d399; animation: pulse 1.5s infinite;">▶ Running...</span>`;
				} else if (isCompleted) {
					statusBadge = `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #34d399;">Completed</span>`;
				} else if (isFailed) {
					statusBadge = `<span class="badge" style="background: rgba(239, 68, 68, 0.2); color: #f87171;">Failed</span>`;
				}

				const icon = item.skill_type === "import" ? "📥" : "⚡";

				return `
					<div class="inspector-card" data-queue-id="${escapeHtml(item.id)}" draggable="${!isRunning}" ondragstart="onQueueDragStart(event, '${escapeHtml(item.id)}')" ondragover="onQueueDragOver(event)" ondrop="onQueueDrop(event, '${escapeHtml(item.id)}')" style="margin-bottom: 8px; padding: 10px 12px; background: ${isRunning ? 'rgba(99, 102, 241, 0.12)' : 'rgba(10, 13, 20, 0.6)'}; border: 1px solid ${isRunning ? 'var(--accent)' : 'rgba(255,255,255,0.08)'}; cursor: ${isRunning ? 'default' : 'grab'};">
						<div style="display: flex; justify-content: space-between; align-items: center;">
							<div style="display: flex; align-items: center; gap: 8px;">
								<span style="color: var(--text-dim); cursor: grab; font-size: 0.9rem;">⋮⋮</span>
								<span style="font-size: 1rem;">${icon}</span>
								<div>
									<div style="font-weight: 700; font-size: 0.84rem; color: var(--text);">${escapeHtml(item.skill_name)}</div>
									<div style="font-size: 0.72rem; color: var(--text-dim);">#${index + 1} · ID: ${escapeHtml(item.id)}</div>
								</div>
							</div>
							<div style="display: flex; align-items: center; gap: 6px;">
								${statusBadge}
								${!isRunning ? `
									<button class="btn btn-sm" onclick="removeQueueItem('${escapeHtml(item.id)}')" style="background: none; border: none; color: var(--text-dim); padding: 2px 6px;" title="Remove from queue">
										🗑️
									</button>
								` : ''}
							</div>
						</div>
					</div>
				`;
			})
			.join("");
	}

	const inspectorHtml = `
		<div class="inspector-card" style="margin-bottom: 12px; background: rgba(99, 102, 241, 0.08); border: 1px solid rgba(99, 102, 241, 0.25);">
			<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
				<h4 style="font-size: 0.86rem; margin: 0; color: var(--accent); display: flex; align-items: center; gap: 6px;">
					<span>${qState.is_running ? '▶' : '⏸️'}</span> Status: ${qState.is_running ? 'Running' : 'Ready'}
				</h4>
				<span class="badge" style="background: ${qState.is_running ? 'rgba(16, 185, 129, 0.2)' : 'rgba(255,255,255,0.08)'}; color: ${qState.is_running ? '#34d399' : 'var(--text-dim)'};">
					${qState.items.length} Skills
				</span>
			</div>
			<div style="display: flex; gap: 8px;">
				${!qState.is_running ? `
					<button class="btn btn-primary btn-sm" onclick="startSkillQueue()" style="flex: 1; justify-content: center; font-weight: 700;">
						▶ Start queue
					</button>
				` : `
					<button class="btn btn-danger btn-sm" onclick="stopSkillQueue()" style="flex: 1; justify-content: center; font-weight: 700;">
						⏸️ Stop queue
					</button>
				`}
			</div>
		</div>

		<div class="inspector-card" style="margin-bottom: 12px;">
			<h4 style="font-size: 0.82rem; margin-bottom: 8px; color: var(--text);">➕ Add Skill to Queue</h4>
			<div style="display: flex; gap: 8px;">
				<select id="queueAddSkillSelect" class="doc-editor-input" style="flex: 1; font-size: 0.8rem; padding: 6px 8px;">
					${skillOptions || '<option value="">No skills available</option>'}
				</select>
				<button class="btn btn-accent btn-sm" onclick="addSelectedSkillToQueue()" style="padding: 6px 12px;">
					Add
				</button>
			</div>
		</div>

		<div style="margin-top: 14px;">
			<h4 style="font-size: 0.82rem; margin-bottom: 8px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px;">
				📋 Queued Skills (Drag & Drop to reorder)
			</h4>
			<div id="queueItemsContainer">
				${queueListHtml}
			</div>
		</div>
	`;

	openAppInspector({
		icon: "⚡",
		title: "Skill Queue",
		subtitle: qState.is_running ? "▶ Execution running..." : "Reorder via drag & drop",
		html: inspectorHtml,
	});
}

function onQueueDragStart(e, itemId) {
	draggedQueueItemId = itemId;
	if (e.dataTransfer) {
		e.dataTransfer.effectAllowed = "move";
		e.dataTransfer.setData("text/plain", itemId);
	}
}

function onQueueDragOver(e) {
	e.preventDefault();
	if (e.dataTransfer) {
		e.dataTransfer.dropEffect = "move";
	}
}

async function onQueueDrop(e, targetId) {
	e.preventDefault();
	if (!draggedQueueItemId || draggedQueueItemId === targetId) return;

	const currentNodes = Array.from(document.querySelectorAll("[data-queue-id]"));
	const currentIds = currentNodes.map((el) => el.dataset.queueId);

	const fromIdx = currentIds.indexOf(draggedQueueItemId);
	const toIdx = currentIds.indexOf(targetId);

	if (fromIdx === -1 || toIdx === -1) return;

	currentIds.splice(fromIdx, 1);
	currentIds.splice(toIdx, 0, draggedQueueItemId);

	try {
		await api("/api/skills/queue/reorder", {
			method: "POST",
			body: JSON.stringify({ item_ids: currentIds }),
		});
		renderQueueInspector();
	} catch (err) {
		toast("Error reordering queue: " + err.message, "error");
	}
}

async function startSkillQueue() {
	try {
		await api("/api/skills/queue/start", { method: "POST" });
		toast("▶ Skill queue started!");
		renderQueueInspector();
	} catch (e) {
		toast("Error starting queue: " + e.message, "error");
	}
}

async function stopSkillQueue() {
	try {
		await api("/api/skills/queue/stop", { method: "POST" });
		toast("⏸️ Stopping skill queue...");
		renderQueueInspector();
	} catch (e) {
		toast("Error stopping queue: " + e.message, "error");
	}
}

async function addSelectedSkillToQueue() {
	const sel = document.getElementById("queueAddSkillSelect");
	if (!sel || !sel.value) return;

	const skillId = sel.value;
	try {
		await api("/api/skills/queue/add", {
			method: "POST",
			body: JSON.stringify({ skill_id: skillId, context: {} }),
		});
		toast("Skill added to queue!");
		renderQueueInspector();
	} catch (e) {
		toast("Error adding to queue: " + e.message, "error");
	}
}

async function removeQueueItem(queueId) {
	try {
		await api("/api/skills/queue/remove", {
			method: "POST",
			body: JSON.stringify({ queue_id: queueId }),
		});
		toast("Entry removed from queue.");
		renderQueueInspector();
	} catch (e) {
		toast("Error removing entry: " + e.message, "error");
	}
}

/* ═══════════════════════════════════════════════════════════
   EDITOR ACTIONS & STEPS
   ═══════════════════════════════════════════════════════════ */

function createNewSkill() {
	const newId = "custom_skill_" + Math.floor(Math.random() * 1000);
	const newSkill = {
		id: newId,
		name: "New Workflow",
		type: "export",
		description: "",
		target_window: "Remote Desktop*",
		rdp_path_prefix: "\\\\tsclient\\C",
		document_types: ["*"],
		upload_mode: "single_file",
		enabled: true,
		steps: [
			{
				id: "step_1",
				description: "Focus Window",
				action_type: "FOCUS_WINDOW",
				window_title: "Remote Desktop*",
			},
		],
	};

	selectedSkillId = newId;
	currentEditingSkill = newSkill;
	currentEditingSteps = JSON.parse(JSON.stringify(newSkill.steps));

	renderSkillsSidebar(state.skills || []);

	const emptyMsg = document.getElementById("noSkillSelectedMessage");
	const wrapper = document.getElementById("skillFormWrapper");
	if (emptyMsg) emptyMsg.style.display = "none";
	if (wrapper) wrapper.style.display = "flex";

	document.getElementById("skillHeaderTitle").textContent = newSkill.name;
	document.getElementById("skillHeaderBadge").textContent = "1 step";

	document.getElementById("editorSkillId").value = newSkill.id;
	document.getElementById("editorSkillName").value = newSkill.name;
	document.getElementById("editorSkillDesc").value = "";
	document.getElementById("editorSkillType").value = "export";
	document.getElementById("editorSkillTargetWindow").value = newSkill.target_window;
	document.getElementById("editorSkillRdpPrefix").value = newSkill.rdp_path_prefix;
	document.getElementById("editorSkillDocTypes").value = "*";
	document.getElementById("editorSkillUploadMode").value = "single_file";

	onSkillTypeChange("export");
	renderEditorSteps();
	renderQueueInspector();
}

function insertVariable(varName) {
	if (activeInputField) {
		const start = activeInputField.selectionStart || 0;
		const end = activeInputField.selectionEnd || 0;
		const val = activeInputField.value;
		activeInputField.value = val.substring(0, start) + varName + val.substring(end);
		activeInputField.focus();
		activeInputField.dispatchEvent(new Event("change"));
	} else {
		toast("Click inside an input field first to insert variables.", "error");
	}
}

function addEditorStep(stepObj = null) {
	const step = stepObj || {
		id: "step_" + (currentEditingSteps.length + 1),
		description: "",
		action_type: "CLICK",
		locator: { type: "som_vlm", prompt: "" },
		delay_ms: 500,
	};
	currentEditingSteps.push(step);
	renderEditorSteps();
	updateHeaderStepBadge();
}

function removeEditorStep(index) {
	currentEditingSteps.splice(index, 1);
	renderEditorSteps();
	updateHeaderStepBadge();
}

function moveStepUp(index) {
	if (index <= 0) return;
	const temp = currentEditingSteps[index];
	currentEditingSteps[index] = currentEditingSteps[index - 1];
	currentEditingSteps[index - 1] = temp;
	renderEditorSteps();
}

function moveStepDown(index) {
	if (index >= currentEditingSteps.length - 1) return;
	const temp = currentEditingSteps[index];
	currentEditingSteps[index] = currentEditingSteps[index + 1];
	currentEditingSteps[index + 1] = temp;
	renderEditorSteps();
}

function updateHeaderStepBadge() {
	const stepCount = currentEditingSteps.length;
	const badge = document.getElementById("skillHeaderBadge");
	if (badge && currentEditingSkill && currentEditingSkill.type !== "import") {
		badge.textContent = `${stepCount} ${stepCount === 1 ? "Step" : "Steps"}`;
	}
}

function getActionBadgeStyle(actionType) {
	switch (actionType) {
		case "FOCUS_WINDOW":
			return { label: "FOCUS WINDOW", bg: "rgba(99, 102, 241, 0.2)", color: "#a5b4fc", border: "rgba(99, 102, 241, 0.4)" };
		case "CLICK":
			return { label: "CLICK", bg: "rgba(16, 185, 129, 0.2)", color: "#34d399", border: "rgba(16, 185, 129, 0.4)" };
		case "DOUBLE_CLICK":
			return { label: "DOUBLE CLICK", bg: "rgba(16, 185, 129, 0.3)", color: "#6ee7b7", border: "rgba(16, 185, 129, 0.5)" };
		case "TYPE_TEXT":
			return { label: "TYPE TEXT", bg: "rgba(245, 158, 11, 0.2)", color: "#fbbf24", border: "rgba(245, 158, 11, 0.4)" };
		case "TYPE_FILE_PATH":
			return { label: "TYPE PATH", bg: "rgba(236, 72, 153, 0.2)", color: "#f472b6", border: "rgba(236, 72, 153, 0.4)" };
		case "VERIFY_SCREEN":
			return { label: "VERIFY SCREEN", bg: "rgba(168, 85, 247, 0.2)", color: "#c084fc", border: "rgba(168, 85, 247, 0.4)" };
		case "CALL_SKILL":
			return { label: "SUB SKILL", bg: "rgba(14, 165, 233, 0.2)", color: "#38bdf8", border: "rgba(14, 165, 233, 0.4)" };
		default:
			return { label: actionType || "STEP", bg: "rgba(255,255,255,0.1)", color: "var(--text)", border: "rgba(255,255,255,0.2)" };
	}
}

function renderEditorSteps() {
	const container = document.getElementById("editorStepsList");
	if (!container) return;

	if (currentEditingSteps.length === 0) {
		container.innerHTML = `
			<div style="text-align: center; padding: 24px; color: var(--text-dim); background: rgba(0,0,0,0.2); border: 1px dashed var(--border); border-radius: 10px; font-style: italic; font-size: 0.85rem;">
				No steps defined for this skill. Click "+ Add Step" above.
			</div>
		`;
		return;
	}

	const allStepIds = currentEditingSteps.map((s) => s.id).filter(Boolean);

	container.innerHTML = currentEditingSteps
		.map((step, idx) => {
			const badgeStyle = getActionBadgeStyle(step.action_type);
			const isFirst = idx === 0;
			const isLast = idx === currentEditingSteps.length - 1;

			return `
				<div class="doc-editor-section" style="background: rgba(10, 13, 20, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); padding: 14px 16px; margin-bottom: 8px;">
					<!-- Header des Schritts -->
					<div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px; margin-bottom: 12px;">
						<div style="display: flex; align-items: center; gap: 10px;">
							<span style="font-size: 0.8rem; font-weight: 700; color: var(--text-dim);">#${idx + 1}</span>
							<span class="badge" style="background: ${badgeStyle.bg}; color: ${badgeStyle.color}; border: 1px solid ${badgeStyle.border}; font-weight: 700; font-size: 0.72rem;">
								${badgeStyle.label}
							</span>
							<code style="font-size: 0.8rem; color: #a5b4fc;">${escapeHtml(step.id)}</code>
						</div>
						<div style="display: flex; align-items: center; gap: 6px;">
							<button type="button" class="btn btn-sm btn-icon" onclick="moveStepUp(${idx})" ${isFirst ? "disabled style='opacity:0.3'" : ""} title="Move up">⬆️</button>
							<button type="button" class="btn btn-sm btn-icon" onclick="moveStepDown(${idx})" ${isLast ? "disabled style='opacity:0.3'" : ""} title="Move down">⬇️</button>
							<button type="button" class="btn btn-sm btn-danger" onclick="removeEditorStep(${idx})" style="padding: 3px 8px; font-size: 0.75rem;" title="Remove step">🗑️ Remove</button>
						</div>
					</div>

					<!-- Formularfelder des Schritts -->
					<div class="grid-3col" style="display: grid; grid-template-columns: 1fr 1.5fr 1fr; gap: 10px;">
						<div class="form-group" style="margin:0;">
							<label class="doc-editor-label">Step ID</label>
							<input type="text" class="doc-editor-input" value="${escapeHtml(step.id || "")}" onchange="currentEditingSteps[${idx}].id = this.value; renderEditorSteps();" />
						</div>
						<div class="form-group" style="margin:0;">
							<label class="doc-editor-label">Description</label>
							<input type="text" class="doc-editor-input" value="${escapeHtml(step.description || "")}" placeholder="e.g. Click search field" onchange="currentEditingSteps[${idx}].description = this.value" />
						</div>
						<div class="form-group" style="margin:0;">
							<label class="doc-editor-label">Action Type</label>
							<select class="doc-editor-input" onchange="currentEditingSteps[${idx}].action_type = this.value; renderEditorSteps();">
								<option value="CLICK" ${step.action_type === "CLICK" ? "selected" : ""}>CLICK</option>
								<option value="DOUBLE_CLICK" ${step.action_type === "DOUBLE_CLICK" ? "selected" : ""}>DOUBLE_CLICK</option>
								<option value="TYPE_TEXT" ${step.action_type === "TYPE_TEXT" ? "selected" : ""}>TYPE_TEXT</option>
								<option value="TYPE_FILE_PATH" ${step.action_type === "TYPE_FILE_PATH" ? "selected" : ""}>TYPE_FILE_PATH</option>
								<option value="VERIFY_SCREEN" ${step.action_type === "VERIFY_SCREEN" ? "selected" : ""}>VERIFY_SCREEN</option>
								<option value="FOCUS_WINDOW" ${step.action_type === "FOCUS_WINDOW" ? "selected" : ""}>FOCUS_WINDOW</option>
								<option value="CALL_SKILL" ${step.action_type === "CALL_SKILL" ? "selected" : ""}>CALL_SKILL</option>
							</select>
						</div>
					</div>

					${
						step.action_type === "FOCUS_WINDOW"
							? `
						<div class="form-group" style="margin:0; margin-top:10px;">
							<label class="doc-editor-label">Window Title Pattern</label>
							<input type="text" class="doc-editor-input" value="${escapeHtml(step.window_title || "")}" placeholder="e.g. Remote Desktop*" onchange="currentEditingSteps[${idx}].window_title = this.value" />
						</div>
					`
							: ""
					}

					${
						step.action_type === "CALL_SKILL"
							? `
						<div class="form-group" style="margin:0; margin-top:10px;">
							<label class="doc-editor-label">Sub-Skill ID</label>
							<input type="text" class="doc-editor-input" value="${escapeHtml(step.skill_id || "")}" placeholder="e.g. rdp_login" onchange="currentEditingSteps[${idx}].skill_id = this.value" />
						</div>
					`
							: ""
					}

					${
						step.action_type === "TYPE_TEXT"
							? `
						<div class="form-group" style="margin:0; margin-top:10px;">
							<label class="doc-editor-label">Input Text / Placeholder</label>
							<input type="text" class="doc-editor-input" value="${escapeHtml(step.text || "")}" placeholder="e.g. {LastName}, {FirstName}" onchange="currentEditingSteps[${idx}].text = this.value" />
						</div>
					`
							: ""
					}

					${
						["CLICK", "DOUBLE_CLICK", "VERIFY_SCREEN"].includes(step.action_type)
							? `
						<div class="grid-2col" style="display: grid; grid-template-columns: 1fr 2fr; gap: 10px; margin-top: 10px; background: rgba(0,0,0,0.2); padding: 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.04);">
							<div class="form-group" style="margin:0;">
								<label class="doc-editor-label">Locator Type</label>
								<select class="doc-editor-input" onchange="if(!currentEditingSteps[${idx}].locator) currentEditingSteps[${idx}].locator={}; currentEditingSteps[${idx}].locator.type = this.value;">
									<option value="som_vlm" ${(step.locator && step.locator.type) === "som_vlm" ? "selected" : ""}>Set-of-Mark (Qwen3-VL)</option>
									<option value="ocr_exact" ${(step.locator && step.locator.type) === "ocr_exact" ? "selected" : ""}>OCR Exact Text</option>
									<option value="ocr_contains" ${(step.locator && step.locator.type) === "ocr_contains" ? "selected" : ""}>OCR Partial Text</option>
								</select>
							</div>
							<div class="form-group" style="margin:0;">
								<label class="doc-editor-label">Search Prompt / Value</label>
								<input type="text" class="doc-editor-input" value="${escapeHtml((step.locator && (step.locator.prompt || step.locator.value)) || "")}" placeholder="e.g. Button 'Search' or {LastName}" onchange="if(!currentEditingSteps[${idx}].locator) currentEditingSteps[${idx}].locator={}; currentEditingSteps[${idx}].locator.prompt = this.value; currentEditingSteps[${idx}].locator.value = this.value;" />
							</div>
						</div>
					`
							: ""
					}

					${
						step.action_type === "VERIFY_SCREEN"
							? `
						<div class="grid-2col" style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; background: rgba(245, 158, 11, 0.08); padding: 10px; border-radius: 6px; border: 1px solid rgba(245, 158, 11, 0.2);">
							<div class="form-group" style="margin:0;">
								<label class="doc-editor-label" style="color: #fbbf24;">On Success (Jump Target)</label>
								<select class="doc-editor-input" onchange="currentEditingSteps[${idx}].on_success = this.value;">
									<option value="">Next Step (Default)</option>
									${allStepIds.map((sId) => `<option value="${escapeHtml(sId)}" ${step.on_success === sId ? "selected" : ""}>Jump to ${escapeHtml(sId)}</option>`).join("")}
								</select>
							</div>
							<div class="form-group" style="margin:0;">
								<label class="doc-editor-label" style="color: #f87171;">On Failure (Jump Target)</label>
								<select class="doc-editor-input" onchange="currentEditingSteps[${idx}].on_failure = this.value;">
									<option value="">Next Step (Default)</option>
									${allStepIds.map((sId) => `<option value="${escapeHtml(sId)}" ${step.on_failure === sId ? "selected" : ""}>Jump to ${escapeHtml(sId)}</option>`).join("")}
								</select>
							</div>
						</div>
					`
							: ""
					}
				</div>
			`;
		})
		.join("");
}

async function saveSkillFromEditor() {
	const skill_id = document.getElementById("editorSkillId").value.trim();
	const name = document.getElementById("editorSkillName").value.trim();
	const type = document.getElementById("editorSkillType").value;
	const description = document.getElementById("editorSkillDesc").value.trim();
	const allowedExtsRaw = (document.getElementById("editorSkillAllowedExtensions") || {}).value || "";
	const allowedExtensions = allowedExtsRaw
		? allowedExtsRaw
				.split(",")
				.map((s) => s.trim().toLowerCase())
				.filter(Boolean)
				.map((s) => (s.startsWith(".") ? s : "." + s))
		: [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"];

	const target_window = document.getElementById("editorSkillTargetWindow").value.trim();
	const rdp_path_prefix = document.getElementById("editorSkillRdpPrefix").value.trim();
	const docTypesRaw = document.getElementById("editorSkillDocTypes").value.trim();
	const docTypes = docTypesRaw
		? docTypesRaw
				.split(",")
				.map((s) => s.trim())
				.filter(Boolean)
		: ["*"];
	const uploadMode = document.getElementById("editorSkillUploadMode").value;

	if (!skill_id || !name) {
		toast("Please provide Skill ID and Name.", "error");
		return;
	}

	const payload = {
		id: skill_id,
		name: name,
		type: type,
		description: description,
		enabled: true,
	};

	if (type === "import") {
		payload.allowed_extensions = allowedExtensions;
		payload.split_multi_documents = document.getElementById("editorSkillSplitMulti") ? document.getElementById("editorSkillSplitMulti").checked : true;
		payload.save_empty_pages = document.getElementById("editorSkillSaveEmpty") ? document.getElementById("editorSkillSaveEmpty").checked : false;
	} else {
		payload.target_window = target_window;
		payload.rdp_path_prefix = rdp_path_prefix;
		payload.document_types = docTypes;
		payload.upload_mode = uploadMode;
		payload.steps = currentEditingSteps;
	}

	try {
		await api("/api/skills", {
			method: "POST",
			body: JSON.stringify(payload),
		});

		if (type === "import" && state.editingDocTypes) {
			await api(`/api/skills/${encodeURIComponent(skill_id)}/documents`, {
				method: "PUT",
				body: JSON.stringify({ document_types: state.editingDocTypes }),
			});
		}

		toast("Skill '" + name + "' successfully saved!");
		selectedSkillId = skill_id;
		await loadSkills();
	} catch (e) {
		toast("Error saving skill: " + e.message, "error");
	}
}

async function duplicateCurrentSkill() {
	if (!selectedSkillId) return;
	try {
		const res = await api(`/api/skills/${selectedSkillId}/duplicate`, {
			method: "POST",
		});
		toast("Skill duplicated: " + (res.skill ? res.skill.name : selectedSkillId));
		if (res.skill && res.skill.id) {
			selectedSkillId = res.skill.id;
		}
		loadSkills();
	} catch (e) {
		toast("Error duplicating skill: " + e.message, "error");
	}
}

async function deleteCurrentSkill() {
	if (!selectedSkillId) return;
	if (!confirm("Are you sure you want to delete this skill?")) return;
	try {
		await api(`/api/skills/${selectedSkillId}`, { method: "DELETE" });
		toast("Skill deleted.");
		selectedSkillId = null;
		loadSkills();
	} catch (e) {
		toast("Error deleting skill: " + e.message, "error");
	}
}

async function runCurrentSkillManual() {
	if (!selectedSkillId) return;
	try {
		await api("/api/skills/queue/add", {
			method: "POST",
			body: JSON.stringify({ skill_id: selectedSkillId, context: {} }),
		});
		toast("Skill added to queue!");
		renderQueueInspector();
	} catch (e) {
		toast("Error adding to queue: " + e.message, "error");
	}
}
