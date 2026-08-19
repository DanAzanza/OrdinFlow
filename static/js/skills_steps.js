/* ═══════════════════════════════════════════════════════════
   SKILLS STEP EDITOR MODULE (Accordion Cards, Actions & Badges)
   ═══════════════════════════════════════════════════════════ */

let stepExpandedMap = {};

function toggleStepCollapse(stepId) {
	stepExpandedMap[stepId] = !stepExpandedMap[stepId];
	const card = document.getElementById(`stepCard_${stepId}`);
	if (card) {
		const isExpanded = !!stepExpandedMap[stepId];
		card.classList.toggle("collapsed", !isExpanded);
		const chevron = card.querySelector(".step-chevron");
		if (chevron) chevron.textContent = isExpanded ? "▼" : "▶";
		const body = card.querySelector(".step-card-body");
		if (body) body.style.display = isExpanded ? "block" : "none";
		const summary = card.querySelector(".step-summary-text");
		if (summary) summary.style.display = isExpanded ? "none" : "inline-block";
	}
}

function expandAllSteps() {
	currentEditingSteps.forEach((s) => {
		stepExpandedMap[s.id] = true;
	});
	renderEditorSteps();
}

function collapseAllSteps() {
	currentEditingSteps.forEach((s) => {
		stepExpandedMap[s.id] = false;
	});
	renderEditorSteps();
}

function addEditorStep(stepObj = null) {
	const step = stepObj || {
		id: "step_" + (currentEditingSteps.length + 1),
		description: "",
		action_type: "CLICK",
		locator: { type: "som_vlm", prompt: "" },
		delay_ms: 500,
	};
	stepExpandedMap[step.id] = true;
	currentEditingSteps.push(step);
	renderEditorSteps();
	updateHeaderStepBadge();
}

function duplicateEditorStep(index) {
	if (index < 0 || index >= currentEditingSteps.length) return;
	const original = currentEditingSteps[index];
	const cloned = JSON.parse(JSON.stringify(original));
	cloned.id = "step_" + (currentEditingSteps.length + 1);
	if (cloned.description) {
		cloned.description = `${cloned.description} (Copy)`;
	}
	stepExpandedMap[cloned.id] = true;
	currentEditingSteps.splice(index + 1, 0, cloned);
	renderEditorSteps();
	updateHeaderStepBadge();
	toast("Step duplicated.");
}

