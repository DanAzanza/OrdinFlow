/* ═══════════════════════════════════════════════════════════
   SKILLS TASK & ACTION EDITOR MODULE (Clean Hierarchical Editor)
   ═══════════════════════════════════════════════════════════ */

let currentEditingTasks = [];

function getActionBadgeStyle(actionType) {
	switch (actionType) {
		case "FOCUS_WINDOW":
			return { label: "🪟 Focus Window", badgeClass: "action-pill-focus", icon: "🪟" };
		case "CLICK":
			return { label: "🎯 Click", badgeClass: "action-pill-click", icon: "🎯" };
		case "DOUBLE_CLICK":
			return { label: "🖱️ Double Click", badgeClass: "action-pill-click", icon: "🖱️" };
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
		default:
			return { label: actionType || "Action", badgeClass: "action-pill-focus", icon: "⚙️" };
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
										<div class="action-row-item" id="actionItem_${act.id || actIdx}">
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
															${availableVars.map(v => `<span class="var-insert-chip" onclick="insertVariableToAction(${taskIdx}, ${actIdx}, '${escapeHtml(v)}')" title="Insert variable ${escapeHtml(v)}">+ ${escapeHtml(v)}</span>`).join("")}
														</div>
													` : ""}
												</div>
											</div>
											<div class="action-item-right">
												${(act.action_type === "CLICK" || act.action_type === "DOUBLE_CLICK" || act.action_type === "RIGHT_CLICK" || act.action_type === "WAIT_FOR_ELEMENT" || act.action_type === "VERIFY_SCREEN") ? `<button type="button" class="btn btn-icon btn-sm btn-pick-element" onclick="pickElementForAction(${taskIdx}, ${actIdx})" title="🎯 Pick element on screen live">🎯 Pick</button>` : ""}
												${act.action_type === "TYPE_TEXT" && isSensitive ? `<button type="button" class="btn btn-icon btn-sm" onclick="toggleActionReveal(${taskIdx}, ${actIdx})" title="${act._revealed ? 'Hide sensitive text' : 'Reveal sensitive text'}">${act._revealed ? '🙈' : '👁️'}</button>` : ""}
												${act.action_type === "TYPE_TEXT" ? `<button type="button" class="btn btn-icon btn-sm" onclick="toggleActionSecret(${taskIdx}, ${actIdx})" title="${act.is_secret ? 'Remove secret flag' : 'Mark as secret/credential'}">${act.is_secret ? '🔒' : '🔓'}</button>` : ""}
												<button type="button" class="btn btn-icon btn-sm" onclick="moveActionUp(${taskIdx}, ${actIdx})" ${isFirstAct ? "disabled" : ""} title="Move up">⬆️</button>
												<button type="button" class="btn btn-icon btn-sm" onclick="moveActionDown(${taskIdx}, ${actIdx})" ${isLastAct ? "disabled" : ""} title="Move down">⬇️</button>
												<button type="button" class="btn btn-icon btn-sm btn-danger-icon" onclick="removeEditorAction(${taskIdx}, ${actIdx})" title="Remove action">🗑️</button>
											</div>
										</div>
									`;
									})
									.join("")
					}
				</div>
			</div>
		`;
		})
		.join("");
}