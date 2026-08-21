/* ═══════════════════════════════════════════════════════════
   SKILLS MANAGEMENT JS (Master-Detail Editor & Skill Queue Inspector)
   ═══════════════════════════════════════════════════════════ */

let selectedSkillId = null;
let currentEditingSkill = null;
let currentEditingSkillOriginalName = null;
let activeInputField = null;
let isNewSkillCreation = false;

const FORBIDDEN_NAME_CHARS_REGEX = /[\\/:*?"<>|]/;

function onSkillNameInput(val) {
	const headerTitle = document.getElementById("skillHeaderTitle");
	if (headerTitle) {
		headerTitle.textContent = val.trim() || "Untitled Skill";
	}
	if (currentEditingSkill) {
		currentEditingSkill.name = val.trim();
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
	const emptyMsg = document.getElementById("noSkillSelectedMessage");
	const wrapper = document.getElementById("skillFormWrapper");
	if (emptyMsg) emptyMsg.style.display = "flex";
	if (wrapper) wrapper.style.display = "none";
	renderSkillsSidebar(state.skills || []);
	renderQueueInspector();
}

function getSkillFormVal(field) {
	if (field === "name") {
		return (
			document.getElementById("editorSkillName")?.value ||
			document.getElementById("editorImportSkillName")?.value ||
			""
		).trim();
	}
	if (field === "type") {
		return (
			document.getElementById("editorSkillType")?.value ||
			document.getElementById("editorImportSkillType")?.value ||
			"export"
		);
	}
	if (field === "description") {
		return (
			document.getElementById("editorSkillDesc")?.value ||
			document.getElementById("editorImportSkillDesc")?.value ||
			""
		).trim();
	}
	return "";
}

function setSkillFormVal(field, val) {
	if (field === "name") {
		const el1 = document.getElementById("editorSkillName");
		const el2 = document.getElementById("editorImportSkillName");
		if (el1) el1.value = val;
		if (el2) el2.value = val;
	} else if (field === "type") {
		const el1 = document.getElementById("editorSkillType");
		const el2 = document.getElementById("editorImportSkillType");
		if (el1) el1.value = val;
		if (el2) el2.value = val;
	} else if (field === "description") {
		const el1 = document.getElementById("editorSkillDesc");
		const el2 = document.getElementById("editorImportSkillDesc");
		if (el1) el1.value = val;
		if (el2) el2.value = val;
	}
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
				title: "Execute Action Sequence",
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

	setSkillFormVal("name", skillObj.name || skillObj.id || "");
	setSkillFormVal("description", skillObj.description || "");
	setSkillFormVal("type", skillObj.type || "export");

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

	if (Array.isArray(skillObj.document_types)) {
		currentSkillDocTypes = skillObj.document_types.filter((t) => t && t !== "*");
	} else if (typeof skillObj.document_types === "string" && skillObj.document_types.trim()) {
		currentSkillDocTypes = skillObj.document_types
			.split(",")
			.map((s) => s.trim())
			.filter((s) => s && s !== "*");
	} else {
		currentSkillDocTypes = [];
	}
	renderSkillDocTypesTags();

	onSkillTypeChange(skillObj.type || "export");
	renderEditorSteps();
	initSkillCopilotChat(skillObj.id);
	switchSkillView("visual");
	renderQueueInspector();
}

/* ═══════════════════════════════════════════════════════════
   ALLOWED DOCUMENT TYPES (Integrated Tokenfield & Plus Menu)
   ═══════════════════════════════════════════════════════════ */

let currentSkillDocTypes = [];

function getImportSkillDocTypesMap() {
	const map = {};
	if (state.config && state.config.document_types) {
		for (const [name, cfg] of Object.entries(state.config.document_types)) {
			map[name] = cfg || {};
		}
	}
	if (Array.isArray(state.skills)) {
		for (const s of state.skills) {
			if (s.type === "import" && s.document_types && typeof s.document_types === "object") {
				for (const [name, cfg] of Object.entries(s.document_types)) {
					if (!map[name]) {
						map[name] = cfg || {};
					}
				}
			}
		}
	}
	return map;
}

function renderSkillDocTypesTags() {
	const container = document.getElementById("editorSkillDocTypesTags");
	if (!container) return;

	container.innerHTML = "";
	const knownMap = getImportSkillDocTypesMap();

	// Clean out any legacy wildcard values
	currentSkillDocTypes = (currentSkillDocTypes || []).filter((t) => t && t !== "*");

	if (currentSkillDocTypes.length === 0) {
		const placeholder = document.createElement("span");
		placeholder.className = "skill-doctype-empty-placeholder";
		placeholder.textContent = "All documents (no filter)";
		container.appendChild(placeholder);
	} else {
		for (const dt of currentSkillDocTypes) {
			const emoji = knownMap[dt]?.emoji || "📄";
			const chip = document.createElement("span");
			chip.className = "skill-doctype-chip";
			chip.innerHTML = `<span>${escapeHtml(emoji)}</span> <span>${escapeHtml(dt)}</span> <button type="button" class="skill-doctype-chip-remove" onclick="removeDocTypeFromSkill('${escapeHtml(dt)}')" title="Remove ${escapeHtml(dt)}">✕</button>`;
			container.appendChild(chip);
		}
	}
}

function toggleDocTypeDropdown(event) {
	if (event) event.stopPropagation();
	const menu = document.getElementById("docTypeDropdownMenu");
	if (!menu) return;

	if (menu.style.display === "block") {
		menu.style.display = "none";
		return;
	}

	const knownMap = getImportSkillDocTypesMap();
	const availableNames = Object.keys(knownMap)
		.filter((name) => !currentSkillDocTypes.includes(name))
		.sort();

	if (availableNames.length === 0) {
		menu.innerHTML = `<div class="doctype-popover-empty">All defined document types added</div>`;
	} else {
		menu.innerHTML = availableNames
			.map((name) => {
				const emoji = knownMap[name]?.emoji || "📄";
				return `<div class="doctype-popover-item" onclick="addDocTypeToSkill('${escapeHtml(name)}')">
					<span>${escapeHtml(emoji)}</span>
					<span>${escapeHtml(name)}</span>
				</div>`;
			})
			.join("");
	}

	menu.style.display = "block";
}

function closeDocTypeDropdown() {
	const menu = document.getElementById("docTypeDropdownMenu");
	if (menu) menu.style.display = "none";
}

document.addEventListener("click", (e) => {
	const menu = document.getElementById("docTypeDropdownMenu");
	const btn = document.getElementById("btnDocTypeAddMenu");
	if (menu && menu.style.display === "block" && !menu.contains(e.target) && e.target !== btn) {
		menu.style.display = "none";
	}
});

function addDocTypeToSkill(docType) {
	const trimmed = (docType || "").trim();
	if (!trimmed || trimmed === "*") return;

	if (!currentSkillDocTypes.includes(trimmed)) {
		currentSkillDocTypes.push(trimmed);
	}
	closeDocTypeDropdown();
	renderSkillDocTypesTags();
}

function removeDocTypeFromSkill(docType) {
	currentSkillDocTypes = currentSkillDocTypes.filter((t) => t !== docType);
	renderSkillDocTypesTags();
}

function onSkillTypeChange(type) {
	if (currentEditingSkill) {
		currentEditingSkill.type = type;
	}
	setSkillFormVal("type", type);
	const exportSection = document.getElementById("exportSkillSection");
	const importSection = document.getElementById("importSkillSection");

	if (type === "import") {
		if (exportSection) exportSection.style.display = "none";
		if (importSection) importSection.style.display = "block";

		if (!isNewSkillCreation && selectedSkillId) {
			loadSkillDocumentTypes(selectedSkillId);
		} else if (typeof renderDocTypesSidebar === "function") {
			renderDocTypesSidebar();
		}
	} else {
		if (exportSection) exportSection.style.display = "grid";
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
	const baseName = isImport ? "New Import Pipeline" : "New Skill";
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
			document_types: [],
			enabled: true,
			tasks: [
				{
					id: "task_1",
					title: "Open target application & prepare",
					actions: [
						{
							id: "act_1",
							description: "Bring target window to foreground",
							action_type: "FOCUS_WINDOW",
							window_title: "Remote Desktop*",
						},
					],
				},
			],
		};
		currentEditingTasks = JSON.parse(JSON.stringify(newSkill.tasks));
	}

	selectedSkillId = newSkill.name;
	currentEditingSkill = newSkill;
	currentEditingSkillOriginalName = null;

	renderSkillsSidebar(state.skills || []);

	const emptyMsg = document.getElementById("noSkillSelectedMessage");
	const wrapper = document.getElementById("skillFormWrapper");
	if (emptyMsg) emptyMsg.style.display = "none";
	if (wrapper) wrapper.style.display = "block";

	const headerTitle = document.getElementById("skillHeaderTitle");
	if (headerTitle) headerTitle.textContent = newSkill.name;

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
		currentSkillDocTypes = [];
		renderSkillDocTypesTags();
	}

	onSkillTypeChange(newSkill.type);
	if (!isImport) {
		renderEditorSteps();
	} else if (typeof renderDocTypesSidebar === "function") {
		renderDocTypesSidebar();
	}
	switchSkillView("visual");
	renderQueueInspector();

	// Focus and select skill name input so the user can type immediately
	const nameInput = document.getElementById("editorSkillName");
	if (nameInput) {
		nameInput.focus();
		nameInput.select();
	}
}

