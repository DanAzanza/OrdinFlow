/* ═══════════════════════════════════════════════════════════
   SKILLS TASK & ACTION EDITOR MODULE (Hierarchical Workflows)
   ═══════════════════════════════════════════════════════════ */

let currentEditingTasks = [];
let workflowViewMode = "simple"; // "simple" (MFA friendly) or "expert"
let actionExpandedMap = {};

function setWorkflowViewMode(mode) {
	workflowViewMode = mode;
	const btnSimple = document.getElementById("btnViewModeSimple");
	const btnExpert = document.getElementById("btnViewModeExpert");
	if (btnSimple && btnExpert) {
		btnSimple.classList.toggle("active", mode === "simple");
		btnExpert.classList.toggle("active", mode === "expert");
	}
	renderEditorSteps();
}

function getActionBadgeStyle(actionType) {
	switch (actionType) {
		case "FOCUS_WINDOW":
			return { label: "🪟 FENSTER", badgeClass: "action-pill-focus", icon: "🪟" };
		case "CLICK":
			return { label: "🎯 KLICK", badgeClass: "action-pill-click", icon: "🎯" };
		case "DOUBLE_CLICK":
			return { label: "🖱️ DOPPELKLICK", badgeClass: "action-pill-click", icon: "🖱️" };
		case "TYPE_TEXT":
			return { label: "⌨️ TEXT", badgeClass: "action-pill-type", icon: "⌨️" };
		case "TYPE_FILE_PATH":
			return { label: "📄 DATEI", badgeClass: "action-pill-path", icon: "📄" };
		case "VERIFY_SCREEN":
			return { label: "👁️ PRÜFUNG", badgeClass: "action-pill-verify", icon: "👁️" };
		case "CALL_SKILL":
			return { label: "⚡ SUB-ROUTINE", badgeClass: "action-pill-skill", icon: "⚡" };
		default:
			return { label: actionType || "AKTION", badgeClass: "action-pill-focus", icon: "⚙️" };
	}
}

