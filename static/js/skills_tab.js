/* ═══════════════════════════════════════════════════════════
   SKILLS MANAGEMENT JS (Master-Detail Editor & Skill Queue Inspector)
   ═══════════════════════════════════════════════════════════ */

let selectedSkillId = null;
let currentEditingSkill = null;
let currentEditingSteps = [];
let activeInputField = null;
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
	const headerTitle = document.getElementById("skillHeaderTitle");
	if (headerTitle) {
		headerTitle.textContent = val.trim() || "Untitled Workflow";
	}
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

async function loadSkills(forceRefresh = false) {
	if (state.skills && state.skills.length > 0 && !forceRefresh) {
		renderSkillsSidebar(state.skills);
		if (selectedSkillId) {
			const found = state.skills.find((s) => s.id === selectedSkillId);
			if (found) {
				selectSkill(selectedSkillId);
			} else if (state.skills.length > 0) {
				selectSkill(state.skills[0].id);
			}
		} else if (state.skills.length > 0) {
			selectSkill(state.skills[0].id);
		}
	}

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
		if (!state.skills || state.skills.length === 0) {
			toast("Error loading skills: " + e.message, "error");
		}
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

	let itemsHtml = "";
	if (skills.length === 0) {
		itemsHtml = `
			<div class="skills-empty-note">
				${searchQuery ? "No matches" : "No skills found"}
			</div>
		`;
	} else {
		itemsHtml = skills
			.map((skill) => {
				const isSelected = skill.id === selectedSkillId;
				const isImport = skill.type === "import";
				const icon = isImport ? "📥" : "⚡";

				return `
					<div class="doc-type-item ${isSelected ? "active" : ""}" onclick="selectSkill('${escapeHtml(skill.id)}')">
						<div class="doc-type-item-name">
							<span class="skill-emoji">${icon}</span>
							<span class="skill-label" title="${escapeHtml(skill.name || skill.id)}">
								${escapeHtml(skill.name || skill.id)}
							</span>
						</div>
						<div class="skill-item-actions">
							<button type="button" class="btn-icon-subtle" onclick="event.stopPropagation(); duplicateSkillById('${escapeHtml(skill.id)}')" title="Duplicate skill">
								📋
							</button>
							<button type="button" class="btn-icon-subtle btn-icon-danger" onclick="event.stopPropagation(); deleteSkillById('${escapeHtml(skill.id)}')" title="Delete skill">
								🗑️
							</button>
						</div>
					</div>
				`;
			})
			.join("");
	}

	container.innerHTML = `
		${itemsHtml}
		<button type="button" class="btn btn-sm btn-primary add-skill-btn" onclick="openCreateSkillModal()">
			<span>➕</span> Add Skill
		</button>
	`;
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
	if (Array.isArray(skillObj.tasks) && skillObj.tasks.length > 0) {
		currentEditingTasks = JSON.parse(JSON.stringify(skillObj.tasks));
	} else if (Array.isArray(skillObj.steps) && skillObj.steps.length > 0) {
		currentEditingTasks = [
			{
				id: "task_1",
				title: "Arbeitsablauf ausführen",
				actions: JSON.parse(JSON.stringify(skillObj.steps)),
			},
		];
	} else {
		currentEditingTasks = [];
	}
	isNewSkillCreation = false;

	renderSkillsSidebar(state.skills || []);

	const emptyMsg = document.getElementById("noSkillSelectedMessage");
	const wrapper = document.getElementById("skillFormWrapper");
	if (emptyMsg) emptyMsg.style.display = "none";
	if (wrapper) wrapper.style.display = "block";

	const headerTitle = document.getElementById("skillHeaderTitle");
	if (headerTitle) headerTitle.textContent = skillObj.name || skillObj.id;

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
	renderQueueInspector();
}

