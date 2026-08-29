/* ═══════════════════════════════════════════════════════════
   SKILLS TASK & ACTION EDITOR MODULE (Clean Hierarchical Editor)
   ═══════════════════════════════════════════════════════════ */

let currentEditingTasks = [];

function getActionBadgeStyle(actionType) {
	const norm = String(actionType || "").toUpperCase();
	switch (norm) {
		case "FOCUS_WINDOW":
			return { label: "🪟 Focus Window", badgeClass: "action-pill-focus", icon: "🪟" };
		case "CLICK":
			return { label: "🎯 Click", badgeClass: "action-pill-click", icon: "🎯" };
		case "DOUBLE_CLICK":
			return { label: "🖱️ Double Click", badgeClass: "action-pill-click", icon: "🖱️" };
		case "RIGHT_CLICK":
			return { label: "🖱️ Right Click", badgeClass: "action-pill-click", icon: "🖱️" };
		case "TYPE_TEXT":
			return { label: "⌨️ Type Text", badgeClass: "action-pill-type", icon: "⌨️" };
		case "TYPE_FILE_PATH":
			return { label: "📄 File Path", badgeClass: "action-pill-path", icon: "📄" };
		case "VERIFY_SCREEN":
			return { label: "👁️ Verify Screen", badgeClass: "action-pill-verify", icon: "👁️" };
		case "WAIT_FOR_ELEMENT":
			return { label: "⏳ Wait For Element", badgeClass: "action-pill-wait", icon: "⏳" };
		case "CALL_SKILL":
			return { label: "⚡ Call Sub-Skill", badgeClass: "action-pill-skill", icon: "⚡" };
		case "POWERSHELL":
		case "RUN_SCRIPT":
		case "EXECUTE_COMMAND":
		case "SCRIPT":
			return { label: "⚡ PowerShell / Script", badgeClass: "action-pill-skill", icon: "⚡" };
		case "HOTKEY":
		case "PRESS_KEY":
			return { label: "⌨️ Hotkey / Key", badgeClass: "action-pill-type", icon: "⌨️" };
		case "SLEEP":
		case "DELAY":
		case "WAIT":
			return { label: "⏱️ Delay", badgeClass: "action-pill-wait", icon: "⏱️" };
		case "BRANCH":
		case "IF_CONDITION":
			return { label: "🔀 Branch (IF/ELSE)", badgeClass: "action-pill-verify", icon: "🔀" };
		case "FOR_EACH_DOCUMENT":
			return { label: "🔁 For Each Doc", badgeClass: "action-pill-path", icon: "🔁" };
		case "FOR_EACH":
			return { label: "🔄 For Each Item", badgeClass: "action-pill-skill", icon: "🔄" };
		case "WHILE_LOOP":
			return { label: "⏳ While Loop", badgeClass: "action-pill-wait", icon: "⏳" };
		case "EXTRACT_UI_TEXT":
			return { label: "📥 Extract UI Text", badgeClass: "action-pill-path", icon: "📥" };
		case "VALIDATE_UI_STATE":
			return { label: "🔍 Validate UI State", badgeClass: "action-pill-verify", icon: "🔍" };
		case "SET_VARIABLE":
			return { label: "💾 Set Variable", badgeClass: "action-pill-type", icon: "💾" };
		default:
			return { label: norm || "Action", badgeClass: "action-pill-focus", icon: "⚙️" };
	}
}

function toggleActionEdit(taskIdx, actIdx) {
	if (taskIdx >= 0 && taskIdx < currentEditingTasks.length) {
		const actions = currentEditingTasks[taskIdx].actions || [];
		if (actIdx >= 0 && actIdx < actions.length) {
			actions[actIdx]._editing = !actions[actIdx]._editing;
			renderEditorSteps();
		}
	}
}

