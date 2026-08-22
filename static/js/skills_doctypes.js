/* ═══════════════════════════════════════════════════════════
   SKILLS DOCTYPES JS (Document Type Scope Tags & Popover Selector)
   ═══════════════════════════════════════════════════════════ */

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

	if (typeof renderEditorSteps === "function") {
		renderEditorSteps();
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