// ═══════════════════════════════════════════════════════════
// SKILL VIEW MODE & YAML EXPERT MODE
// ═══════════════════════════════════════════════════════════

let currentSkillViewMode = "visual";

function switchSkillView(mode) {
	currentSkillViewMode = mode;
	const visualSection = document.getElementById("skillVisualSection");
	const yamlSection = document.getElementById("skillYamlSection");
	const btnVisual = document.getElementById("btnSkillViewVisual");
	const btnYaml = document.getElementById("btnSkillViewYaml");

	if (mode === "yaml") {
		if (visualSection) visualSection.style.display = "none";
		if (yamlSection) yamlSection.style.display = "block";
		if (btnVisual) btnVisual.classList.remove("active");
		if (btnYaml) btnYaml.classList.add("active");
		syncYamlFromVisual();
	} else {
		if (visualSection) visualSection.style.display = "block";
		if (yamlSection) yamlSection.style.display = "none";
		if (btnVisual) btnVisual.classList.add("active");
		if (btnYaml) btnYaml.classList.remove("active");
	}
}

function getSkillPayloadFromForm() {
	const name = getSkillFormVal("name") || "Untitled Skill";
	const type = getSkillFormVal("type");
	const description = getSkillFormVal("description");

	const payload = {
		id: name,
		name: name,
		type: type,
		description: description,
		enabled: true,
	};

	if (currentEditingSkillOriginalName && currentEditingSkillOriginalName !== name) {
		payload.original_name = currentEditingSkillOriginalName;
	}

	if (type === "import") {
		const allowedExtsRaw = (document.getElementById("editorSkillAllowedExtensions") || {}).value || "";
		payload.allowed_extensions = allowedExtsRaw
			? allowedExtsRaw
					.split(",")
					.map((s) => s.trim().toLowerCase())
					.filter(Boolean)
					.map((s) => (s.startsWith(".") ? s : "." + s))
			: [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"];
		payload.split_multi_documents = document.getElementById("editorSkillSplitMulti")
			? document.getElementById("editorSkillSplitMulti").checked
			: true;
		payload.save_empty_pages = document.getElementById("editorSkillSaveEmpty")
			? document.getElementById("editorSkillSaveEmpty").checked
			: false;
		payload.document_types = state.editingDocTypes || {};
	} else {
		const explicitTargetWin = (document.getElementById("editorSkillTargetWindow")?.value || "").trim();
		const flatSteps = typeof getFlattenedSteps === "function" ? getFlattenedSteps() : [];
		const firstFocusWin = (flatSteps.find((s) => s.action_type === "FOCUS_WINDOW")?.window_title || "").trim();
		payload.target_window = explicitTargetWin || firstFocusWin || "Remote Desktop*";
		payload.rdp_path_prefix = (document.getElementById("editorSkillRdpPrefix")?.value || "").trim() || "\\\\tsclient\\C";
		payload.document_types = Array.isArray(currentSkillDocTypes)
			? currentSkillDocTypes.filter((t) => t && t !== "*")
			: [];
		payload.tasks = currentEditingTasks;
		payload.steps = flatSteps;
	}

	return payload;
}

async function syncYamlFromVisual() {
	const textarea = document.getElementById("skillYamlEditorTextarea");
	if (!textarea) return;
	const payload = getSkillPayloadFromForm();
	try {
		const res = await api("/api/skills/to_yaml", {
			method: "POST",
			body: JSON.stringify({ skill: payload }),
		});
		if (res && res.yaml) {
			textarea.value = res.yaml;
		}
	} catch (e) {
		console.error("Error generating YAML:", e);
	}
}

async function applyYamlToVisualAndSave() {
	const textarea = document.getElementById("skillYamlEditorTextarea");
	if (!textarea) return;
	const yamlStr = textarea.value.trim();
	if (!yamlStr) {
		toast("YAML content cannot be empty", "error");
		return;
	}

	try {
		const res = await api("/api/skills/from_yaml", {
			method: "POST",
			body: JSON.stringify({ yaml: yamlStr }),
		});

		if (res && res.skill) {
			const skillObj = res.skill;
			await api("/api/skills", {
				method: "POST",
				body: JSON.stringify(skillObj),
			});

			selectedSkillId = skillObj.id;
			isNewSkillCreation = false;
			await loadSkills(true);
			await selectSkill(skillObj.id);
			switchSkillView("visual");
			toast(`✨ YAML for skill '${skillObj.name || skillObj.id}' saved successfully!`, "success");
		}
	} catch (e) {
		toast("Error applying YAML: " + e.message, "error");
	}
}

// ═══════════════════════════════════════════════════════════
// CONVERSATIONAL AI SKILL COPILOT CHAT
// ═══════════════════════════════════════════════════════════

const skillCopilotChatMap = {};

function getSkillCopilotHistory(skillId) {
	const id = skillId || selectedSkillId || "temp";
	if (!skillCopilotChatMap[id]) {
		skillCopilotChatMap[id] = [
			{
				role: "assistant",
				content: "Hello! I am your AI Copilot for this export skill. Simply describe in natural language how the workflow should look or what changes to make (e.g. add clicks, adjust delays, or change target window titles).",
				time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
			},
		];
	}
	return skillCopilotChatMap[id];
}

function initSkillCopilotChat(skillId) {
	const feed = document.getElementById("skillCopilotChatFeed");
	if (!feed) return;
	const history = getSkillCopilotHistory(skillId);
	renderSkillChatFeed(history);
}

function clearSkillCopilotChat() {
	const id = selectedSkillId || "temp";
	skillCopilotChatMap[id] = [
		{
			role: "assistant",
			content: "Chat history reset. How can I assist you with this skill?",
			time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
		},
	];
	renderSkillChatFeed(skillCopilotChatMap[id]);
}

function renderSkillChatFeed(history) {
	const feed = document.getElementById("skillCopilotChatFeed");
	if (!feed) return;
	feed.innerHTML = history
		.map((msg) => {
			const isUser = msg.role === "user";
			return `
			<div class="skill-chat-msg ${isUser ? "user" : "assistant"}">
				<div class="skill-chat-msg-icon">${isUser ? "👤" : "✨"}</div>
				<div class="skill-chat-msg-bubble">
					<div>${escapeHtml(msg.content)}</div>
					${
						msg.time
							? `<div style="font-size: 0.68rem; color: ${
									isUser ? "rgba(255,255,255,0.7)" : "var(--text-dim)"
								}; text-align: right; margin-top: 3px;">${escapeHtml(msg.time)}</div>`
							: ""
					}
				</div>
			</div>
		`;
		})
		.join("");
	feed.scrollTop = feed.scrollHeight;
}

async function sendSkillCopilotMessage() {
	const input = document.getElementById("skillCopilotChatInput");
	const promptText = (input?.value || "").trim();
	if (!promptText) return;

	const id = selectedSkillId || "temp";
	const history = getSkillCopilotHistory(id);
	const nowTime = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

	// Append user message
	history.push({
		role: "user",
		content: promptText,
		time: nowTime,
	});
	if (input) input.value = "";
	renderSkillChatFeed(history);

	// Append typing indicator
	const feed = document.getElementById("skillCopilotChatFeed");
	const typingId = "skillChatTypingIndicator";
	if (feed) {
		const typingEl = document.createElement("div");
		typingEl.id = typingId;
		typingEl.className = "skill-chat-msg assistant";
		typingEl.innerHTML = `
			<div class="skill-chat-msg-icon">✨</div>
			<div class="skill-chat-typing">
				<div class="skill-chat-dot"></div>
				<div class="skill-chat-dot"></div>
				<div class="skill-chat-dot"></div>
			</div>
		`;
		feed.appendChild(typingEl);
		feed.scrollTop = feed.scrollHeight;
	}

	const sendBtn = document.getElementById("btnSkillCopilotSend");
	if (sendBtn) sendBtn.disabled = true;

	const currentPayload = getSkillPayloadFromForm();

	try {
		const res = await api("/api/skills/ai_modify", {
			method: "POST",
			body: JSON.stringify({
				skill: currentPayload,
				instruction: promptText,
				history: history.slice(0, -1),
			}),
		});

		// Remove typing indicator
		document.getElementById(typingId)?.remove();

		if (res && res.skill) {
			const updated = res.skill;
			if (updated.name) {
				setSkillFormVal("name", updated.name);
				onSkillNameInput(updated.name);
			}
			if (updated.description) {
				setSkillFormVal("description", updated.description);
			}
			if (updated.target_window) {
				const winEl = document.getElementById("editorSkillTargetWindow");
				if (winEl) winEl.value = updated.target_window;
			}
			if (updated.document_types !== undefined) {
				currentSkillDocTypes = Array.isArray(updated.document_types)
					? updated.document_types.filter((t) => t && t !== "*")
					: typeof updated.document_types === "string"
						? updated.document_types.split(",").map((s) => s.trim()).filter((s) => s && s !== "*")
						: [];
				renderSkillDocTypesTags();
			}
			if (Array.isArray(updated.tasks) && updated.tasks.length > 0) {
				currentEditingTasks = updated.tasks;
			} else if (Array.isArray(updated.steps) && updated.steps.length > 0) {
				currentEditingTasks = [
					{
						id: "task_1",
						title: "Task 1: Execute Application Flow",
						actions: updated.steps,
					},
				];
			}

			if (currentEditingSkill) {
				Object.assign(currentEditingSkill, updated);
				currentEditingSkill.tasks = currentEditingTasks;
			}

			renderEditorSteps();

			// Append assistant reply
			const replyText = res.reply || "I have updated the skill according to your instruction.";
			history.push({
				role: "assistant",
				content: replyText,
				time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
			});
			renderSkillChatFeed(history);
			toast("✨ Skill updated by AI Copilot!", "success");
		} else {
			history.push({
				role: "assistant",
				content: "Sorry, I was unable to apply this modification.",
				time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
			});
			renderSkillChatFeed(history);
		}
	} catch (e) {
		document.getElementById(typingId)?.remove();
		console.error("Skill copilot chat error:", e);
		history.push({
			role: "assistant",
			content: "Failed to apply changes: " + e.message,
			time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
		});
		renderSkillChatFeed(history);
		toast("Error: " + e.message, "error");
	} finally {
		if (sendBtn) sendBtn.disabled = false;
		input?.focus();
	}
}

function duplicateCurrentSkill() {
	const activeName = currentEditingSkill?.name || selectedSkillId;
	if (activeName) {
		duplicateSkillById(activeName);
	}
}

function deleteCurrentSkill() {
	const activeName = currentEditingSkill?.name || selectedSkillId;
	if (activeName) {
		deleteSkillById(activeName);
	}
}

async function saveSkillFromEditor() {
	const payload = getSkillPayloadFromForm();
	const name = payload.name;
	const type = payload.type;

	if (FORBIDDEN_NAME_CHARS_REGEX.test(name)) {
		toast("Skill name cannot contain path characters (:, /, \\, *, ?, \", <, >, |)", "error");
		return;
	}

	try {
		const res = await api("/api/skills", {
			method: "POST",
			body: JSON.stringify(payload),
		});

		const finalName = (res && (res.name || res.skill_id)) || name;

		if (type === "import" && state.editingDocTypes) {
			await api(`/api/skills/${encodeURIComponent(finalName)}/documents`, {
				method: "PUT",
				body: JSON.stringify({ document_types: state.editingDocTypes }),
			});
		}

		toast("Skill '" + finalName + "' saved successfully!");
		isNewSkillCreation = false;
		selectedSkillId = finalName;
		currentEditingSkillOriginalName = finalName;
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
		const newName = res.skill ? (res.skill.name || res.skill.id) : skillId;
		toast("Skill duplicated: " + newName);
		selectedSkillId = newName;
		currentEditingSkillOriginalName = newName;
		await loadSkills(true);
	} catch (e) {
		toast("Error duplicating skill: " + e.message, "error");
	}
}

async function deleteSkillById(skillId) {
	if (!skillId) return;
	const skillObj = (state.skills || []).find((s) => (s.name === skillId || s.id === skillId));
	const displayName = skillObj ? skillObj.name : skillId;
	if (!confirm(`Really delete skill '${displayName}'?`)) return;
	try {
		await api(`/api/skills/${encodeURIComponent(skillId)}`, { method: "DELETE" });
		toast("Skill deleted.");
		if (selectedSkillId === skillId || selectedSkillId === displayName) {
			selectedSkillId = null;
			currentEditingSkillOriginalName = null;
		}
		await loadSkills(true);
	} catch (e) {
		toast("Error deleting skill: " + e.message, "error");
	}
}

