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

function renderEditorSteps() {
	const container = document.getElementById("editorStepsList");
	if (!container) return;

	updateHeaderStepBadge();

	if (currentEditingTasks.length === 0) {
		container.innerHTML = `
			<div class="step-empty-box" style="padding: 32px 20px; text-align: center; background: rgba(0,0,0,0.2); border-radius: 8px; border: 1px dashed var(--border);">
				<div style="font-size: 2rem; margin-bottom: 8px;">🤖✨</div>
				<div style="font-weight: 700; color: #f1f5f9; font-size: 0.95rem; margin-bottom: 4px;">No actions recorded yet</div>
				<div style="font-size: 0.8rem; color: #94a3b8; max-width: 460px; margin: 0 auto 16px auto;">
					Click <strong>"Start Live Recording"</strong> to demonstrate your routine on screen, or use the <strong>AI Skill Copilot</strong> above to generate tasks automatically.
				</div>
				<button type="button" class="btn btn-sm btn-danger" onclick="startLiveRecording(currentEditingSkill ? currentEditingSkill.name : 'New Skill')" style="font-weight: 700;">
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
						<input type="text" class="task-title-input" value="${escapeHtml(task.title || "")}" placeholder="e.g. Open file in target application" onchange="currentEditingTasks[${taskIdx}].title = this.value;" />
					</div>
					<div class="task-header-right">
						<button type="button" class="btn btn-icon btn-sm" onclick="moveTaskUp(${taskIdx})" ${isFirstTask ? "disabled" : ""} title="Move task up">⬆️</button>
						<button type="button" class="btn btn-icon btn-sm" onclick="moveTaskDown(${taskIdx})" ${isLastTask ? "disabled" : ""} title="Move task down">⬇️</button>
						<button type="button" class="btn btn-icon btn-sm" onclick="removeEditorTask(${taskIdx})" title="Delete task" style="color: var(--danger);">🗑️</button>
					</div>
				</div>

				<div class="task-actions-container">
					${
						actions.length === 0
							? `<div style="font-size: 0.76rem; color: #64748b; font-style: italic; padding: 6px;">No actions in this task yet.</div>`
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
										else if (act.action_type === "CALL_SKILL") paramText = `Skill: ${act.skill_id || ""}`;
										else if (act.locator) paramText = act.locator.prompt || act.locator.value || act.locator.target || "";

										return `
										<div class="action-row-item" id="actionItem_${act.id || actIdx}">
											<div class="action-item-left">
												<span class="action-type-pill ${badgeStyle.badgeClass || "action-pill-focus"}">
													${badgeStyle.label || act.action_type}
												</span>
												${isSensitive ? `<span class="action-type-pill action-pill-secret" title="Security Warning: Sensitive credential or password detected. Plaintext inputs are executed on screen.">🔒 Sensitive</span>` : ""}
												<div style="display: flex; flex-direction: column; min-width: 0;">
													<span class="action-item-desc">${escapeHtml(act.description || act.action_type || "Action")}</span>
													${paramText ? `<span class="action-item-param" title="${escapeHtml(act.text || paramText)}">${escapeHtml(paramText)}</span>` : ""}
												</div>
											</div>
											<div class="action-item-right">
												${act.action_type === "TYPE_TEXT" && isSensitive ? `<button type="button" class="btn btn-icon btn-sm" onclick="toggleActionReveal(${taskIdx}, ${actIdx})" title="${act._revealed ? 'Hide sensitive text' : 'Reveal sensitive text'}">${act._revealed ? '🙈' : '👁️'}</button>` : ""}
												${act.action_type === "TYPE_TEXT" ? `<button type="button" class="btn btn-icon btn-sm" onclick="toggleActionSecret(${taskIdx}, ${actIdx})" title="${act.is_secret ? 'Remove secret flag' : 'Mark as secret/credential'}">${act.is_secret ? '🔒' : '🔓'}</button>` : ""}
												<button type="button" class="btn btn-icon btn-sm" onclick="moveActionUp(${taskIdx}, ${actIdx})" ${isFirstAct ? "disabled" : ""} title="Move up">⬆️</button>
												<button type="button" class="btn btn-icon btn-sm" onclick="moveActionDown(${taskIdx}, ${actIdx})" ${isLastAct ? "disabled" : ""} title="Move down">⬇️</button>
												<button type="button" class="btn btn-icon btn-sm" onclick="removeEditorAction(${taskIdx}, ${actIdx})" title="Remove action" style="color: var(--danger);">🗑️</button>
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