function updateActionProperty(taskIdx, actIdx, prop, val) {
	if (taskIdx >= 0 && taskIdx < currentEditingTasks.length) {
		const actions = currentEditingTasks[taskIdx].actions || [];
		if (actIdx >= 0 && actIdx < actions.length) {
			const act = actions[actIdx];
			if (prop.startsWith("locator.")) {
				const sub = prop.split(".")[1];
				if (!act.locator) act.locator = { type: "auto" };
				act.locator[sub] = val;
			} else {
				act[prop] = val;
			}
			if (currentEditingSkill) {
				currentEditingSkill.tasks = currentEditingTasks;
			}
		}
	}
}

function addEditorTask(title = "New Task", actions = []) {
	const taskIdx = currentEditingTasks.length + 1;
	const newTask = {
		id: `task_${taskIdx}`,
		title: title,
		actions: actions.length > 0 ? actions : [
			{
				id: `act_${Date.now()}_1`,
				action_type: "CLICK",
				description: "Click on element",
				locator: { type: "auto", prompt: "" },
				delay_ms: 300,
			},
		],
	};
	currentEditingTasks.push(newTask);
	renderEditorSteps();
	updateHeaderStepBadge();
}

function removeEditorTask(taskIdx) {
	if (taskIdx >= 0 && taskIdx < currentEditingTasks.length) {
		currentEditingTasks.splice(taskIdx, 1);
		renderEditorSteps();
		updateHeaderStepBadge();
	}
}

function moveTaskUp(taskIdx) {
	if (taskIdx <= 0) return;
	const temp = currentEditingTasks[taskIdx];
	currentEditingTasks[taskIdx] = currentEditingTasks[taskIdx - 1];
	currentEditingTasks[taskIdx - 1] = temp;
	renderEditorSteps();
}

function moveTaskDown(taskIdx) {
	if (taskIdx >= currentEditingTasks.length - 1) return;
	const temp = currentEditingTasks[taskIdx];
	currentEditingTasks[taskIdx] = currentEditingTasks[taskIdx + 1];
	currentEditingTasks[taskIdx + 1] = temp;
	renderEditorSteps();
}

function addEditorAction(taskIdx = null) {
	if (currentEditingTasks.length === 0) {
		addEditorTask("Task 1: Execute Application Flow");
		return;
	}

	const targetIdx = taskIdx !== null && taskIdx >= 0 && taskIdx < currentEditingTasks.length
		? taskIdx
		: currentEditingTasks.length - 1;

	const task = currentEditingTasks[targetIdx];
	if (!task.actions) task.actions = [];

	const newAct = {
		id: `act_${Date.now()}_${task.actions.length + 1}`,
		action_type: "CLICK",
		description: "Click on element",
		locator: { type: "auto", prompt: "" },
		delay_ms: 300,
	};
	task.actions.push(newAct);
	renderEditorSteps();
	updateHeaderStepBadge();
}

const addEditorStep = addEditorAction;

function removeEditorAction(taskIdx, actIdx) {
	if (
		taskIdx >= 0 &&
		taskIdx < currentEditingTasks.length &&
		actIdx >= 0 &&
		actIdx < currentEditingTasks[taskIdx].actions.length
	) {
		currentEditingTasks[taskIdx].actions.splice(actIdx, 1);
		renderEditorSteps();
		updateHeaderStepBadge();
	}
}

function moveActionUp(taskIdx, actIdx) {
	if (taskIdx < 0 || taskIdx >= currentEditingTasks.length || actIdx <= 0) return;
	const actions = currentEditingTasks[taskIdx].actions;
	const temp = actions[actIdx];
	actions[actIdx] = actions[actIdx - 1];
	actions[actIdx - 1] = temp;
	renderEditorSteps();
}

function moveActionDown(taskIdx, actIdx) {
	if (taskIdx < 0 || taskIdx >= currentEditingTasks.length) return;
	const actions = currentEditingTasks[taskIdx].actions;
	if (actIdx >= actions.length - 1) return;
	const temp = actions[actIdx];
	actions[actIdx] = actions[actIdx + 1];
	actions[actIdx + 1] = temp;
	renderEditorSteps();
}