function renderVariableBadges() {
	const container = document.getElementById("variableBadges");
	if (!container) return;

	const caseVars = new Set();
	const extractedVars = new Set();
	const systemVars = new Set(["{document_fullpath}"]);

	// Extract variables from configured folder structure (e.g. {Datum}, {Produkt}, {Person})
	if (state.config && Array.isArray(state.config.folder_structure)) {
		state.config.folder_structure.forEach((part) => {
			const cleaned = String(part).trim();
			if (cleaned) {
				const formatted = cleaned.startsWith("{") && cleaned.endsWith("}") ? cleaned : `{${cleaned}}`;
				caseVars.add(formatted);
			}
		});
	}

	// Extract variables from configured document extraction fields
	if (state.config && state.config.document_types) {
		Object.values(state.config.document_types).forEach((doc) => {
			if (doc && doc.extraction_fields) {
				Object.keys(doc.extraction_fields).forEach((f) => {
					extractedVars.add(`{${f}}`);
				});
			}
		});
	}

	let html = "";

	if (caseVars.size > 0) {
		html += `<div class="variable-chip-group">
			<span class="variable-group-label">📁 Case / Folder:</span>
			<div class="variable-chip-list">
				${Array.from(caseVars).map((v) => `<span class="badge variable-badge variable-badge-case" onclick="insertVariable('${escapeHtml(v)}')" title="Insert ${escapeHtml(v)} into active field">${escapeHtml(v)}</span>`).join("")}
			</div>
		</div>`;
	}

	if (extractedVars.size > 0) {
		html += `<div class="variable-chip-group">
			<span class="variable-group-label">📑 Extracted Fields:</span>
			<div class="variable-chip-list">
				${Array.from(extractedVars).map((v) => `<span class="badge variable-badge variable-badge-extracted" onclick="insertVariable('${escapeHtml(v)}')" title="Insert ${escapeHtml(v)} into active field">${escapeHtml(v)}</span>`).join("")}
			</div>
		</div>`;
	}

	if (systemVars.size > 0) {
		html += `<div class="variable-chip-group">
			<span class="variable-group-label">⚙️ System Paths:</span>
			<div class="variable-chip-list">
				${Array.from(systemVars).map((v) => `<span class="badge variable-badge variable-badge-system" onclick="insertVariable('${escapeHtml(v)}')" title="Insert ${escapeHtml(v)} into active field">${escapeHtml(v)}</span>`).join("")}
			</div>
		</div>`;
	}

	container.innerHTML = html || `<span class="variables-empty-note">No variables configured.</span>`;
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

		if (!isNewSkillCreation && selectedSkillId) {
			loadSkillDocumentTypes(selectedSkillId);
		} else if (typeof renderDocTypesSidebar === "function") {
			renderDocTypesSidebar();
		}
	} else {
		if (importMeta) importMeta.style.display = "none";
		if (exportMeta) exportMeta.style.display = "block";
		if (exportSection) exportSection.style.display = "block";
		if (importSection) importSection.style.display = "none";
	}
}

// Document Types & Extraction Fields Editor functions are modularized in doctypes_tab.js

/* ═══════════════════════════════════════════════════════════
   CREATE SKILL MODAL & EDITOR ACTIONS
   ═══════════════════════════════════════════════════════════ */

let currentSelectedNewSkillType = "export";

function openCreateSkillModal() {
	currentSelectedNewSkillType = "export";
	selectCreateSkillType("export");
	const modal = document.getElementById("createSkillModal");
	if (modal) {
		modal.style.display = "flex";
	}
}

function closeCreateSkillModal() {
	const modal = document.getElementById("createSkillModal");
	if (modal) {
		modal.style.display = "none";
	}
}

