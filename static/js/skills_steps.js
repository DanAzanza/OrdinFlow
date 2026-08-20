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
	const badge = document.getElementById("skillHeaderBadge");
	if (badge && currentEditingSkill && currentEditingSkill.type !== "import") {
		const taskCount = currentEditingTasks.length;
		badge.textContent = `${taskCount} ${taskCount === 1 ? "Task" : "Tasks"} (${totalActions} ${totalActions === 1 ? "Action" : "Actions"})`;
	}

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

function renderEditorSteps() {
	const container = document.getElementById("editorStepsList");
	if (!container) return;

	updateHeaderStepBadge();

	if (currentEditingTasks.length === 0) {
		container.innerHTML = `
			<div class="step-empty-box" style="padding: 24px; text-align: center; background: rgba(0,0,0,0.2); border-radius: 8px; border: 1px dashed var(--border);">
				<div style="font-size: 1.8rem; margin-bottom: 8px;">🤖✨</div>
				<div style="font-weight: 700; color: #f1f5f9; margin-bottom: 4px;">No tasks in this skill yet</div>
				<div style="font-size: 0.8rem; color: #94a3b8; max-width: 440px; margin: 0 auto 14px auto;">
					Click <strong>"Start Live Recording"</strong> below to demonstrate the workflow, or add a task manually.
				</div>
				<button type="button" class="btn btn-sm btn-danger" onclick="startLiveRecording(currentEditingSkill ? currentEditingSkill.name : 'New Skill')">
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
						<button type="button" class="btn btn-sm btn-secondary" onclick="addEditorAction(${taskIdx})" title="Add action to this task" style="font-size: 0.72rem; padding: 2px 7px;">
							<span>➕</span> Action
						</button>
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
										const targetVal = (act.locator && (act.locator.prompt || act.locator.value || act.locator.target)) || "";

										return `
										<div class="action-row-item" id="actionItem_${act.id || actIdx}" style="display: flex; gap: 8px; align-items: center; padding: 8px 10px; background: rgba(0,0,0,0.25); border-radius: 6px; margin-bottom: 6px; border: 1px solid rgba(255,255,255,0.06);">
											<select class="doc-editor-input" style="width: 150px; flex-shrink: 0; padding: 4px 6px; font-size: 0.78rem;" onchange="currentEditingTasks[${taskIdx}].actions[${actIdx}].action_type = this.value; renderEditorSteps();">
												<option value="CLICK" ${act.action_type === "CLICK" ? "selected" : ""}>🎯 Click (Button / Element)</option>
												<option value="DOUBLE_CLICK" ${act.action_type === "DOUBLE_CLICK" ? "selected" : ""}>🖱️ Double Click</option>
												<option value="TYPE_FILE_PATH" ${act.action_type === "TYPE_FILE_PATH" ? "selected" : ""}>📄 File Path</option>
												<option value="TYPE_TEXT" ${act.action_type === "TYPE_TEXT" ? "selected" : ""}>⌨️ Text / Variable</option>
												<option value="FOCUS_WINDOW" ${act.action_type === "FOCUS_WINDOW" ? "selected" : ""}>🪟 Focus Window</option>
												<option value="VERIFY_SCREEN" ${act.action_type === "VERIFY_SCREEN" ? "selected" : ""}>👁️ Verify Screen</option>
												<option value="CALL_SKILL" ${act.action_type === "CALL_SKILL" ? "selected" : ""}>⚡ Call Sub-Skill</option>
											</select>

											${
												act.action_type === "FOCUS_WINDOW"
													? `<input type="text" class="doc-editor-input" style="flex: 1; padding: 4px 8px; font-size: 0.8rem;" value="${escapeHtml(act.window_title || "Remote Desktop*")}" placeholder="Window title (e.g. CorelDRAW*)" onchange="currentEditingTasks[${taskIdx}].actions[${actIdx}].window_title = this.value;" />`
													: act.action_type === "TYPE_FILE_PATH"
													? `<input type="text" class="doc-editor-input" style="flex: 1; padding: 4px 8px; font-size: 0.8rem;" value="${escapeHtml(act.file_path || "{document_fullpath}")}" placeholder="File path (e.g. {document_fullpath})" onchange="currentEditingTasks[${taskIdx}].actions[${actIdx}].file_path = this.value;" />`
													: act.action_type === "TYPE_TEXT"
													? `<input type="text" class="doc-editor-input" style="flex: 1; padding: 4px 8px; font-size: 0.8rem;" value="${escapeHtml(act.text || "")}" placeholder="Text to type (e.g. {Nachname})" onchange="currentEditingTasks[${taskIdx}].actions[${actIdx}].text = this.value;" />`
													: `<input type="text" class="doc-editor-input" style="flex: 1; padding: 4px 8px; font-size: 0.8rem;" value="${escapeHtml(targetVal)}" placeholder="Button label or element name (e.g. File, Save)" onchange="if(!currentEditingTasks[${taskIdx}].actions[${actIdx}].locator) currentEditingTasks[${taskIdx}].actions[${actIdx}].locator={}; currentEditingTasks[${taskIdx}].actions[${actIdx}].locator.prompt = this.value; currentEditingTasks[${taskIdx}].actions[${actIdx}].locator.type = 'auto';" />`
											}

											<input type="text" class="doc-editor-input" style="width: 170px; flex-shrink: 0; padding: 4px 8px; font-size: 0.78rem; opacity: 0.8;" value="${escapeHtml(act.description || "")}" placeholder="Description..." onchange="currentEditingTasks[${taskIdx}].actions[${actIdx}].description = this.value;" />

											<div class="action-item-right" style="display: flex; gap: 4px; flex-shrink: 0;">
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