function updateHeaderStepBadge() {
	let totalActions = 0;
	currentEditingTasks.forEach((t) => {
		totalActions += (t.actions || []).length;
	});

	const statsBadge = document.getElementById("workflowStatsBadge");
	if (statsBadge) {
		statsBadge.textContent = `${currentEditingTasks.length} Tasks · ${totalActions} Actions`;
	}
}

function getFlattenedActions() {
	const flat = [];
	currentEditingTasks.forEach((t) => {
		(t.actions || []).forEach((a) => {
			flat.push(a);
		});
	});
	return flat;
}

const getFlattenedSteps = getFlattenedActions;

function isActionSensitive(act) {
	if (!act) return false;
	if (act.is_secret) return true;
	const text = `${act.description || ""} ${act.text || ""}`.toLowerCase();
	return /\b(password|passwort|kennwort|geheim|secret|pin|api_key|token|access_key|auth_token|bearer)\b/i.test(text);
}

function toggleActionSecret(taskIdx, actIdx) {
	if (taskIdx >= 0 && taskIdx < currentEditingTasks.length) {
		const actions = currentEditingTasks[taskIdx].actions || [];
		if (actIdx >= 0 && actIdx < actions.length) {
			actions[actIdx].is_secret = !actions[actIdx].is_secret;
			renderEditorSteps();
		}
	}
}

function toggleActionReveal(taskIdx, actIdx) {
	if (taskIdx >= 0 && taskIdx < currentEditingTasks.length) {
		const actions = currentEditingTasks[taskIdx].actions || [];
		if (actIdx >= 0 && actIdx < actions.length) {
			actions[actIdx]._revealed = !actions[actIdx]._revealed;
			renderEditorSteps();
		}
	}
}

function getAvailableSkillVariables(filterDocTypes = null) {
	const vars = new Set([
		"{document_fullpath}",
		"{document_filename}",
		"{document_basename}",
		"{document_extension}",
		"{case_folder}",
		"{Datum}",
	]);

	const appState = typeof state !== "undefined" ? state : ((typeof window !== "undefined" && window.state) || {});

	// Active document types filter (from argument or currentSkillDocTypes)
	const activeFilter = filterDocTypes || (typeof currentSkillDocTypes !== "undefined" && Array.isArray(currentSkillDocTypes) && currentSkillDocTypes.length > 0 ? currentSkillDocTypes : null);

	// 1. Extract dynamic fields from Import Skills (matching active document types if filtered)
	const skills = appState.skills || [];
	for (const skill of skills) {
		if (skill.type === "import" && skill.document_types && typeof skill.document_types === "object") {
			for (const [dtName, dtConfig] of Object.entries(skill.document_types)) {
				if (activeFilter && !activeFilter.includes(dtName) && !activeFilter.includes("*")) {
					continue;
				}
				if (dtConfig && dtConfig.extraction_fields && typeof dtConfig.extraction_fields === "object") {
					for (const fieldName of Object.keys(dtConfig.extraction_fields)) {
						if (fieldName) vars.add(`{${fieldName}}`);
					}
				}
			}
		}
	}

	// 2. Extract dynamic fields from config.document_types (matching active document types if filtered)
	if (appState.config && appState.config.document_types && typeof appState.config.document_types === "object") {
		for (const [dtName, dtConfig] of Object.entries(appState.config.document_types)) {
			if (activeFilter && !activeFilter.includes(dtName) && !activeFilter.includes("*")) {
				continue;
			}
			if (dtConfig && dtConfig.extraction_fields && typeof dtConfig.extraction_fields === "object") {
				for (const fieldName of Object.keys(dtConfig.extraction_fields)) {
					if (fieldName) vars.add(`{${fieldName}}`);
				}
			}
		}
	}

	// 3. Extract dynamic fields from config.folder_structure (always included)
	if (appState.config && Array.isArray(appState.config.folder_structure)) {
		for (const segment of appState.config.folder_structure) {
			if (typeof segment === "string") {
				const matches = segment.match(/\{([^{}]+)\}/g);
				if (matches) {
					matches.forEach((m) => vars.add(m));
				}
			}
		}
	}

	// Dynamic context & time variables
	vars.add("{category}");
	vars.add("{Jahr}");
	vars.add("{Zeit}");

	return Array.from(vars);
}