function selectCreateSkillType(type) {
	currentSelectedNewSkillType = type;
	const cardExport = document.getElementById("createSkillCardExport");
	const cardImport = document.getElementById("createSkillCardImport");
	const importOpts = document.getElementById("importSkillCreationOptions");

	if (type === "import") {
		if (cardExport) cardExport.classList.remove("active");
		if (cardImport) cardImport.classList.add("active");
		if (importOpts) importOpts.style.display = "block";
	} else {
		if (cardExport) cardExport.classList.add("active");
		if (cardImport) cardImport.classList.remove("active");
		if (importOpts) importOpts.style.display = "none";
	}

	const radios = document.getElementsByName("newSkillTypeRadio");
	radios.forEach((r) => {
		if (r.value === type) r.checked = true;
	});
}

function confirmCreateSkill() {
	closeCreateSkillModal();
	const copyDefaultDocs = document.getElementById("createSkillCopyDefaultDocs")
		? document.getElementById("createSkillCopyDefaultDocs").checked
		: true;
	createNewSkill(currentSelectedNewSkillType, copyDefaultDocs);
}

function createNewSkill(skillType = "export", copyDefaultDocs = true) {
	isNewSkillCreation = true;
	const isImport = skillType === "import";
	const baseName = isImport ? "New Import Pipeline" : "New Workflow";
	let slug = slugifySkillName(baseName);
	const existingIds = new Set((state.skills || []).map((s) => s.id));
	let counter = 2;
	while (existingIds.has(slug)) {
		slug = `${slugifySkillName(baseName)}_${counter}`;
		counter++;
	}

	let newSkill = null;

	if (isImport) {
		let initialDocTypes = {};
		if (copyDefaultDocs) {
			if (state.config && state.config.document_types) {
				initialDocTypes = JSON.parse(JSON.stringify(state.config.document_types));
			} else {
				const defaultImport = (state.skills || []).find((s) => s.type === "import");
				if (defaultImport && defaultImport.document_types) {
					initialDocTypes = JSON.parse(JSON.stringify(defaultImport.document_types));
				}
			}
		}

		newSkill = {
			id: slug,
			name: counter > 2 ? `${baseName} ${counter - 1}` : baseName,
			type: "import",
			description: "",
			allowed_extensions: [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"],
			split_multi_documents: true,
			save_empty_pages: false,
			enabled: true,
			document_types: initialDocTypes,
		};

		state.editingDocTypes = JSON.parse(JSON.stringify(initialDocTypes));
		state.selectedDocType = null;
	} else {
		newSkill = {
			id: slug,
			name: counter > 2 ? `${baseName} ${counter - 1}` : baseName,
			type: "export",
			description: "",
			target_window: "Remote Desktop*",
			rdp_path_prefix: "\\\\tsclient\\C",
			document_types: ["*"],
			upload_mode: "single_file",
			enabled: true,
			tasks: [
				{
					id: "task_1",
					title: "Programm aufrufen & vorbereiten",
					actions: [
						{
							id: "act_1",
							description: "Zielfenster in den Vordergrund bringen",
							action_type: "FOCUS_WINDOW",
							window_title: "Remote Desktop*",
						},
					],
				},
			],
		};
		currentEditingTasks = JSON.parse(JSON.stringify(newSkill.tasks));
	}

	selectedSkillId = newSkill.id;
	currentEditingSkill = newSkill;

	renderSkillsSidebar(state.skills || []);

	const emptyMsg = document.getElementById("noSkillSelectedMessage");
	const wrapper = document.getElementById("skillFormWrapper");
	if (emptyMsg) emptyMsg.style.display = "none";
	if (wrapper) wrapper.style.display = "block";

	const headerTitle = document.getElementById("skillHeaderTitle");
	if (headerTitle) headerTitle.textContent = newSkill.name;

	document.getElementById("editorSkillId").value = newSkill.id;
	document.getElementById("editorSkillName").value = newSkill.name;
	document.getElementById("editorSkillDesc").value = "";
	document.getElementById("editorSkillType").value = newSkill.type;

	if (isImport) {
		const allowedEl = document.getElementById("editorSkillAllowedExtensions");
		if (allowedEl) allowedEl.value = ".pdf, .png, .jpg, .jpeg, .tif, .tiff";
		const splitEl = document.getElementById("editorSkillSplitMulti");
		if (splitEl) splitEl.checked = true;
		const saveEmptyEl = document.getElementById("editorSkillSaveEmpty");
		if (saveEmptyEl) saveEmptyEl.checked = false;
	} else {
		const targetWinEl = document.getElementById("editorSkillTargetWindow");
		if (targetWinEl) targetWinEl.value = "";
		const rdpPrefixEl = document.getElementById("editorSkillRdpPrefix");
		if (rdpPrefixEl) rdpPrefixEl.value = newSkill.rdp_path_prefix || "\\\\tsclient\\C";
		const docTypesEl = document.getElementById("editorSkillDocTypes");
		if (docTypesEl) docTypesEl.value = "*";
		const uploadModeEl = document.getElementById("editorSkillUploadMode");
		if (uploadModeEl) uploadModeEl.value = "single_file";
	}

	onSkillTypeChange(newSkill.type);
	if (!isImport) {
		renderEditorSteps();
	} else if (typeof renderDocTypesSidebar === "function") {
		renderDocTypesSidebar();
	}
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

// Step rendering, accordion cards & step operations are modularized in skills_steps.js

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

	const flatSteps = typeof getFlattenedSteps === "function" ? getFlattenedSteps() : [];
	const explicitTargetWin = (document.getElementById("editorSkillTargetWindow")?.value || "").trim();
	const firstFocusWin = (flatSteps.find((s) => s.action_type === "FOCUS_WINDOW")?.window_title || "").trim();
	const target_window = explicitTargetWin || firstFocusWin || "Remote Desktop*";
	const rdp_path_prefix = (document.getElementById("editorSkillRdpPrefix")?.value || "").trim() || "\\\\tsclient\\C";
	const docTypesRaw = (document.getElementById("editorSkillDocTypes")?.value || "*").trim();
	const docTypes = docTypesRaw
		? docTypesRaw
				.split(",")
				.map((s) => s.trim())
				.filter(Boolean)
		: ["*"];
	const uploadMode = document.getElementById("editorSkillUploadMode")?.value || "single_file";

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
		payload.split_multi_documents = document.getElementById("editorSkillSplitMulti")
			? document.getElementById("editorSkillSplitMulti").checked
			: true;
		payload.save_empty_pages = document.getElementById("editorSkillSaveEmpty")
			? document.getElementById("editorSkillSaveEmpty").checked
			: false;
		payload.document_types = state.editingDocTypes || {};
	} else {
		payload.target_window = target_window;
		payload.rdp_path_prefix = rdp_path_prefix;
		payload.document_types = docTypes;
		payload.upload_mode = uploadMode;
		payload.tasks = currentEditingTasks;
		payload.steps = flatSteps;
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
		await loadSkills(true);
	} catch (e) {
		toast("Error saving skill: " + e.message, "error");
	}
}

async function duplicateSkillById(skillId) {
	if (!skillId) return;
	try {
		const res = await api(`/api/skills/${encodeURIComponent(skillId)}/duplicate`, {
			method: "POST",
		});
		toast("Skill duplicated: " + (res.skill ? res.skill.name : skillId));
		if (res.skill && res.skill.id) {
			selectedSkillId = res.skill.id;
		}
		await loadSkills(true);
	} catch (e) {
		toast("Error duplicating skill: " + e.message, "error");
	}
}

async function deleteSkillById(skillId) {
	if (!skillId) return;
	const skillObj = (state.skills || []).find((s) => s.id === skillId);
	const displayName = skillObj ? skillObj.name : skillId;
	if (!confirm(`Really delete skill '${displayName}'?`)) return;
	try {
		await api(`/api/skills/${encodeURIComponent(skillId)}`, { method: "DELETE" });
		toast("Skill deleted.");
		if (selectedSkillId === skillId) {
			selectedSkillId = null;
		}
		await loadSkills(true);
	} catch (e) {
		toast("Error deleting skill: " + e.message, "error");
	}
}