function removeEditorStep(index) {
	if (index >= 0 && index < currentEditingSteps.length) {
		const s = currentEditingSteps[index];
		delete stepExpandedMap[s.id];
	}
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

function getStepSummaryText(step) {
	if (!step) return "";
	const desc = (step.description || "").trim();
	const targetVal = (step.locator && (step.locator.prompt || step.locator.value || step.locator.target)) || "";

	switch (step.action_type) {
		case "FOCUS_WINDOW": {
			const win = step.window_title || "Remote Desktop*";
			return desc ? `${desc} · "${win}"` : `Window: "${win}"`;
		}
		case "CLICK": {
			const val = targetVal || "Element";
			return desc ? `${desc} · Target: "${val}"` : `Click "${val}"`;
		}
		case "DOUBLE_CLICK": {
			const val = targetVal || "Element";
			return desc ? `${desc} · Target: "${val}"` : `Double-Click "${val}"`;
		}
		case "TYPE_TEXT": {
			const txt = step.text || "";
			const enterNote = step.press_enter ? " ↵" : "";
			return desc ? `${desc} · "${txt}"${enterNote}` : `Type "${txt}"${enterNote}`;
		}
		case "TYPE_FILE_PATH": {
			const p = step.file_path || "{document_fullpath}";
			const enterNote = step.press_enter !== false ? " ↵" : "";
			return desc ? `${desc} · ${p}${enterNote}` : `Path: ${p}${enterNote}`;
		}
		case "VERIFY_SCREEN": {
			const val = targetVal || "Screen Text";
			const fallbackAction = step.on_failure_action || (step.on_failure_skill ? "run_skill" : "skip");
			const fallbackNote =
				fallbackAction === "run_skill"
					? ` ➔ ⚡ ${step.on_failure_skill || "Routine"}`
					: fallbackAction === "pause_prompt"
						? " ➔ 🔔 Pause"
						: " ➔ ⏭️ Skip";
			return desc ? `${desc} · Verify "${val}"${fallbackNote}` : `Verify "${val}"${fallbackNote}`;
		}
		case "CALL_SKILL": {
			const sk = step.skill_id || "Sub-Routine";
			return desc ? `${desc} · ⚡ ${sk}` : `Run ⚡ ${sk}`;
		}
		default:
			return desc || step.action_type || "";
	}
}

function renderWorkflowStats(steps) {
	const container = document.getElementById("workflowStatsBadge");
	if (!container) return;
	if (!steps || steps.length === 0) {
		container.innerHTML = "";
		return;
	}

	let clicks = 0;
	let types = 0;
	let verifies = 0;
	let focus = 0;
	let skills = 0;

	steps.forEach((s) => {
		if (["CLICK", "DOUBLE_CLICK"].includes(s.action_type)) clicks++;
		else if (["TYPE_TEXT", "TYPE_FILE_PATH"].includes(s.action_type)) types++;
		else if (s.action_type === "VERIFY_SCREEN") verifies++;
		else if (s.action_type === "FOCUS_WINDOW") focus++;
		else if (s.action_type === "CALL_SKILL") skills++;
	});

	const items = [];
	items.push(`<strong>${steps.length}</strong> ${steps.length === 1 ? "Step" : "Steps"}`);
	if (clicks > 0) items.push(`🎯 ${clicks}`);
	if (types > 0) items.push(`⌨️ ${types}`);
	if (verifies > 0) items.push(`👁️ ${verifies}`);
	if (focus > 0) items.push(`🪟 ${focus}`);
	if (skills > 0) items.push(`⚡ ${skills}`);

	container.innerHTML = items.join(" · ");
}

function getActionBadgeStyle(actionType) {
	switch (actionType) {
		case "FOCUS_WINDOW":
			return { label: "🪟 FOCUS WINDOW", badgeClass: "badge-action-focus", themeClass: "step-theme-focus" };
		case "CLICK":
			return { label: "🎯 CLICK", badgeClass: "badge-action-click", themeClass: "step-theme-click" };
		case "DOUBLE_CLICK":
			return { label: "🖱️ DOUBLE CLICK", badgeClass: "badge-action-dblclick", themeClass: "step-theme-dblclick" };
		case "TYPE_TEXT":
			return { label: "⌨️ TYPE TEXT", badgeClass: "badge-action-type", themeClass: "step-theme-type" };
		case "TYPE_FILE_PATH":
			return { label: "📄 FILE PATH", badgeClass: "badge-action-filepath", themeClass: "step-theme-filepath" };
		case "VERIFY_SCREEN":
			return { label: "👁️ VERIFY SCREEN", badgeClass: "badge-action-verify", themeClass: "step-theme-verify" };
		case "CALL_SKILL":
			return { label: "⚡ SUB SKILL", badgeClass: "badge-action-skill", themeClass: "step-theme-skill" };
		default:
			return { label: actionType || "STEP", badgeClass: "badge-action-default", themeClass: "step-theme-default" };
	}
}

function renderEditorSteps() {
	const container = document.getElementById("editorStepsList");
	if (!container) return;

	renderWorkflowStats(currentEditingSteps);

	if (currentEditingSteps.length === 0) {
		container.innerHTML = `
			<div class="step-empty-box">
				No steps defined for this skill yet. Click "Record workflow" or "Add step manually" below.
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
			const isExpanded = stepExpandedMap[step.id] !== undefined ? !!stepExpandedMap[step.id] : false;
			const summaryText = getStepSummaryText(step);

			let actionSpecificHtml = "";

			if (["CLICK", "DOUBLE_CLICK"].includes(step.action_type)) {
				actionSpecificHtml = `
					<div class="form-group">
						<label class="doc-editor-label">🎯 Target Element / Button Text (or {Variable})</label>
						<input type="text" class="doc-editor-input" value="${escapeHtml(targetVal)}" placeholder="e.g. 'Search' button or {LastName}" onchange="if(!currentEditingSteps[${idx}].locator) currentEditingSteps[${idx}].locator={}; currentEditingSteps[${idx}].locator.prompt = this.value; currentEditingSteps[${idx}].locator.value = this.value; currentEditingSteps[${idx}].locator.type = 'auto';" />
					</div>
				`;
			} else if (step.action_type === "TYPE_TEXT") {
				actionSpecificHtml = `
					<div class="step-type-row">
						<div class="form-group zero-margin">
							<label class="doc-editor-label">⌨️ Text or Variables to type</label>
							<input type="text" class="doc-editor-input" value="${escapeHtml(step.text || "")}" placeholder="e.g. {LastName}, {BirthDate}" onchange="currentEditingSteps[${idx}].text = this.value" />
						</div>
						<label class="step-checkbox-label">
							<input type="checkbox" class="step-checkbox-input" ${step.press_enter ? "checked" : ""} onchange="currentEditingSteps[${idx}].press_enter = this.checked;" />
							Press Enter after typing
						</label>
					</div>
				`;
			} else if (step.action_type === "TYPE_FILE_PATH") {
				actionSpecificHtml = `
					<div class="step-type-row">
						<div class="form-group zero-margin">
							<label class="doc-editor-label">📄 File Path Placeholder</label>
							<input type="text" class="doc-editor-input" value="${escapeHtml(step.file_path || "{document_fullpath}")}" placeholder="{document_fullpath}" onchange="currentEditingSteps[${idx}].file_path = this.value" />
						</div>
						<label class="step-checkbox-label">
							<input type="checkbox" class="step-checkbox-input" ${step.press_enter !== false ? "checked" : ""} onchange="currentEditingSteps[${idx}].press_enter = this.checked;" />
							Press Enter after path
						</label>
					</div>
				`;
			} else if (step.action_type === "VERIFY_SCREEN") {
				const failureAction = step.on_failure_action || (step.on_failure_skill ? "run_skill" : "skip");
				const availableRoutines = (state.skills || []).filter((s) => s.type !== "import" && s.id !== selectedSkillId);

				actionSpecificHtml = `
					<div class="form-group">
						<label class="doc-editor-label step-verify-label">👁️ Element or Text that must appear on screen</label>
						<input type="text" class="doc-editor-input" value="${escapeHtml(targetVal)}" placeholder="e.g. 'Patient Profile' or 'Saved successfully'" onchange="if(!currentEditingSteps[${idx}].locator) currentEditingSteps[${idx}].locator={}; currentEditingSteps[${idx}].locator.prompt = this.value; currentEditingSteps[${idx}].locator.value = this.value; currentEditingSteps[${idx}].locator.type = 'auto';" />
					</div>

					<div class="step-fallback-box">
						<label class="doc-editor-label step-fallback-label">❓ What to do if NOT found on screen?</label>
						<div class="step-fallback-grid">
							<select class="doc-editor-input" onchange="currentEditingSteps[${idx}].on_failure_action = this.value; renderEditorSteps();">
								<option value="run_skill" ${failureAction === "run_skill" ? "selected" : ""}>⚡ Run Routine Workflow</option>
								<option value="pause_prompt" ${failureAction === "pause_prompt" ? "selected" : ""}>🔔 Pause & Alert Human</option>
								<option value="skip" ${failureAction === "skip" ? "selected" : ""}>⏭️ Skip this Case</option>
							</select>

							${
								failureAction === "run_skill"
									? `
								<div class="step-fallback-flex">
									<select class="doc-editor-input flex-input-field" onchange="currentEditingSteps[${idx}].on_failure_skill = this.value;">
										<option value="">-- Select Routine Workflow --</option>
										${availableRoutines.map((r) => `<option value="${escapeHtml(r.id)}" ${step.on_failure_skill === r.id ? "selected" : ""}>${escapeHtml(r.name || r.id)}</option>`).join("")}
									</select>
									<button type="button" class="btn btn-sm btn-secondary step-btn-create-routine" onclick="createRoutineInlineForStep(${idx}, true)" title="Create new routine">➕ New</button>
								</div>
							`
									: `
								<div class="field-hint-text">
									${failureAction === "pause_prompt" ? "Sounds an alert and pauses execution for human assistance." : "Safely aborts this file and marks it for review."}
								</div>
							`
							}
						</div>
					</div>
				`;
			} else if (step.action_type === "FOCUS_WINDOW") {
				actionSpecificHtml = `
					<div class="form-group">
						<label class="doc-editor-label">🪟 Target Window Title (Regex or Wildcard)</label>
						<input type="text" class="doc-editor-input" value="${escapeHtml(step.window_title || "Remote Desktop*")}" placeholder="e.g. Remote Desktop*" onchange="currentEditingSteps[${idx}].window_title = this.value" />
					</div>
				`;
			} else if (step.action_type === "CALL_SKILL") {
				const availableRoutines = (state.skills || []).filter((s) => s.type !== "import" && s.id !== selectedSkillId);
				actionSpecificHtml = `
					<div class="form-group">
						<label class="doc-editor-label">⚡ Routine Workflow to run</label>
						<div class="skill-input-action-row">
							<select class="doc-editor-input flex-input-field" onchange="currentEditingSteps[${idx}].skill_id = this.value;">
								<option value="">-- Select Routine Workflow --</option>
								${availableRoutines.map((r) => `<option value="${escapeHtml(r.id)}" ${step.skill_id === r.id ? "selected" : ""}>${escapeHtml(r.name || r.id)}</option>`).join("")}
							</select>
							<button type="button" class="btn btn-sm btn-secondary step-btn-create-routine" onclick="createRoutineInlineForStep(${idx}, false)" title="Create new routine">➕ New</button>
						</div>
					</div>
				`;
			}

			return `
				<div class="doc-editor-section step-card-box ${badgeStyle.themeClass} ${isExpanded ? "" : "collapsed"}" id="stepCard_${step.id}">
					<!-- Step Header (Clickable Accordion) -->
					<div class="step-card-header" onclick="toggleStepCollapse('${escapeHtml(step.id)}')">
						<div class="step-header-left">
							<span class="step-chevron">${isExpanded ? "▼" : "▶"}</span>
							<span class="step-card-num">#${idx + 1}</span>
							<span class="badge ${badgeStyle.badgeClass}">
								${badgeStyle.label}
							</span>
							<span class="step-summary-text" style="${isExpanded ? "display: none;" : "display: inline-block;"}">${escapeHtml(summaryText)}</span>
						</div>
						<div class="step-card-tools" onclick="event.stopPropagation();">
							<button type="button" class="btn-icon-subtle" onclick="moveStepUp(${idx})" ${isFirst ? "disabled" : ""} title="Move up">⬆️</button>
							<button type="button" class="btn-icon-subtle" onclick="moveStepDown(${idx})" ${isLast ? "disabled" : ""} title="Move down">⬇️</button>
							<button type="button" class="btn-icon-subtle" onclick="duplicateEditorStep(${idx})" title="Duplicate step">📋</button>
							<button type="button" class="btn-icon-subtle btn-icon-danger" onclick="removeEditorStep(${idx})" title="Remove step">🗑️</button>
						</div>
					</div>

					<!-- Step Body (Collapsible) -->
					<div class="step-card-body" style="${isExpanded ? "display: block;" : "display: none;"}">
						<!-- Primary Action & Description -->
						<div class="grid-2col">
							<div class="form-group zero-margin">
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
							<div class="form-group zero-margin">
								<label class="doc-editor-label">Description (Optional)</label>
								<input type="text" class="doc-editor-input" value="${escapeHtml(step.description || "")}" placeholder="e.g. Click search field" onchange="currentEditingSteps[${idx}].description = this.value" />
							</div>
						</div>

						<!-- Action Specific Fields -->
						${actionSpecificHtml}

						<!-- Inline AI Step Refinement -->
						<div class="step-ai-refine-box">
							<span class="ai-assistant-icon" title="AI Step Assistant">✨</span>
							<input type="text" id="aiRefineInput_${idx}" class="doc-editor-input step-ai-refine-input" placeholder="Adjust step with AI: e.g. 'Type {LastName} and press Enter' or 'Click search button'" onkeydown="if(event.key==='Enter') refineStepWithAI(${idx})" />
							<button type="button" class="btn btn-sm btn-accent step-btn-refine" onclick="refineStepWithAI(${idx})">✨ Refine</button>
						</div>
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