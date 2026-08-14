/* ═══════════════════════════════════════════════════════════
   SKILLS MANAGEMENT JS (Master-Detail Editor & Skill Queue Inspector)
   ═══════════════════════════════════════════════════════════ */

let selectedSkillId = null;
let currentEditingSkill = null;
let currentEditingSteps = [];
let activeInputField = null;
let skillsTabPollInterval = null;
let isNewSkillCreation = false;

function slugifySkillName(name) {
	if (!name) return "";
	return name
		.toLowerCase()
		.trim()
		.replace(/[^a-z0-9_]+/g, "_")
		.replace(/^_+|_+$/g, "");
}

function onSkillNameInput(val) {
	document.getElementById("skillHeaderTitle").textContent = val.trim() || "Untitled Workflow";
	if (isNewSkillCreation) {
		const slug = slugifySkillName(val) || "custom_skill";
		const idInput = document.getElementById("editorSkillId");
		if (idInput) {
			idInput.value = slug;
		}
		if (currentEditingSkill) {
			currentEditingSkill.id = slug;
		}
	}
}

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
		toast("Error loading skills: " + e.message, "error");
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
				${searchQuery ? "No matches" : "No skills found"}
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
			const badgeText = isImport ? "Import" : `${stepCount} ${stepCount === 1 ? "step" : "steps"}`;

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
	isNewSkillCreation = false;

	renderSkillsSidebar(state.skills || []);

	const emptyMsg = document.getElementById("noSkillSelectedMessage");
	const wrapper = document.getElementById("skillFormWrapper");
	if (emptyMsg) emptyMsg.style.display = "none";
	if (wrapper) wrapper.style.display = "flex";

	document.getElementById("skillHeaderTitle").textContent = skillObj.name || skillObj.id;
	const isImport = skillObj.type === "import";
	document.getElementById("skillHeaderBadge").textContent = isImport ? "Import Skill" : `${currentEditingSteps.length} ${currentEditingSteps.length === 1 ? "step" : "steps"}`;

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
	renderVariableBadges();

	// Update Batch Run Button text with pending count
	if (!isImport) {
		updateBatchRunBadge(skillId);
	}

	renderQueueInspector();

	if (!skillsTabPollInterval) {
		skillsTabPollInterval = setInterval(() => {
			const activeTab = document.querySelector(".nav-item.active")?.dataset?.tab;
			if (activeTab === "skills") {
				renderQueueInspector();
			}
		}, 3000);
	}
}

async function updateBatchRunBadge(skillId) {
	try {
		const res = await api(`/api/skills/${encodeURIComponent(skillId)}/pending_cases`);
		const btn = document.getElementById("btnRunSkillBatch");
		if (btn) {
			const count = res.count || 0;
			btn.innerHTML = `▶ Batch Run (${count} ${count === 1 ? "case" : "cases"})`;
			btn.title = `${count} approved case folder(s) pending for this export skill`;
		}
	} catch (e) {
		console.debug("Could not fetch pending count for skill:", e);
	}
}

