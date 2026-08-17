/* ═══════════════════════════════════════════════════════════
   SKILL QUEUE INSPECTOR & EXECUTION CONTROLLER
   ═══════════════════════════════════════════════════════════ */

let draggedQueueItemId = null;
let queuePollTimer = null;

function isQueueInspectorOpen() {
	const container = document.getElementById("queueItemsContainer");
	return Boolean(container && container.offsetParent !== null);
}

function startQueuePolling() {
	if (queuePollTimer) return;
	queuePollTimer = setInterval(async () => {
		if (!isQueueInspectorOpen()) {
			stopQueuePolling();
			return;
		}
		try {
			const qState = await api("/api/skills/queue");
			updateQueueInspectorIfOpen(qState);
			if (!qState.is_running) {
				stopQueuePolling();
			}
		} catch (e) {
			console.debug("Queue poll error:", e);
		}
	}, 1200);
}

function stopQueuePolling() {
	if (queuePollTimer) {
		clearInterval(queuePollTimer);
		queuePollTimer = null;
	}
}

function buildQueueListHtml(items) {
	if (!items || items.length === 0) {
		return `
			<div class="empty-state-box">
				Queue is empty.<br>Add a skill below.
			</div>
		`;
	}

	return items
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
							</div>
						</div>
						<div class="queue-actions-group">
							${statusBadge}
							${
								!isRunning
									? `
								<button type="button" class="btn btn-sm btn-icon queue-remove-btn" onclick="removeQueueItem('${escapeHtml(item.id)}')" title="Remove from queue">
									🗑️
								</button>
							`
									: ""
							}
						</div>
					</div>
				</div>
			`;
		})
		.join("");
}

function updateQueueInspectorIfOpen(qState) {
	if (!qState) return;

	// Update Skills Tab Button Badge in primary sidebar
	const navBtnBadge = document.querySelector(".nav-item[data-tab='skills'] .nav-badge");
	if (navBtnBadge) {
		if (qState.is_running) {
			navBtnBadge.textContent = "▶ Run";
			navBtnBadge.style.display = "";
		} else {
			navBtnBadge.textContent = "";
			navBtnBadge.style.display = "none";
		}
	}

	if (!isQueueInspectorOpen()) return;

	// Update Subtitle
	const subtitleEl = document.querySelector(".app-inspector .inspector-subtitle");
	if (subtitleEl) {
		if (qState.is_running) {
			const activeName = qState.active_item ? qState.active_item.skill_name : "";
			subtitleEl.textContent = activeName ? `▶ Running: ${activeName}` : "▶ Execution running...";
		} else {
			subtitleEl.textContent = "Reorder via drag & drop";
		}
	}

	// Update Status Card
	const statusTitle = document.querySelector(".queue-status-title");
	if (statusTitle) {
		statusTitle.innerHTML = `<span>${qState.is_running ? "▶" : "⏸️"}</span> Status: ${qState.is_running ? "Running" : "Ready"}`;
	}
	const countBadge = document.querySelector(".queue-status-header .badge");
	if (countBadge) {
		countBadge.className = `badge ${qState.is_running ? "badge-running" : "badge-idle"}`;
		countBadge.textContent = `${qState.items.length} Skills`;
	}
	const btnRow = document.querySelector(".queue-btn-row");
	if (btnRow) {
		btnRow.innerHTML = !qState.is_running
			? `
				<button type="button" class="btn btn-primary btn-sm queue-main-btn" onclick="startSkillQueue()">
					▶ Start queue
				</button>
			`
			: `
				<button type="button" class="btn btn-danger btn-sm queue-main-btn" onclick="stopSkillQueue()">
					⏸️ Stop queue
				</button>
			`;
	}

	// Update Items Container
	const container = document.getElementById("queueItemsContainer");
	if (container) {
		container.innerHTML = buildQueueListHtml(qState.items);
	}
}

async function renderQueueInspector() {
	if (typeof openAppInspector !== "function") return;

	let qState = { is_running: false, items: [], active_item: null };
	try {
		qState = await api("/api/skills/queue");
	} catch (e) {
		console.error("Error fetching queue:", e);
	}

	const skillOptions = (state.skills || [])
		.map(
			(s) =>
				`<option value="${escapeHtml(s.id)}">${s.type === "import" ? "📥" : "⚡"} ${escapeHtml(s.name || s.id)}</option>`,
		)
		.join("");

	const queueListHtml = buildQueueListHtml(qState.items);

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
				${
					!qState.is_running
						? `
					<button type="button" class="btn btn-primary btn-sm queue-main-btn" onclick="startSkillQueue()">
						▶ Start queue
					</button>
				`
						: `
					<button type="button" class="btn btn-danger btn-sm queue-main-btn" onclick="stopSkillQueue()">
						⏸️ Stop queue
					</button>
				`
				}
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

	const subtitle = qState.is_running
		? qState.active_item
			? `▶ Running: ${escapeHtml(qState.active_item.skill_name)}`
			: "▶ Execution running..."
		: "Reorder via drag & drop";

	openAppInspector({
		icon: "⚡",
		title: "Skill Queue",
		subtitle: subtitle,
		html: inspectorHtml,
	});

	if (qState.is_running) {
		startQueuePolling();
	}
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
		const qState = await api("/api/skills/queue");
		updateQueueInspectorIfOpen(qState);
	} catch (err) {
		toast("Error reordering queue: " + err.message, "error");
	}
}

async function startSkillQueue() {
	try {
		await api("/api/skills/queue/start", { method: "POST" });
		toast("▶ Skill queue started!");
		const qState = await api("/api/skills/queue");
		updateQueueInspectorIfOpen(qState);
		startQueuePolling();
	} catch (e) {
		toast("Error starting queue: " + e.message, "error");
	}
}

async function stopSkillQueue() {
	try {
		await api("/api/skills/queue/stop", { method: "POST" });
		toast("⏸️ Stopping skill queue...");
		const qState = await api("/api/skills/queue");
		updateQueueInspectorIfOpen(qState);
		stopQueuePolling();
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
		const qState = await api("/api/skills/queue");
		updateQueueInspectorIfOpen(qState);
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
		const qState = await api("/api/skills/queue");
		updateQueueInspectorIfOpen(qState);
	} catch (e) {
		toast("Error removing entry: " + e.message, "error");
	}
}
