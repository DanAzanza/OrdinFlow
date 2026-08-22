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

	const launchSelect = document.getElementById("editorSkillLaunchSkill");
	if (launchSelect) {
		launchSelect.innerHTML = '<option value="">-- None (Direct Execution) --</option>';
		const exportSkills = (state.skills || []).filter((s) => s.type === "export" && s.id !== skillObj.id);
		for (const s of exportSkills) {
			const opt = document.createElement("option");
			opt.value = s.id || s.name;
			opt.textContent = `🚀 ${s.name || s.id}`;
			if ((skillObj.launch_skill_id || "") === opt.value) {
				opt.selected = true;
			}
			launchSelect.appendChild(opt);
		}
		launchSelect.value = skillObj.launch_skill_id || "";
	}

	const exeInput = document.getElementById("editorSkillExecutablePath");
	if (exeInput) exeInput.value = skillObj.executable_path || "";

	const maxWinCheckbox = document.getElementById("editorSkillMaximizeWindow");
	if (maxWinCheckbox) maxWinCheckbox.checked = skillObj.maximize_window !== undefined ? skillObj.maximize_window : false;

	const recHungCheckbox = document.getElementById("editorSkillRecoverHung");
	if (recHungCheckbox) recHungCheckbox.checked = skillObj.recover_hung_process !== undefined ? skillObj.recover_hung_process : false;

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

// ═══════════════════════════════════════════════════════════
// SKILL DOCUMENT TYPES TAGS & SELECTOR MODULARIZED IN skills_doctypes.js
// ═══════════════════════════════════════════════════════════

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
		payload.launch_skill_id = (document.getElementById("editorSkillLaunchSkill")?.value || "").trim();
		payload.executable_path = (document.getElementById("editorSkillExecutablePath")?.value || "").trim();
		payload.maximize_window = document.getElementById("editorSkillMaximizeWindow") ? document.getElementById("editorSkillMaximizeWindow").checked : false;
		payload.recover_hung_process = document.getElementById("editorSkillRecoverHung") ? document.getElementById("editorSkillRecoverHung").checked : false;
		payload.document_types = Array.isArray(currentSkillDocTypes)
			? currentSkillDocTypes.filter((t) => t && t !== "*")
			: [];
		payload.tasks = currentEditingTasks;
		payload.steps = flatSteps;
	}

	return payload;
}

async function pickElementForAction(taskIdx, actIdx) {
	const action = currentEditingTasks?.[taskIdx]?.actions?.[actIdx];
	if (!action) return;

	showToast("🎯 Position cursor over the target element on screen (capturing in 1s)...", "info");

	try {
		const winTitle = (document.getElementById("editorSkillTargetWindow")?.value || "").trim();
		const res = await api("/api/skills/pick_element", {
			method: "POST",
			body: JSON.stringify({
				window_title: winTitle,
				delay_seconds: 1.0,
			}),
		});

		if (res && res.status === "ok") {
			if (!action.locator || typeof action.locator !== "object") {
				action.locator = {};
			}
			action.locator.prompt = res.locator.prompt;
			action.locator.type = res.locator.type;
			action.locator.offset = res.locator.offset || [0, 0];
			renderEditorSteps();
			showToast(`🎯 Picked element: "${res.locator.prompt}"`, "success");
		} else {
			showToast("Could not pick element: " + (res?.error || "Unknown error"), "error");
		}
	} catch (e) {
		console.error("Pick element error:", e);
		showToast("Pick element failed: " + e.message, "error");
	}
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

// Conversational AI Skill Copilot Chat routines are modularized in skills_copilot.js

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

async function testRunCurrentSkill() {
	const payload = getSkillPayloadFromForm();
	const btn = document.getElementById("btnTestRunSkillTop");
	if (btn) {
		btn.disabled = true;
		btn.innerHTML = `<span>⏳</span> Running...`;
	}

	toast("▶️ Starting test execution of skill with test data...", "info");

	try {
		const res = await api("/api/skills/test_run", {
			method: "POST",
			body: JSON.stringify({
				skill: payload,
				context: {
					document_fullpath: "C:\\OrdinFlowTest\\Cases\\Test_Patient_2026\\Fußscan.pdf",
					Nachname: "Mustermann",
					Vorname: "Max",
					Datum: new Date().toISOString().split("T")[0],
					Fallnummer: "F-2026-TEST",
				},
			}),
		});

		if (res && res.success) {
			toast(`✅ Test run completed successfully in ${res.duration_seconds}s (${res.total_actions} actions)!`, "success");
		} else {
			toast(`⚠️ Test run finished with issues (${res.error || "Check target application window"})`, "error");
		}
	} catch (e) {
		toast("Test run error: " + e.message, "error");
	} finally {
		if (btn) {
			btn.disabled = false;
			btn.innerHTML = `<span>▶️</span> Test Run`;
		}
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