function addEditorTask(title = "Neue Aufgabe", actions = []) {
	const taskIdx = currentEditingTasks.length + 1;
	const newTask = {
		id: `task_${taskIdx}`,
		title: title,
		actions: actions.length > 0 ? actions : [
			{
				id: `act_${Date.now()}_1`,
				action_type: "CLICK",
				description: "Klicke auf Element",
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

function addEditorStep(taskIdx = null) {
	if (currentEditingTasks.length === 0) {
		addEditorTask("Aufgabe 1: Programm ausführen");
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
		description: "Klicke auf Element",
		locator: { type: "auto", prompt: "" },
		delay_ms: 300,
	};
	task.actions.push(newAct);
	renderEditorSteps();
	updateHeaderStepBadge();
}

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

function toggleActionExpand(actId) {
	actionExpandedMap[actId] = !actionExpandedMap[actId];
	renderEditorSteps();
}

function expandAllSteps() {
	currentEditingTasks.forEach((t) => {
		(t.actions || []).forEach((a) => {
			actionExpandedMap[a.id] = true;
		});
	});
	renderEditorSteps();
}

function collapseAllSteps() {
	actionExpandedMap = {};
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
		badge.textContent = `${taskCount} ${taskCount === 1 ? "Aufgabe" : "Aufgaben"} (${totalActions} Aktionen)`;
	}

	const statsBadge = document.getElementById("workflowStatsBadge");
	if (statsBadge) {
		statsBadge.textContent = `${currentEditingTasks.length} Tasks · ${totalActions} Actions`;
	}
}

function getFlattenedSteps() {
	const flat = [];
	currentEditingTasks.forEach((t) => {
		(t.actions || []).forEach((a) => {
			flat.push(a);
		});
	});
	return flat;
}

function renderEditorSteps() {
	const container = document.getElementById("editorStepsList");
	if (!container) return;

	updateHeaderStepBadge();

	if (currentEditingTasks.length === 0) {
		container.innerHTML = `
			<div class="step-empty-box" style="padding: 24px; text-align: center; background: rgba(0,0,0,0.2); border-radius: 8px; border: 1px dashed var(--border);">
				<div style="font-size: 1.8rem; margin-bottom: 8px;">🤖✨</div>
				<div style="font-weight: 700; color: #f1f5f9; margin-bottom: 4px;">Noch keine Aufgaben in diesem Workflow</div>
				<div style="font-size: 0.8rem; color: #94a3b8; max-width: 440px; margin: 0 auto 14px auto;">
					Klicke unten auf <strong>„Live-Aufnahme starten“</strong>, um den Ablauf vorzumachen, oder erstelle eine Aufgabe manuell.
				</div>
				<button type="button" class="btn btn-sm btn-danger" onclick="startLiveRecording(currentEditingSkill ? currentEditingSkill.name : 'New Workflow')">
					<span>🔴</span> Live-Aufnahme starten
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
						<span class="task-num-badge">📦 Aufgabe ${taskIdx + 1}</span>
						<input type="text" class="task-title-input" value="${escapeHtml(task.title || "")}" placeholder="z. B. Datei im Programm öffnen" onchange="currentEditingTasks[${taskIdx}].title = this.value;" />
					</div>
					<div class="task-header-right">
						<button type="button" class="btn btn-icon btn-sm" onclick="moveTaskUp(${taskIdx})" ${isFirstTask ? "disabled" : ""} title="Aufgabe nach oben">⬆️</button>
						<button type="button" class="btn btn-icon btn-sm" onclick="moveTaskDown(${taskIdx})" ${isLastTask ? "disabled" : ""} title="Aufgabe nach unten">⬇️</button>
						<button type="button" class="btn btn-sm btn-secondary" onclick="addEditorStep(${taskIdx})" title="Aktion zu dieser Aufgabe hinzufügen" style="font-size: 0.72rem; padding: 2px 7px;">
							<span>➕</span> Aktion
						</button>
						<button type="button" class="btn btn-icon btn-sm" onclick="removeEditorTask(${taskIdx})" title="Aufgabe löschen" style="color: var(--danger);">🗑️</button>
					</div>
				</div>

				<div class="task-actions-container">
					${
						actions.length === 0
							? `<div style="font-size: 0.76rem; color: #64748b; font-style: italic; padding: 6px;">Keine Aktionen in dieser Aufgabe.</div>`
							: actions
									.map((act, actIdx) => {
										const badgeStyle = getActionBadgeStyle(act.action_type);
										const isFirstAct = actIdx === 0;
										const isLastAct = actIdx === actions.length - 1;
										const isExpanded = workflowViewMode === "expert" || !!actionExpandedMap[act.id];
										const targetVal = (act.locator && (act.locator.prompt || act.locator.value || act.locator.target)) || "";

										return `
										<div class="action-row-item" id="actionItem_${act.id || actIdx}">
											<div class="action-item-left">
												<span class="action-type-pill ${badgeStyle.badgeClass}">${badgeStyle.label}</span>
												<input type="text" class="doc-editor-input" style="padding: 4px 8px; font-size: 0.8rem; background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.08);" value="${escapeHtml(act.description || "")}" placeholder="Beschreibung der Aktion..." onchange="currentEditingTasks[${taskIdx}].actions[${actIdx}].description = this.value;" />
												
												${
													act.action_type === "FOCUS_WINDOW"
														? `<span class="action-item-param" title="Zielfenster">🪟 ${escapeHtml(act.window_title || "Remote Desktop*")}</span>`
														: act.action_type === "TYPE_FILE_PATH"
														? `<span class="action-item-param" title="Dateipfad">📄 ${escapeHtml(act.file_path || "{document_fullpath}")}</span>`
														: act.action_type === "TYPE_TEXT"
														? `<span class="action-item-param" title="Eingabe">⌨️ ${escapeHtml(act.text || "")}</span>`
														: targetVal
														? `<span class="action-item-param" title="Element / Button">🎯 ${escapeHtml(targetVal)}</span>`
														: ""
												}
											</div>

											<div class="action-item-right">
												<button type="button" class="btn btn-icon btn-sm" onclick="moveActionUp(${taskIdx}, ${actIdx})" ${isFirstAct ? "disabled" : ""} title="Nach oben">⬆️</button>
												<button type="button" class="btn btn-icon btn-sm" onclick="moveActionDown(${taskIdx}, ${actIdx})" ${isLastAct ? "disabled" : ""} title="Nach unten">⬇️</button>
												<button type="button" class="btn btn-icon btn-sm" onclick="toggleActionExpand('${act.id}')" title="Details / Expertenfelder anpassen">⚙️</button>
												<button type="button" class="btn btn-icon btn-sm" onclick="removeEditorAction(${taskIdx}, ${actIdx})" title="Aktion entfernen" style="color: var(--danger);">🗑️</button>
											</div>
										</div>

										${
											isExpanded
												? `
										<div class="action-details-panel" style="padding: 10px 14px; background: rgba(0,0,0,0.3); border-radius: 6px; margin-bottom: 6px; border: 1px solid rgba(255,255,255,0.06);">
											<div class="grid-2col" style="gap: 10px;">
												<div class="form-group" style="margin: 0;">
													<label class="doc-editor-label">Aktions-Typ</label>
													<select class="doc-editor-input" onchange="currentEditingTasks[${taskIdx}].actions[${actIdx}].action_type = this.value; renderEditorSteps();">
														<option value="CLICK" ${act.action_type === "CLICK" ? "selected" : ""}>🎯 Klick (Button / Element)</option>
														<option value="DOUBLE_CLICK" ${act.action_type === "DOUBLE_CLICK" ? "selected" : ""}>🖱️ Doppelklick</option>
														<option value="TYPE_TEXT" ${act.action_type === "TYPE_TEXT" ? "selected" : ""}>⌨️ Text / Variablen eintippen</option>
														<option value="TYPE_FILE_PATH" ${act.action_type === "TYPE_FILE_PATH" ? "selected" : ""}>📄 Dateipfad übergeben</option>
														<option value="FOCUS_WINDOW" ${act.action_type === "FOCUS_WINDOW" ? "selected" : ""}>🪟 Fenster fokussieren</option>
														<option value="VERIFY_SCREEN" ${act.action_type === "VERIFY_SCREEN" ? "selected" : ""}>👁️ Bildschirminhalt prüfen</option>
														<option value="CALL_SKILL" ${act.action_type === "CALL_SKILL" ? "selected" : ""}>⚡ Sub-Routine aufrufen</option>
													</select>
												</div>

												${
													act.action_type === "FOCUS_WINDOW"
														? `
													<div class="form-group" style="margin: 0;">
														<label class="doc-editor-label">🪟 Zielfenster-Titel (Wildcard / Regex)</label>
														<input type="text" class="doc-editor-input" value="${escapeHtml(act.window_title || "Remote Desktop*")}" onchange="currentEditingTasks[${taskIdx}].actions[${actIdx}].window_title = this.value;" />
													</div>
												`
														: act.action_type === "TYPE_FILE_PATH"
														? `
													<div class="form-group" style="margin: 0;">
														<label class="doc-editor-label">📄 Dateipfad-Platzhalter</label>
														<input type="text" class="doc-editor-input" value="${escapeHtml(act.file_path || "{document_fullpath}")}" onchange="currentEditingTasks[${taskIdx}].actions[${actIdx}].file_path = this.value;" />
													</div>
												`
														: act.action_type === "TYPE_TEXT"
														? `
													<div class="form-group" style="margin: 0;">
														<label class="doc-editor-label">⌨️ Einzutippender Text / Variablen</label>
														<input type="text" class="doc-editor-input" value="${escapeHtml(act.text || "")}" placeholder="z. B. {Nachname}, {Datum}" onchange="currentEditingTasks[${taskIdx}].actions[${actIdx}].text = this.value;" />
													</div>
												`
														: `
													<div class="form-group" style="margin: 0;">
														<label class="doc-editor-label">🎯 Ziel-Element / Button-Text</label>
														<input type="text" class="doc-editor-input" value="${escapeHtml(targetVal)}" placeholder="z. B. 'Speichern' Button" onchange="if(!currentEditingTasks[${taskIdx}].actions[${actIdx}].locator) currentEditingTasks[${taskIdx}].actions[${actIdx}].locator={}; currentEditingTasks[${taskIdx}].actions[${actIdx}].locator.prompt = this.value; currentEditingTasks[${taskIdx}].actions[${actIdx}].locator.type = 'auto';" />
													</div>
												`
												}
											</div>
										</div>
									`
												: ""
										}
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