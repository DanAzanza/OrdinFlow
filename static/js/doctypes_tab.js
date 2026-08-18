/* ═══════════════════════════════════════════════════════════
   DOCUMENT TYPES & EXTRACTION FIELDS EDITOR (Import Skills)
   ═══════════════════════════════════════════════════════════ */

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
	let itemsHtml = "";

	if (keys.length === 0) {
		itemsHtml = `
			<div class="empty-categories-box">
				No categories defined yet.
			</div>
		`;
	} else {
		itemsHtml = keys
			.map((key) => {
				const isSelected = key === state.selectedDocType;
				const doc = state.editingDocTypes[key] || {};
				const emoji = doc.emoji || "📄";
				const fieldCount = Object.keys(doc.extraction_fields || {}).length;

				return `
					<div class="category-item ${isSelected ? "active" : ""}" onclick="selectDocType('${escapeHtml(key)}')">
						<div class="category-item-name">
							<span class="category-emoji">${emoji}</span>
							<span class="category-label" title="${escapeHtml(key)}">
								${escapeHtml(key)}
							</span>
						</div>
						<span class="category-item-count">
							${fieldCount} ${fieldCount === 1 ? "field" : "fields"}
						</span>
					</div>
				`;
			})
			.join("");
	}

	container.innerHTML = `
		${itemsHtml}
		<button type="button" class="btn btn-sm btn-primary add-category-btn" onclick="createNewDocType()">
			<span>➕</span> Add type
		</button>
	`;
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
	el.style.height = Math.max(34, el.scrollHeight + 2) + "px";
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
				<tr class="doc-field-row">
					<td class="doc-field-name-td">
						<input type="text" class="doc-editor-input doc-field-key-input" value="${escapeHtml(fKey)}" readonly />
					</td>
					<td class="doc-field-prompt-td">
						<textarea class="doc-editor-textarea auto-resize-ta" rows="1" placeholder="Prompt for the AI..." oninput="autoResizeTextarea(this)" onchange="updateDocTypeField('${escapeHtml(typeName)}', '${escapeHtml(fKey)}', 'desc', this.value)">${escapeHtml(desc)}</textarea>
					</td>
					<td class="doc-field-req-td">
						<input type="checkbox" class="config-checkbox" ${req ? "checked" : ""} onchange="updateDocTypeField('${escapeHtml(typeName)}', '${escapeHtml(fKey)}', 'req', this.checked)" />
					</td>
					<td class="doc-field-act-td">
						<button type="button" class="btn btn-sm btn-danger" onclick="removeExtractionField('${escapeHtml(typeName)}', '${escapeHtml(fKey)}')" title="Remove field">🗑️</button>
					</td>
				</tr>
			`;
		})
		.join("");

	let tableHtml = `
		<table class="doc-fields-table">
			<thead>
				<tr>
					<th class="table-col-name">Field Name</th>
					<th class="table-col-prompt">Extraction Prompt / Instruction</th>
					<th class="table-col-req">Required</th>
					<th class="table-col-act">Action</th>
				</tr>
			</thead>
			<tbody>
				${tableRowsHtml}
			</tbody>
		</table>
	`;

	if (fieldKeys.length === 0) {
		tableHtml = `<div class="empty-fields-box">No extraction fields defined yet. Click '➕ Add Field' below to configure fields.</div>`;
	}

	container.innerHTML = `
		<div class="doc-form-header-card">
			<div class="doc-form-header-title">
				<div class="doc-form-header-emoji">${emoji}</div>
				<div>
					<h3 class="doc-header-name">${escapeHtml(typeName)}</h3>
				</div>
			</div>
			<button type="button" class="btn btn-sm btn-danger" onclick="deleteDocType('${escapeHtml(typeName)}')">🗑️ Delete Category</button>
		</div>

		<div class="doc-editor-section">
			<h4>🧠 Recognition & Classification Rules (AI Vision)</h4>
			<span class="doc-field-hint">
				Define the visual, text, or layout features the AI uses to recognize this document.
			</span>
			<textarea class="doc-editor-textarea auto-resize-ta" rows="2" placeholder="E.g. Document containing the text 'Report' in the header area..." oninput="autoResizeTextarea(this)" onchange="updateDocTypeRules('${escapeHtml(typeName)}', this.value)">${escapeHtml(descValue)}</textarea>
		</div>

		<div class="doc-editor-section">
			<div class="doc-section-header-row">
				<h4>📋 Extraction Fields & AI Prompts</h4>
				<button type="button" class="btn btn-sm btn-accent" onclick="addExtractionField('${escapeHtml(typeName)}')">➕ Add Field</button>
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