function renderVariableBadges() {
	const container = document.getElementById("variableBadges");
	if (!container) return;

	const dynamicVars = new Set();
	dynamicVars.add("{document_fullpath}");

	// Extract variables from configured folder structure (e.g. {Datum}, {Produkt}, {Person})
	if (state.config && Array.isArray(state.config.folder_structure)) {
		state.config.folder_structure.forEach((part) => {
			const cleaned = String(part).trim();
			if (cleaned) {
				const formatted = cleaned.startsWith("{") && cleaned.endsWith("}") ? cleaned : `{${cleaned}}`;
				dynamicVars.add(formatted);
			}
		});
	}

	// Extract variables from configured document extraction fields
	if (state.config && state.config.document_types) {
		Object.values(state.config.document_types).forEach((doc) => {
			if (doc && doc.extraction_fields) {
				Object.keys(doc.extraction_fields).forEach((f) => {
					dynamicVars.add(`{${f}}`);
				});
			}
		});
	}

	if (dynamicVars.size === 0) {
		container.innerHTML = `<span style="font-size:0.75rem; color:var(--text-dim);">No variables configured.</span>`;
		return;
	}

	container.innerHTML = Array.from(dynamicVars)
		.map(
			(v) => `
			<span class="badge variable-badge" onclick="insertVariable('${escapeHtml(v)}')" title="Click to insert into active input field">
				${escapeHtml(v)}
			</span>
		`
		)
		.join("");
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
				No categories defined in this skill.
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
						${fieldCount} ${fieldCount === 1 ? "field" : "fields"}
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
			Document: { description: "Category of the document", required: true }
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
						<textarea class="doc-editor-textarea auto-resize-ta" rows="1" placeholder="Description for the AI..." oninput="autoResizeTextarea(this)" onchange="updateDocTypeField('${escapeHtml(typeName)}', '${escapeHtml(fKey)}', 'desc', this.value)" style="resize: none; overflow: hidden; min-height: 38px;">${escapeHtml(desc)}</textarea>
					</td>
					<td style="padding: 10px 12px; vertical-align: top; text-align: center;">
						<input type="checkbox" ${req ? "checked" : ""} onchange="updateDocTypeField('${escapeHtml(typeName)}', '${escapeHtml(fKey)}', 'req', this.checked)" style="width: 18px; height: 18px; accent-color: #6366f1; cursor: pointer; margin-top: 8px;" />
					</td>
					<td style="padding: 10px 12px; vertical-align: top; text-align: center;">
						<button class="btn btn-sm btn-danger" onclick="removeExtractionField('${escapeHtml(typeName)}', '${escapeHtml(fKey)}')" title="Remove field" style="padding: 6px 10px; margin-top: 4px;">🗑️</button>
					</td>
				</tr>
			`;
		})
		.join("");

	let tableHtml = `
		<table class="doc-fields-table" style="width: 100%; border-collapse: separate; border-spacing: 0; background: rgba(10, 13, 20, 0.5); border-radius: 10px; border: 1px solid rgba(255,255,255,0.08); overflow: hidden;">
			<thead>
				<tr style="background: rgba(255, 255, 255, 0.03); color: var(--text-dim); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em;">
					<th style="padding: 12px; text-align: left; width: 22%; border-bottom: 1px solid rgba(255,255,255,0.08);">Field name</th>
					<th style="padding: 12px; text-align: left; width: 60%; border-bottom: 1px solid rgba(255,255,255,0.08);">Extraction prompt / Instruction</th>
					<th style="padding: 12px; text-align: center; width: 10%; border-bottom: 1px solid rgba(255,255,255,0.08);">Required</th>
					<th style="padding: 12px; text-align: center; width: 8%; border-bottom: 1px solid rgba(255,255,255,0.08);">Action</th>
				</tr>
			</thead>
			<tbody>
				${tableRowsHtml}
			</tbody>
		</table>
	`;

	if (fieldKeys.length === 0) {
		tableHtml = `<div style="padding: 20px; color: var(--text-dim); font-size: 0.85rem; text-align: center; background: rgba(0,0,0,0.15); border-radius: 8px;">No extraction fields defined.</div>`;
	}

	container.innerHTML = `
		<div class="doc-form-header-card">
			<div class="doc-form-header-title">
				<div class="doc-form-header-emoji">${emoji}</div>
				<div>
					<h3 style="margin: 0; font-size: 1.15rem; font-weight: 700; color: var(--text);">${escapeHtml(typeName)}</h3>
					<span style="font-size: 0.78rem; color: var(--text-dim);">${fieldKeys.length} extraction fields configured</span>
				</div>
			</div>
			<button class="btn btn-sm btn-danger" onclick="deleteDocType('${escapeHtml(typeName)}')">🗑️ Delete Category</button>
		</div>

		<div class="doc-editor-section" style="margin-top: 16px;">
			<h4>🧠 Recognition & Classification Rules (AI Vision)</h4>
			<span style="font-size: 0.8rem; color: var(--text-dim); margin-top: -8px; margin-bottom: 6px; display: block;">
				Define the visual, text, or layout features the AI uses to recognize this document.
			</span>
			<textarea class="doc-editor-textarea auto-resize-ta" rows="2" placeholder="E.g. Document containing the text 'Report' in the header area..." oninput="autoResizeTextarea(this)" onchange="updateDocTypeRules('${escapeHtml(typeName)}', this.value)" style="resize: none; overflow: hidden; min-height: 52px;">${escapeHtml(descValue)}</textarea>
		</div>

		<div class="doc-editor-section" style="margin-top: 16px;">
			<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
				<h4 style="margin: 0;">📋 Extraction Fields & AI Prompts</h4>
				<button class="btn btn-sm btn-accent" onclick="addExtractionField('${escapeHtml(typeName)}')">➕ Add Field</button>
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
	const key = prompt("Field key name (e.g. InvoiceNumber, Date, Total):");
	if (!key || !key.trim()) return;

	const cleanKey = key.trim();
	if (!state.editingDocTypes || !state.editingDocTypes[typeName]) return;
	const fields = state.editingDocTypes[typeName].extraction_fields || {};

	if (fields[cleanKey]) {
		toast("Field already exists.", "error");
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
   EDITOR ACTIONS & STEPS
   ═══════════════════════════════════════════════════════════ */

function createNewSkill() {
	isNewSkillCreation = true;
	const baseName = "New Workflow";
	let slug = slugifySkillName(baseName);
	const existingIds = new Set((state.skills || []).map((s) => s.id));
	let counter = 2;
	while (existingIds.has(slug)) {
		slug = `${slugifySkillName(baseName)}_${counter}`;
		counter++;
	}

	const newSkill = {
		id: slug,
		name: counter > 2 ? `${baseName} ${counter - 1}` : baseName,
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

	selectedSkillId = newSkill.id;
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
	renderVariableBadges();
	renderQueueInspector();

	// Focus and select skill name input so the user can type immediately
	const nameInput = document.getElementById("editorSkillName");
	if (nameInput) {
		nameInput.focus();
		nameInput.select();
	}
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
		toast("Click into an input field first to insert a variable.", "info");
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
		badge.textContent = `${stepCount} ${stepCount === 1 ? "step" : "steps"}`;
	}
}

function getActionBadgeStyle(actionType) {
	switch (actionType) {
		case "FOCUS_WINDOW":
			return { label: "🪟 FOCUS WINDOW", bg: "rgba(99, 102, 241, 0.2)", color: "#a5b4fc", border: "rgba(99, 102, 241, 0.4)" };
		case "CLICK":
			return { label: "🎯 CLICK", bg: "rgba(16, 185, 129, 0.2)", color: "#34d399", border: "rgba(16, 185, 129, 0.4)" };
		case "DOUBLE_CLICK":
			return { label: "🖱️ DOUBLE CLICK", bg: "rgba(16, 185, 129, 0.3)", color: "#6ee7b7", border: "rgba(16, 185, 129, 0.5)" };
		case "TYPE_TEXT":
			return { label: "⌨️ TYPE TEXT", bg: "rgba(245, 158, 11, 0.2)", color: "#fbbf24", border: "rgba(245, 158, 11, 0.4)" };
		case "TYPE_FILE_PATH":
			return { label: "📄 FILE PATH", bg: "rgba(236, 72, 153, 0.2)", color: "#f472b6", border: "rgba(236, 72, 153, 0.4)" };
		case "VERIFY_SCREEN":
			return { label: "👁️ VERIFY SCREEN", bg: "rgba(168, 85, 247, 0.2)", color: "#c084fc", border: "rgba(168, 85, 247, 0.4)" };
		case "CALL_SKILL":
			return { label: "⚡ SUB SKILL", bg: "rgba(14, 165, 233, 0.2)", color: "#38bdf8", border: "rgba(14, 165, 233, 0.4)" };
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
				No steps defined for this skill. Click "+ Add step" above.
			</div>
		`;
		return;
	}

	container.innerHTML = currentEditingSteps
		.map((step, idx) => {
			const badgeStyle = getActionBadgeStyle(step.action_type);
			const isFirst = idx === 0;
			const isLast = idx === currentEditingSteps.length - 1;
			const targetVal = (step.locator && (step.locator.prompt || step.locator.value || step.locator.target)) || "";

			let actionSpecificHtml = "";

			if (["CLICK", "DOUBLE_CLICK"].includes(step.action_type)) {
				actionSpecificHtml = `
					<div class="form-group" style="margin-top: 10px;">
						<label class="doc-editor-label">🎯 Target Element / Button Text (or {Variable})</label>
						<input type="text" class="doc-editor-input" value="${escapeHtml(targetVal)}" placeholder="e.g. 'Search' button or {LastName}" onchange="if(!currentEditingSteps[${idx}].locator) currentEditingSteps[${idx}].locator={}; currentEditingSteps[${idx}].locator.prompt = this.value; currentEditingSteps[${idx}].locator.value = this.value; currentEditingSteps[${idx}].locator.type = 'auto';" />
					</div>
				`;
			} else if (step.action_type === "TYPE_TEXT") {
				actionSpecificHtml = `
					<div style="display: grid; grid-template-columns: 1fr auto; gap: 14px; align-items: end; margin-top: 10px;">
						<div class="form-group" style="margin: 0;">
							<label class="doc-editor-label">⌨️ Text or Variables to type</label>
							<input type="text" class="doc-editor-input" value="${escapeHtml(step.text || "")}" placeholder="e.g. {LastName}, {BirthDate}" onchange="currentEditingSteps[${idx}].text = this.value" />
						</div>
						<label style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px; cursor: pointer; font-size: 0.82rem; color: var(--text-dim); user-select: none;">
							<input type="checkbox" ${step.press_enter ? "checked" : ""} onchange="currentEditingSteps[${idx}].press_enter = this.checked;" style="width: 16px; height: 16px; accent-color: #6366f1; cursor: pointer;" />
							Press Enter after typing
						</label>
					</div>
				`;
			} else if (step.action_type === "TYPE_FILE_PATH") {
				actionSpecificHtml = `
					<div style="display: grid; grid-template-columns: 1fr auto; gap: 14px; align-items: end; margin-top: 10px;">
						<div class="form-group" style="margin: 0;">
							<label class="doc-editor-label">📄 File Path Placeholder</label>
							<input type="text" class="doc-editor-input" value="${escapeHtml(step.file_path || "{document_fullpath}")}" placeholder="{document_fullpath}" onchange="currentEditingSteps[${idx}].file_path = this.value" />
						</div>
						<label style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px; cursor: pointer; font-size: 0.82rem; color: var(--text-dim); user-select: none;">
							<input type="checkbox" ${step.press_enter !== false ? "checked" : ""} onchange="currentEditingSteps[${idx}].press_enter = this.checked;" style="width: 16px; height: 16px; accent-color: #6366f1; cursor: pointer;" />
							Press Enter after path
						</label>
					</div>
				`;
			} else if (step.action_type === "VERIFY_SCREEN") {
				const failureAction = step.on_failure_action || (step.on_failure_skill ? "run_skill" : "skip");
				const availableRoutines = (state.skills || []).filter((s) => s.type !== "import" && s.id !== selectedSkillId);

				actionSpecificHtml = `
					<div class="form-group" style="margin-top: 10px;">
						<label class="doc-editor-label" style="color: #c084fc;">👁️ Element or Text that must appear on screen</label>
						<input type="text" class="doc-editor-input" value="${escapeHtml(targetVal)}" placeholder="e.g. 'Patient Profile' or 'Saved successfully'" onchange="if(!currentEditingSteps[${idx}].locator) currentEditingSteps[${idx}].locator={}; currentEditingSteps[${idx}].locator.prompt = this.value; currentEditingSteps[${idx}].locator.value = this.value; currentEditingSteps[${idx}].locator.type = 'auto';" />
					</div>

					<div style="margin-top: 10px; background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.06); padding: 12px; border-radius: 8px;">
						<label class="doc-editor-label" style="color: #fbbf24; margin-bottom: 6px;">❓ What to do if NOT found on screen?</label>
						<div class="grid-2col" style="display: grid; grid-template-columns: 1.2fr 2fr; gap: 10px; align-items: center;">
							<select class="doc-editor-input" onchange="currentEditingSteps[${idx}].on_failure_action = this.value; renderEditorSteps();">
								<option value="run_skill" ${failureAction === "run_skill" ? "selected" : ""}>⚡ Run Routine Workflow</option>
								<option value="pause_prompt" ${failureAction === "pause_prompt" ? "selected" : ""}>🔔 Pause & Alert Human</option>
								<option value="skip" ${failureAction === "skip" ? "selected" : ""}>⏭️ Skip this Case</option>
							</select>

							${
								failureAction === "run_skill"
									? `
								<div style="display: flex; gap: 6px; align-items: center;">
									<select class="doc-editor-input" style="flex: 1;" onchange="currentEditingSteps[${idx}].on_failure_skill = this.value;">
										<option value="">-- Select Routine Workflow --</option>
										${availableRoutines.map((r) => `<option value="${escapeHtml(r.id)}" ${step.on_failure_skill === r.id ? "selected" : ""}>${escapeHtml(r.name || r.id)}</option>`).join("")}
									</select>
									<button type="button" class="btn btn-sm btn-secondary" onclick="createRoutineInlineForStep(${idx}, true)" style="white-space: nowrap; padding: 5px 10px; font-size: 0.78rem;" title="Create new routine">➕ New</button>
								</div>
							`
									: `
								<div style="font-size: 0.8rem; color: var(--text-dim);">
									${failureAction === "pause_prompt" ? "Sounds an alert and pauses execution for human assistance." : "Safely aborts this file and marks it for review."}
								</div>
							`
							}
						</div>
					</div>
				`;
			} else if (step.action_type === "FOCUS_WINDOW") {
				actionSpecificHtml = `
					<div class="form-group" style="margin-top: 10px;">
						<label class="doc-editor-label">🪟 Target Window Title (Regex or Wildcard)</label>
						<input type="text" class="doc-editor-input" value="${escapeHtml(step.window_title || "Remote Desktop*")}" placeholder="e.g. Remote Desktop*" onchange="currentEditingSteps[${idx}].window_title = this.value" />
					</div>
				`;
			} else if (step.action_type === "CALL_SKILL") {
				const availableRoutines = (state.skills || []).filter((s) => s.type !== "import" && s.id !== selectedSkillId);
				actionSpecificHtml = `
					<div class="form-group" style="margin-top: 10px;">
						<label class="doc-editor-label">⚡ Routine Workflow to run</label>
						<div style="display: flex; gap: 8px; align-items: center;">
							<select class="doc-editor-input" style="flex: 1;" onchange="currentEditingSteps[${idx}].skill_id = this.value;">
								<option value="">-- Select Routine Workflow --</option>
								${availableRoutines.map((r) => `<option value="${escapeHtml(r.id)}" ${step.skill_id === r.id ? "selected" : ""}>${escapeHtml(r.name || r.id)}</option>`).join("")}
							</select>
							<button type="button" class="btn btn-sm btn-secondary" onclick="createRoutineInlineForStep(${idx}, false)" style="white-space: nowrap; padding: 5px 10px; font-size: 0.78rem;" title="Create new routine">➕ New</button>
						</div>
					</div>
				`;
			}

			return `
				<div class="doc-editor-section" style="background: rgba(10, 13, 20, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); padding: 14px 16px; margin-bottom: 10px; border-radius: 10px;">
					<!-- Step Header -->
					<div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px; margin-bottom: 12px;">
						<div style="display: flex; align-items: center; gap: 10px;">
							<span style="font-size: 0.82rem; font-weight: 700; color: var(--text-dim);">#${idx + 1}</span>
							<span class="badge" style="background: ${badgeStyle.bg}; color: ${badgeStyle.color}; border: 1px solid ${badgeStyle.border}; font-weight: 700; font-size: 0.72rem;">
								${badgeStyle.label}
							</span>
							<code style="font-size: 0.75rem; color: var(--text-dim); opacity: 0.7;">${escapeHtml(step.id)}</code>
						</div>
						<div style="display: flex; align-items: center; gap: 6px;">
							<button type="button" class="btn btn-sm btn-icon" onclick="moveStepUp(${idx})" ${isFirst ? "disabled style='opacity:0.3'" : ""} title="Move up">⬆️</button>
							<button type="button" class="btn btn-sm btn-icon" onclick="moveStepDown(${idx})" ${isLast ? "disabled style='opacity:0.3'" : ""} title="Move down">⬇️</button>
							<button type="button" class="btn btn-sm btn-danger" onclick="removeEditorStep(${idx})" style="padding: 3px 8px; font-size: 0.75rem;" title="Remove step">🗑️</button>
						</div>
					</div>

					<!-- Primary Action & Description -->
					<div class="grid-2col" style="display: grid; grid-template-columns: 1.1fr 2fr; gap: 12px;">
						<div class="form-group" style="margin:0;">
							<label class="doc-editor-label">Action Type</label>
							<select class="doc-editor-input" onchange="currentEditingSteps[${idx}].action_type = this.value; renderEditorSteps();">
								<option value="CLICK" ${step.action_type === "CLICK" ? "selected" : ""}>🎯 Click Element</option>
								<option value="DOUBLE_CLICK" ${step.action_type === "DOUBLE_CLICK" ? "selected" : ""}>🖱️ Double-Click Element</option>
								<option value="TYPE_TEXT" ${step.action_type === "TYPE_TEXT" ? "selected" : ""}>⌨️ Type Text / Variables</option>
								<option value="TYPE_FILE_PATH" ${step.action_type === "TYPE_FILE_PATH" ? "selected" : ""}>📄 Enter File Path</option>
								<option value="VERIFY_SCREEN" ${step.action_type === "VERIFY_SCREEN" ? "selected" : ""}>👁️ Wait / Verify Screen</option>
								<option value="FOCUS_WINDOW" ${step.action_type === "FOCUS_WINDOW" ? "selected" : ""}>🪟 Focus Window</option>
								<option value="CALL_SKILL" ${step.action_type === "CALL_SKILL" ? "selected" : ""}>⚡ Call Sub-Skill</option>
							</select>
						</div>
						<div class="form-group" style="margin:0;">
							<label class="doc-editor-label">Description (Optional)</label>
							<input type="text" class="doc-editor-input" value="${escapeHtml(step.description || "")}" placeholder="e.g. Click search field" onchange="currentEditingSteps[${idx}].description = this.value" />
						</div>
					</div>

					<!-- Action Specific Fields -->
					${actionSpecificHtml}

					<!-- Inline AI Step Refinement -->
					<div style="margin-top: 12px; display: flex; gap: 8px; align-items: center; background: rgba(99,102,241,0.06); border: 1px dashed rgba(99,102,241,0.25); border-radius: 8px; padding: 6px 10px;">
						<span style="font-size: 0.85rem; user-select: none;" title="AI Step Assistant">✨</span>
						<input type="text" id="aiRefineInput_${idx}" class="doc-editor-input" style="flex: 1; height: 30px; font-size: 0.8rem; background: transparent; border: none; padding: 0 4px;" placeholder="Adjust step with AI: e.g. 'Type {LastName} and press Enter' or 'Click search button'" onkeydown="if(event.key==='Enter') refineStepWithAI(${idx})" />
						<button type="button" class="btn btn-sm btn-accent" style="padding: 3px 10px; font-size: 0.75rem; white-space: nowrap;" onclick="refineStepWithAI(${idx})">✨ Refine</button>
					</div>
				</div>
			`;
		})
		.join("");
}

async function refineStepWithAI(idx) {
	const inputEl = document.getElementById(`aiRefineInput_${idx}`);
	if (!inputEl) return;
	const instruction = inputEl.value.trim();
	if (!instruction) {
		toast("Please enter an instruction for the AI.", "info");
		return;
	}

	const currentStep = currentEditingSteps[idx];
	try {
		toast("✨ Refining step with AI...", "info");
		const res = await api("/api/skills/refine_step", {
			method: "POST",
			body: JSON.stringify({ instruction: instruction, step: currentStep }),
		});

		if (res.status === "ok" && res.step) {
			currentEditingSteps[idx] = res.step;
			renderEditorSteps();
			toast("Step updated by AI!", "success");
		}
	} catch (e) {
		toast("Error refining step: " + e.message, "error");
	}
}

async function createRoutineInlineForStep(idx, isFallback = true) {
	const defaultName = "New Routine";
	const name = prompt("Enter a name for the new routine workflow:", defaultName);
	if (!name || !name.trim()) return;

	const cleanName = name.trim();
	const slug = slugifySkillName(cleanName) || `routine_${Date.now()}`;

	const newSkill = {
		id: slug,
		name: cleanName,
		type: "export",
		description: "Sub-routine workflow",
		target_window: (currentEditingSkill && currentEditingSkill.target_window) || "Remote Desktop*",
		rdp_path_prefix: (currentEditingSkill && currentEditingSkill.rdp_path_prefix) || "\\\\tsclient\\C",
		document_types: ["*"],
		upload_mode: "single_file",
		enabled: true,
		steps: [
			{
				id: "step_1",
				description: "Focus Window",
				action_type: "FOCUS_WINDOW",
				window_title: (currentEditingSkill && currentEditingSkill.target_window) || "Remote Desktop*",
			},
		],
	};

	try {
		await api("/api/skills", {
			method: "POST",
			body: JSON.stringify(newSkill),
		});

		toast(`Routine '${cleanName}' created!`, "success");
		await loadSkills();

		if (isFallback) {
			currentEditingSteps[idx].on_failure_action = "run_skill";
			currentEditingSteps[idx].on_failure_skill = slug;
		} else {
			currentEditingSteps[idx].skill_id = slug;
		}
		renderEditorSteps();
	} catch (e) {
		toast("Error creating routine: " + e.message, "error");
	}
}

async function saveSkillFromEditor() {
	let skill_id = document.getElementById("editorSkillId").value.trim();
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

	if (!name) {
		toast("Please enter a skill name.", "error");
		return;
	}

	if (!skill_id) {
		skill_id = slugifySkillName(name) || "custom_skill";
		document.getElementById("editorSkillId").value = skill_id;
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
		const res = await api("/api/skills", {
			method: "POST",
			body: JSON.stringify(payload),
		});

		const finalId = (res && res.skill_id) || skill_id;

		if (type === "import" && state.editingDocTypes) {
			await api(`/api/skills/${encodeURIComponent(finalId)}/documents`, {
				method: "PUT",
				body: JSON.stringify({ document_types: state.editingDocTypes }),
			});
		}

		toast("Skill '" + name + "' saved successfully!");
		isNewSkillCreation = false;
		selectedSkillId = finalId;
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

async function runCurrentSkillBatch() {
	if (!selectedSkillId) return;
	try {
		const res = await api(`/api/skills/${encodeURIComponent(selectedSkillId)}/run_batch`, {
			method: "POST",
		});

		if (res.status === "no_pending_cases" || res.queued_count === 0) {
			toast("No pending approved cases found for this skill.", "info");
		} else {
			toast(`🚀 ${res.queued_count} approved cases added to queue!`, "success");
		}
		renderQueueInspector();
		updateBatchRunBadge(selectedSkillId);
	} catch (e) {
		toast("Error during batch run: " + e.message, "error");
	}
}

async function previewSkillWindow() {
	const winTitle = document.getElementById("editorSkillTargetWindow")?.value || "Remote Desktop*";
	try {
		toast("📷 Capturing screenshot of: " + winTitle, "info");
		const res = await api("/api/skills/screenshot_preview", {
			method: "POST",
			body: JSON.stringify({ window_title: winTitle }),
		});

		if (res.image) {
			const w = window.open("", "_blank");
			if (w) {
				w.document.write(`
					<html>
						<head><title>Screenshot Preview - ${escapeHtml(winTitle)}</title></head>
						<body style="margin:0; background:#0b0f19; display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:100vh; font-family:sans-serif; color:#fff;">
							<div style="padding:12px 20px; background:rgba(255,255,255,0.08); border-radius:8px; margin-bottom:12px;">
								<strong>Target window:</strong> ${escapeHtml(winTitle)}
							</div>
							<img src="${res.image}" style="max-width:95vw; max-height:85vh; border:2px solid #6366f1; border-radius:8px; box-shadow:0 10px 30px rgba(0,0,0,0.8);" />
						</body>
					</html>
				`);
			}
		}
	} catch (e) {
		toast("Screenshot capture failed: " + e.message, "error");
	}
}
