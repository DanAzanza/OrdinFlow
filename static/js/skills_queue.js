/* ═══════════════════════════════════════════════════════════
   SKILL QUEUE INSPECTOR & EXECUTION CONTROLLER
   ═══════════════════════════════════════════════════════════ */

let draggedQueueItemId = null;
let queuePollInterval = null;

async function renderQueueInspector() {
	if (typeof openAppInspector !== "function") return;

	let qState = { is_running: false, items: [] };
	try {
		qState = await api("/api/skills/queue");
	} catch (e) {
		console.error("Error fetching queue:", e);
	}

	// Update Skills Tab Button Indicator Emoji
	const navBtnLabel = document.querySelector(".nav-item[data-tab='skills'] .nav-label");
	if (navBtnLabel) {
		navBtnLabel.textContent = qState.is_running ? "▶ Skills" : "Skills";
	}

	const skillOptions = (state.skills || [])
		.map((s) => `<option value="${escapeHtml(s.id)}">${s.type === "import" ? "📥" : "⚡"} ${escapeHtml(s.name || s.id)}</option>`)
		.join("");

	let queueListHtml = "";
	if (qState.items.length === 0) {
		queueListHtml = `
			<div class="empty-state-box">
				Queue is empty.<br>Add a skill below.
			</div>
		`;
	} else {
		queueListHtml = qState.items
			.map((item, index) => {
				const isRunning = item.status === "running";
				const isFailed = item.status === "failed";
				const isCompleted = item.status === "completed";

				let statusBadge = `<span class="badge badge-waiting">Waiting</span>`;
				if (isRunning) {
					statusBadge = `<span class="badge badge-running">▶ Running...</span>`;
				} else if (isCompleted) {
					statusBadge = `<span class="badge badge-completed">Completed</span>`;
				} else if (isFailed) {
					statusBadge = `<span class="badge badge-failed">Failed</span>`;
				}

				const icon = item.skill_type === "import" ? "📥" : "⚡";

				return `
					<div class="queue-item-card ${isRunning ? "queue-item-running" : "queue-item-idle"}" data-queue-id="${escapeHtml(item.id)}" draggable="${!isRunning}" ondragstart="onQueueDragStart(event, '${escapeHtml(item.id)}')" ondragover="onQueueDragOver(event)" ondrop="onQueueDrop(event, '${escapeHtml(item.id)}')">
						<div class="queue-item-header">
							<div class="queue-item-title-group">
								<span class="queue-drag-handle">⋮⋮</span>
								<span class="queue-icon">${icon}</span>
								<div style="min-width: 0;">
									<div class="queue-name">${escapeHtml(item.skill_name)}</div>
									<div class="queue-meta">#${index + 1} · ID: ${escapeHtml(item.id)}</div>
								</div>
							</div>
							<div class="queue-actions-group">
								${statusBadge}
								${!isRunning ? `
									<button type="button" class="btn btn-sm btn-icon queue-remove-btn" onclick="removeQueueItem('${escapeHtml(item.id)}')" title="Remove from queue">
										🗑️
									</button>
								` : ""}
							</div>
						</div>
					</div>
				`;
			})
			.join("");
	}

	const inspectorHtml = `
		<div class="queue-status-card">
			<div class="queue-status-header">
				<h4 class="queue-status-title">
					<span>${qState.is_running ? "▶" : "⏸️"}</span> Status: ${qState.is_running ? "Running" : "Ready"}
				</h4>
				<span class="badge ${qState.is_running ? "badge-running" : "badge-idle"}">
					${qState.items.length} Skills
				</span>
			</div>
			<div class="queue-btn-row">
				${!qState.is_running ? `
					<button type="button" class="btn btn-primary btn-sm queue-main-btn" onclick="startSkillQueue()">
						▶ Start queue
					</button>
				` : `
					<button type="button" class="btn btn-danger btn-sm queue-main-btn" onclick="stopSkillQueue()">
						⏸️ Stop queue
					</button>
				`}
			</div>
		</div>

		<div class="queue-list-section">
			<h4 class="queue-list-title">
				📋 Queued Skills (Drag & Drop to reorder)
			</h4>
			<div id="queueItemsContainer">
				${queueListHtml}
			</div>
		</div>

		<div class="queue-add-card">
			<h4 class="queue-add-title">➕ Add Skill to Queue</h4>
			<div class="queue-add-row">
				<select id="queueAddSkillSelect" class="doc-editor-input queue-add-select">
					${skillOptions || '<option value="">No skills available</option>'}
				</select>
				<button type="button" class="btn btn-accent btn-sm" onclick="addSelectedSkillToQueue()">
					Add
				</button>
			</div>
		</div>
	`;

	openAppInspector({
		icon: "⚡",
		title: "Skill Queue",
		subtitle: qState.is_running ? "▶ Execution running..." : "Reorder via drag & drop",
		html: inspectorHtml,
	});
}

function onQueueDragStart(e, itemId) {
	draggedQueueItemId = itemId;
	if (e.dataTransfer) {
		e.dataTransfer.effectAllowed = "move";
		e.dataTransfer.setData("text/plain", itemId);
	}
}

function onQueueDragOver(e) {
	e.preventDefault();
	if (e.dataTransfer) {
		e.dataTransfer.dropEffect = "move";
	}
}

async function onQueueDrop(e, targetId) {
	e.preventDefault();
	if (!draggedQueueItemId || draggedQueueItemId === targetId) return;

	const currentNodes = Array.from(document.querySelectorAll("[data-queue-id]"));
	const currentIds = currentNodes.map((el) => el.dataset.queueId);

	const fromIdx = currentIds.indexOf(draggedQueueItemId);
	const toIdx = currentIds.indexOf(targetId);

	if (fromIdx === -1 || toIdx === -1) return;

	currentIds.splice(fromIdx, 1);
	currentIds.splice(toIdx, 0, draggedQueueItemId);

	try {
		await api("/api/skills/queue/reorder", {
			method: "POST",
			body: JSON.stringify({ item_ids: currentIds }),
		});
		renderQueueInspector();
	} catch (err) {
		toast("Error reordering queue: " + err.message, "error");
	}
}

async function startSkillQueue() {
	try {
		await api("/api/skills/queue/start", { method: "POST" });
		toast("▶ Skill queue started!");
		renderQueueInspector();
	} catch (e) {
		toast("Error starting queue: " + e.message, "error");
	}
}

async function stopSkillQueue() {
	try {
		await api("/api/skills/queue/stop", { method: "POST" });
		toast("⏸️ Stopping skill queue...");
		renderQueueInspector();
	} catch (e) {
		toast("Error stopping queue: " + e.message, "error");
	}
}

async function addSelectedSkillToQueue() {
	const sel = document.getElementById("queueAddSkillSelect");
	if (!sel || !sel.value) return;

	const skillId = sel.value;
	try {
		await api("/api/skills/queue/add", {
			method: "POST",
			body: JSON.stringify({ skill_id: skillId, context: {} }),
		});
		toast("Skill added to queue!");
		renderQueueInspector();
	} catch (e) {
		toast("Error adding to queue: " + e.message, "error");
	}
}

async function removeQueueItem(queueId) {
	try {
		await api("/api/skills/queue/remove", {
			method: "POST",
			body: JSON.stringify({ queue_id: queueId }),
		});
		toast("Entry removed from queue.");
		renderQueueInspector();
	} catch (e) {
		toast("Error removing entry: " + e.message, "error");
	}
}