function insertVariableToAction(taskIdx, actIdx, varName) {
	if (taskIdx >= 0 && taskIdx < currentEditingTasks.length) {
		const actions = currentEditingTasks[taskIdx].actions || [];
		if (actIdx >= 0 && actIdx < actions.length) {
			const act = actions[actIdx];
			if (act.action_type === "TYPE_FILE_PATH") {
				act.file_path = (act.file_path || "") + varName;
			} else if (act.action_type === "TYPE_TEXT") {
				act.text = (act.text || "") + varName;
			}
			renderEditorSteps();
		}
	}
}

function renderEditorSteps() {
	const container = document.getElementById("editorStepsList");
	if (!container) return;

	updateHeaderStepBadge();

	if (currentEditingTasks.length === 0) {
		container.innerHTML = `
			<div class="step-empty-box">
				<div class="step-empty-icon">🤖✨</div>
				<div class="step-empty-title">No actions recorded yet</div>
				<div class="step-empty-desc">
					Click <strong>"Start Live Recording"</strong> to demonstrate your routine on screen, or use the <strong>AI Skill Copilot</strong> above to generate tasks automatically.
				</div>
				<button type="button" class="btn btn-sm btn-danger btn-bold" onclick="startLiveRecording(currentEditingSkill ? currentEditingSkill.name : 'New Skill')">
					<span>🔴</span> Start Live Recording
				</button>
			</div>
		`;
		return;
	}

	container.innerHTML = currentEditingTasks
		.map((task, taskIdx) => {
			const actions = task.actions || [];
			const isFirstTask = taskIdx === 0;
			const isLastTask = taskIdx === currentEditingTasks.length - 1;

			return `
			<div class="workflow-task-card" id="taskCard_${task.id || taskIdx}">
				<div class="workflow-task-header">
					<div class="task-header-left">
						<span class="task-num-badge">📦 Task ${taskIdx + 1}</span>
						<input type="text" class="task-title-input" value="${escapeHtml(task.title || "")}" placeholder="e.g. Open file in target application" aria-label="Task ${taskIdx + 1} Title" onchange="currentEditingTasks[${taskIdx}].title = this.value;" />
					</div>
					<div class="task-header-right">
						<button type="button" class="btn btn-icon btn-sm" onclick="moveTaskUp(${taskIdx})" ${isFirstTask ? "disabled" : ""} title="Move task up">⬆️</button>
						<button type="button" class="btn btn-icon btn-sm" onclick="moveTaskDown(${taskIdx})" ${isLastTask ? "disabled" : ""} title="Move task down">⬇️</button>
						<button type="button" class="btn btn-icon btn-sm btn-danger-icon" onclick="removeEditorTask(${taskIdx})" title="Delete task">🗑️</button>
					</div>
				</div>

				<div class="task-actions-container">
					${
						actions.length === 0
							? `<div class="step-empty-task-notice">No actions in this task yet.</div>`
							: actions
									.map((act, actIdx) => {
										const isFirstAct = actIdx === 0;
										const isLastAct = actIdx === actions.length - 1;
										const badgeStyle = getActionBadgeStyle(act.action_type);
										const isSensitive = isActionSensitive(act);
										let paramText = "";
										if (act.action_type === "FOCUS_WINDOW") paramText = act.window_title || "Remote Desktop*";
										else if (act.action_type === "TYPE_FILE_PATH") paramText = act.file_path || "{document_fullpath}";
										else if (act.action_type === "TYPE_TEXT") {
											paramText = act.text || "";
											if (isSensitive && !act._revealed) {
												paramText = "••••••••••••";
											}
										}
										else if (act.action_type === "WAIT_FOR_ELEMENT") {
											paramText = (act.locator ? (act.locator.prompt || act.locator.value || act.locator.target || "Element") : "Element") + ` (${act.timeout_s || 5}s timeout)`;
										}
										else if (act.action_type === "CALL_SKILL") paramText = `Skill: ${act.skill_id || ""}`;
										else if (act.locator) paramText = act.locator.prompt || act.locator.value || act.locator.target || "";

										const showVariableChips = act.action_type === "TYPE_TEXT" || act.action_type === "TYPE_FILE_PATH";
										const availableVars = showVariableChips ? getAvailableSkillVariables() : [];

										return `
										<div class="action-row-item ${act._editing ? 'action-row-editing' : ''}" id="actionItem_${act.id || actIdx}">
											<div class="action-item-left">
												<span class="action-type-pill ${badgeStyle.badgeClass || "action-pill-focus"}">
													${badgeStyle.label || act.action_type}
												</span>
												${isSensitive ? `<span class="action-type-pill action-pill-secret" title="Security Warning: Sensitive credential or password detected. Plaintext inputs are executed on screen.">🔒 Sensitive</span>` : ""}
												<div class="step-action-desc-col">
													<span class="action-item-desc">${escapeHtml(act.description || act.action_type || "Action")}</span>
													${paramText ? `<span class="action-item-param" title="${escapeHtml(act.text || paramText)}">${escapeHtml(paramText)}</span>` : ""}
													${showVariableChips && availableVars.length > 0 ? `
														<div class="variable-chips-row">
															${availableVars.map(v => `<span class="var-insert-chip" data-var="${escapeHtml(v)}" onclick="insertVariableToAction(${taskIdx}, ${actIdx}, this.dataset.var)" title="Insert variable ${escapeHtml(v)}">+ ${escapeHtml(v)}</span>`).join("")}
														</div>
													` : ""}
												</div>
											</div>
											<div class="action-item-right">
												<button type="button" class="btn btn-icon btn-sm" onclick="toggleActionEdit(${taskIdx}, ${actIdx})" title="${act._editing ? 'Close edit drawer' : 'Edit action parameters'}">${act._editing ? '✖️ Done' : '✏️ Edit'}</button>
												${(act.action_type === "CLICK" || act.action_type === "DOUBLE_CLICK" || act.action_type === "RIGHT_CLICK" || act.action_type === "WAIT_FOR_ELEMENT" || act.action_type === "VERIFY_SCREEN") ? `<button type="button" class="btn btn-icon btn-sm btn-pick-element" onclick="pickElementForAction(${taskIdx}, ${actIdx})" title="🎯 Pick element on screen live">🎯 Pick</button>` : ""}
												${act.action_type === "TYPE_TEXT" && isSensitive ? `<button type="button" class="btn btn-icon btn-sm" onclick="toggleActionReveal(${taskIdx}, ${actIdx})" title="${act._revealed ? 'Hide sensitive text' : 'Reveal sensitive text'}">${act._revealed ? '🙈' : '👁️'}</button>` : ""}
												${act.action_type === "TYPE_TEXT" ? `<button type="button" class="btn btn-icon btn-sm" onclick="toggleActionSecret(${taskIdx}, ${actIdx})" title="${act.is_secret ? 'Remove secret flag' : 'Mark as secret/credential'}">${act.is_secret ? '🔒' : '🔓'}</button>` : ""}
												<button type="button" class="btn btn-icon btn-sm" onclick="moveActionUp(${taskIdx}, ${actIdx})" ${isFirstAct ? "disabled" : ""} title="Move up">⬆️</button>
												<button type="button" class="btn btn-icon btn-sm" onclick="moveActionDown(${taskIdx}, ${actIdx})" ${isLastAct ? "disabled" : ""} title="Move down">⬇️</button>
												<button type="button" class="btn btn-icon btn-sm btn-danger-icon" onclick="removeEditorAction(${taskIdx}, ${actIdx})" title="Remove action">🗑️</button>
											</div>
										</div>
										${act._editing ? `
										<div class="action-inline-editor-card">
											<div class="action-editor-grid-row">
												<label class="action-editor-label">Action Type:</label>
												<select class="form-select form-select-sm action-editor-input" onchange="updateActionProperty(${taskIdx}, ${actIdx}, 'action_type', this.value); renderEditorSteps();">
													<option value="CLICK" ${act.action_type === "CLICK" ? "selected" : ""}>🎯 Click Element</option>
													<option value="DOUBLE_CLICK" ${act.action_type === "DOUBLE_CLICK" ? "selected" : ""}>🖱️ Double Click</option>
													<option value="RIGHT_CLICK" ${act.action_type === "RIGHT_CLICK" ? "selected" : ""}>🖱️ Right Click</option>
													<option value="TYPE_TEXT" ${act.action_type === "TYPE_TEXT" ? "selected" : ""}>⌨️ Type Text</option>
													<option value="TYPE_FILE_PATH" ${act.action_type === "TYPE_FILE_PATH" ? "selected" : ""}>📄 Type File Path</option>
													<option value="FOR_EACH_DOCUMENT" ${act.action_type === "FOR_EACH_DOCUMENT" ? "selected" : ""}>🔁 For Each Document (Loop Case Docs)</option>
													<option value="BRANCH" ${act.action_type === "BRANCH" || act.action_type === "IF_CONDITION" ? "selected" : ""}>🔀 Branch (IF / ELSE)</option>
													<option value="FOR_EACH" ${act.action_type === "FOR_EACH" ? "selected" : ""}>🔄 For Each Item (List Loop)</option>
													<option value="WHILE_LOOP" ${act.action_type === "WHILE_LOOP" ? "selected" : ""}>⏳ While Condition (Polling Loop)</option>
													<option value="EXTRACT_UI_TEXT" ${act.action_type === "EXTRACT_UI_TEXT" ? "selected" : ""}>📥 Extract UI Text</option>
													<option value="VALIDATE_UI_STATE" ${act.action_type === "VALIDATE_UI_STATE" ? "selected" : ""}>🔍 Validate UI State</option>
													<option value="SET_VARIABLE" ${act.action_type === "SET_VARIABLE" ? "selected" : ""}>💾 Set Variable</option>
													<option value="POWERSHELL" ${act.action_type === "POWERSHELL" || act.action_type === "RUN_SCRIPT" ? "selected" : ""}>⚡ PowerShell / Script</option>
													<option value="DELAY" ${act.action_type === "DELAY" || act.action_type === "SLEEP" ? "selected" : ""}>⏱️ Delay / Pause</option>
													<option value="FOCUS_WINDOW" ${act.action_type === "FOCUS_WINDOW" ? "selected" : ""}>🪟 Focus Window</option>
													<option value="WAIT_FOR_ELEMENT" ${act.action_type === "WAIT_FOR_ELEMENT" ? "selected" : ""}>⏳ Wait For Element</option>
													<option value="CALL_SKILL" ${act.action_type === "CALL_SKILL" ? "selected" : ""}>⚡ Call Sub-Skill</option>
												</select>
											</div>
											<div class="action-editor-grid-row">
												<label class="action-editor-label">Description:</label>
												<input type="text" class="form-control form-control-sm action-editor-input" value="${escapeHtml(act.description || "")}" placeholder="Description of this step" onchange="updateActionProperty(${taskIdx}, ${actIdx}, 'description', this.value)" />
											</div>
											${act.action_type === "FOR_EACH_DOCUMENT" ? `
											<div class="action-editor-grid-row">
												<label class="action-editor-label-accent">Document Types:</label>
												<input type="text" class="form-control form-control-sm action-editor-input-cyan" value="${escapeHtml(Array.isArray(act.document_types) ? act.document_types.join(', ') : (act.document_types || '*'))}" placeholder="Fußscan, Rezept, *" onchange="updateActionProperty(${taskIdx}, ${actIdx}, 'document_types', this.value.split(',').map(s => s.trim()).filter(Boolean))" />
											</div>
											<div class="action-editor-grid-row">
												<label class="action-editor-label">On Item Error:</label>
												<select class="form-select form-select-sm action-editor-input" onchange="updateActionProperty(${taskIdx}, ${actIdx}, 'on_item_error', this.value)">
													<option value="ABORT" ${(!act.on_item_error || act.on_item_error === 'ABORT') ? "selected" : ""}>🛑 Abort Loop</option>
													<option value="CONTINUE" ${act.on_item_error === 'CONTINUE' ? "selected" : ""}>⏭️ Skip & Continue Next Doc</option>
													<option value="RETRY" ${act.on_item_error === 'RETRY' ? "selected" : ""}>🔄 Retry Once</option>
												</select>
											</div>
											` : ""}
											${(act.action_type === "BRANCH" || act.action_type === "IF_CONDITION" || act.action_type === "VALIDATE_UI_STATE" || act.action_type === "WHILE_LOOP") ? `
											<div class="action-editor-grid-row">
												<label class="action-editor-label-accent">Condition Expr:</label>
												<input type="text" class="form-control form-control-sm action-editor-input-code" value="${escapeHtml(typeof act.condition === 'string' ? act.condition : (act.condition?.expr || JSON.stringify(act.condition || '')))}" placeholder="{category} == 'Fußscan'" onchange="updateActionProperty(${taskIdx}, ${actIdx}, 'condition', this.value)" />
											</div>
											` : ""}
											${act.action_type === "WHILE_LOOP" ? `
											<div class="action-editor-grid-row">
												<label class="action-editor-label">Max Iterations:</label>
												<input type="number" class="form-control form-control-sm action-editor-input" value="${act.max_iterations || 20}" placeholder="20" onchange="updateActionProperty(${taskIdx}, ${actIdx}, 'max_iterations', parseInt(this.value) || 20)" />
											</div>
											` : ""}
											${act.action_type === "EXTRACT_UI_TEXT" ? `
											<div class="action-editor-grid-row">
												<label class="action-editor-label">Save Variable:</label>
												<input type="text" class="form-control form-control-sm action-editor-input" value="${escapeHtml(act.extract_to_var || act.variable || "ui_extracted_var")}" placeholder="ui_patient_id" onchange="updateActionProperty(${taskIdx}, ${actIdx}, 'extract_to_var', this.value)" />
											</div>
											<div class="action-editor-grid-row">
												<label class="action-editor-label">Provider:</label>
												<select class="form-select form-select-sm action-editor-input" onchange="updateActionProperty(${taskIdx}, ${actIdx}, 'provider', this.value)">
													<option value="auto" ${(!act.provider || act.provider === 'auto') ? "selected" : ""}>🤖 Auto (UIA -> Vision Fallback)</option>
													<option value="uia" ${act.provider === 'uia' ? "selected" : ""}>⚡ UIA (Native Windows Control)</option>
													<option value="vision" ${act.provider === 'vision' ? "selected" : ""}>👁️ Vision (RDP / OCR Pixel)</option>
												</select>
											</div>
											` : ""}
											${act.action_type === "SET_VARIABLE" ? `
											<div class="action-editor-grid-row">
												<label class="action-editor-label">Variable Name:</label>
												<input type="text" class="form-control form-control-sm action-editor-input" value="${escapeHtml(act.variable || "")}" placeholder="my_var" onchange="updateActionProperty(${taskIdx}, ${actIdx}, 'variable', this.value)" />
											</div>
											<div class="action-editor-grid-row">
												<label class="action-editor-label">Value / Formula:</label>
												<input type="text" class="form-control form-control-sm action-editor-input" value="${escapeHtml(act.value || "")}" placeholder="Custom value or {other_var}" onchange="updateActionProperty(${taskIdx}, ${actIdx}, 'value', this.value)" />
											</div>
											` : ""}
											${(act.action_type === "POWERSHELL" || act.action_type === "RUN_SCRIPT" || act.action_type === "EXECUTE_COMMAND") ? `
											<div class="action-editor-grid-row-top">
												<label class="action-editor-label">Command / Script:</label>
												<textarea class="form-control form-control-sm action-editor-textarea-code" rows="5" onchange="updateActionProperty(${taskIdx}, ${actIdx}, 'command', this.value)">${escapeHtml(act.command || act.script || "")}</textarea>
											</div>
											` : ""}
											${act.action_type === "TYPE_TEXT" ? `
											<div class="action-editor-grid-row">
												<label class="action-editor-label">Text to Type:</label>
												<input type="text" class="form-control form-control-sm action-editor-input" value="${escapeHtml(act.text || "")}" placeholder="Text or variable (e.g. {Nachname})" onchange="updateActionProperty(${taskIdx}, ${actIdx}, 'text', this.value)" />
											</div>
											` : ""}
											${act.action_type === "TYPE_FILE_PATH" ? `
											<div class="action-editor-grid-row">
												<label class="action-editor-label">File Path:</label>
												<input type="text" class="form-control form-control-sm action-editor-input" value="${escapeHtml(act.file_path || "{document_fullpath}")}" placeholder="{document_fullpath}" onchange="updateActionProperty(${taskIdx}, ${actIdx}, 'file_path', this.value)" />
											</div>
											` : ""}
											${(act.action_type === "DELAY" || act.action_type === "SLEEP" || act.action_type === "WAIT") ? `
											<div class="action-editor-grid-row">
												<label class="action-editor-label">Delay (ms):</label>
												<input type="number" class="form-control form-control-sm action-editor-input" value="${act.delay_ms !== undefined ? act.delay_ms : (act.duration_s !== undefined ? act.duration_s * 1000 : 500)}" placeholder="500" onchange="updateActionProperty(${taskIdx}, ${actIdx}, 'delay_ms', isNaN(parseInt(this.value)) ? 0 : parseInt(this.value))" />
											</div>
											` : ""}
											${act.action_type === "FOCUS_WINDOW" ? `
											<div class="action-editor-grid-row">
												<label class="action-editor-label">Window Title:</label>
												<input type="text" class="form-control form-control-sm action-editor-input" value="${escapeHtml(act.window_title || "")}" placeholder="CorelDRAW*" onchange="updateActionProperty(${taskIdx}, ${actIdx}, 'window_title', this.value)" />
											</div>
											` : ""}
											${(act.action_type === "CLICK" || act.action_type === "DOUBLE_CLICK" || act.action_type === "RIGHT_CLICK" || act.action_type === "WAIT_FOR_ELEMENT" || act.action_type === "EXTRACT_UI_TEXT") ? `
											<div class="action-editor-grid-row">
												<label class="action-editor-label">Locator Target:</label>
												<input type="text" class="form-control form-control-sm action-editor-input" value="${escapeHtml(act.locator?.prompt || act.locator?.value || act.locator?.automation_id || "")}" placeholder="Button name, automation_id, or OCR text" onchange="updateActionProperty(${taskIdx}, ${actIdx}, 'locator.prompt', this.value)" />
											</div>
											` : ""}
											<div class="action-editor-grid-row-border">
												<label class="action-editor-label-warn">On Error:</label>
												<select class="form-select form-select-sm action-editor-input" onchange="updateActionProperty(${taskIdx}, ${actIdx}, 'on_error', this.value)">
													<option value="ABORT" ${(!act.on_error || act.on_error === 'ABORT') ? "selected" : ""}>🛑 Abort & Stop Workflow</option>
													<option value="CONTINUE" ${act.on_error === 'CONTINUE' ? "selected" : ""}>⏭️ Ignore & Continue</option>
													<option value="RETRY" ${act.on_error === 'RETRY' ? "selected" : ""}>🔄 Retry Step (up to 3x)</option>
												</select>
											</div>
										</div>
										` : ""}
									`;
									})
									.join("")
					}
					<div class="task-add-action-row">
						<button type="button" class="btn btn-sm btn-secondary btn-add-action-task" onclick="addEditorAction(${taskIdx})">
							➕ Add Action to Task ${taskIdx + 1}
						</button>
					</div>
				</div>
			</div>
		`;
		})
		.join("") + `
		<div class="workflow-add-task-row">
			<button type="button" class="btn btn-sm btn-outline-primary btn-add-task" onclick="addEditorTask('Task ' + (currentEditingTasks.length + 1))">
				➕ Add New Task
			</button>
		</div>
	`;
}