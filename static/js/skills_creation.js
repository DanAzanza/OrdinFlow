/* ═══════════════════════════════════════════════════════════
   SKILLS CREATION MODAL & TEMPLATES MODULE
   ═══════════════════════════════════════════════════════════ */

let currentSelectedNewSkillType = "export";

function slugifySkillName(name) {
	return (name || "")
		.toLowerCase()
		.trim()
		.replace(/[^a-z0-9_]+/g, "_")
		.replace(/^_+|_+$/g, "") || "skill";
}

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
