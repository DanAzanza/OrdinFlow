/* ═══════════════════════════════════════════════════════════
   SKILL QUEUE INSPECTOR & EXECUTION CONTROLLER
   ═══════════════════════════════════════════════════════════ */

let draggedQueueItemId = null;
let queuePollTimer = null;

function isQueueInspectorOpen() {
	const container = document.getElementById("queueItemsContainer");
	const inspector = document.getElementById("appInspector");
	if (!container || !inspector) return false;
	return !inspector.classList.contains("hidden-inspector");
}

function startQueuePolling() {
	if (queuePollTimer) return;
	queuePollTimer = setInterval(async () => {
		try {
			const qState = await api("/api/skills/queue");
			updateQueueInspectorIfOpen(qState);
			updateSkillsSidebarBadge(qState);
			if (!qState.is_running && !qState.is_paused && !isQueueInspectorOpen()) {
				stopQueuePolling();
			}
		} catch (e) {
			console.error("Queue poll error:", e);
		}
	}, 1500);
}

function stopQueuePolling() {
	if (queuePollTimer) {
		clearInterval(queuePollTimer);
		queuePollTimer = null;
	}
}

function updateSkillsSidebarBadge(qState) {
	const badge = document.getElementById("badgeSkills") || document.querySelector(".nav-item[data-tab='skills'] .nav-badge");
	if (!badge) return;

	if (qState && qState.is_running && !qState.is_paused) {
		badge.textContent = "▶️";
		badge.className = "badge nav-badge badge-running";
		badge.style.display = "inline-flex";
	} else if (qState && qState.is_paused) {
		badge.textContent = "⏸️";
		badge.className = "badge nav-badge badge-paused";
		badge.style.display = "inline-flex";
	} else {
		badge.textContent = "";
		badge.style.display = "none";
	}
}

function buildQueueListHtml(items) {
	if (!items || items.length === 0) {
		return `
			<div class="empty-state-box">
				Queue is empty.<br>Add a skill below or enable auto-run.
			</div>
		`;
	}

	return items
		.map((item) => {
			const isRunning = item.status === "running";
			const isFailed = item.status === "failed";
			const isCompleted = item.status === "completed";
			const isPaused = item.status === "paused";

			let statusBadge = `<span class="badge badge-waiting">Waiting</span>`;
			if (isRunning) {
				statusBadge = `<span class="badge badge-running">▶️ Running...</span>`;
			} else if (isPaused) {
				statusBadge = `<span class="badge badge-paused">Paused</span>`;
			} else if (isCompleted) {
				statusBadge = `<span class="badge badge-completed">Completed</span>`;
			} else if (isFailed) {
				statusBadge = `<span class="badge badge-failed">Failed</span>`;
			}

			const icon = item.skill_type === "import" ? "📥" : "⚡";
			const progressMsg = (item.progress && item.progress.message) ? escapeHtml(item.progress.message) : "";
			const progressPct = (item.progress && item.progress.percent) ? item.progress.percent : 0;

			return `
				<div class="queue-item-card ${isRunning ? "queue-item-running" : "queue-item-idle"}" data-queue-id="${escapeHtml(item.id)}" draggable="${!isRunning}" ondragstart="onQueueDragStart(event, this.dataset.queueId)" ondragover="onQueueDragOver(event)" ondragleave="onQueueDragLeave(event)" ondragend="onQueueDragEnd(event)" ondrop="onQueueDrop(event, this.dataset.queueId)">
					<div class="queue-item-header">
						<div class="queue-item-title-group">
							<span class="queue-drag-handle">↕️</span>
							<span class="queue-icon">${icon}</span>
							<div class="min-w-0">
								<div class="queue-name">${escapeHtml(item.skill_name)}</div>
								${isRunning && progressMsg ? `<div class="queue-item-subtitle">${progressMsg}</div>` : ""}
							</div>
						</div>
						<div class="queue-actions-group">
							${statusBadge}
							${
								!isRunning
									? `
								<button type="button" class="btn btn-sm btn-icon queue-remove-btn" data-id="${escapeHtml(item.id)}" onclick="removeQueueItem(this.dataset.id)" title="Remove from queue">
									🗑️
								</button>
							`
									: ""
							}
						</div>
					</div>
					${
						isRunning && progressPct > 0
							? `
						<div class="queue-progress-bar-wrap">
							<div class="queue-progress-bar" style="width: ${progressPct}%"></div>
						</div>
					`
							: ""
					}
				</div>
			`;
		})
		.join("");
}

function updateQueueInspectorIfOpen(qState) {
	if (!qState) return;

	updateSkillsSidebarBadge(qState);

	if (!isQueueInspectorOpen()) return;

	const isRunning = !!qState.is_running;
	const isPaused = !!qState.is_paused;

	// Update Subtitle
	const subtitleEl = document.querySelector(".app-inspector .inspector-subtitle");
	if (subtitleEl) {
		if (isRunning && !isPaused) {
			const activeName = qState.active_item ? qState.active_item.skill_name : "";
			const progMsg = qState.active_item && qState.active_item.progress ? qState.active_item.progress.message : "";
			subtitleEl.textContent = progMsg ? `▶️ ${activeName}: ${progMsg}` : `▶️ Running: ${activeName || "Execution in progress..."}`;
		} else if (isPaused) {
			subtitleEl.textContent = "⏸️ Queue paused";
		} else {
			subtitleEl.textContent = qState.auto_repeat_enabled ? "🔄 Auto-run active (every 5 min)" : "";
		}
	}

	// Update Status Card
	const statusTitle = document.querySelector(".queue-status-title");
	if (statusTitle) {
		if (isRunning && !isPaused) {
			statusTitle.innerHTML = `<span>▶️</span> Status: Running`;
		} else if (isPaused) {
			statusTitle.innerHTML = `<span>⏸️</span> Status: Paused`;
		} else {
			statusTitle.innerHTML = `<span>⏹️</span> Status: Ready`;
		}
	}

	const countBadge = document.querySelector(".queue-status-header .badge");
	if (countBadge) {
		if (isRunning && !isPaused) {
			countBadge.className = "badge badge-running";
			countBadge.textContent = `${qState.items.length} Tasks`;
		} else if (isPaused) {
			countBadge.className = "badge badge-paused";
			countBadge.textContent = `Paused (${qState.items.length})`;
		} else {
			countBadge.className = "badge badge-idle";
			countBadge.textContent = `${qState.items.length} Tasks`;
		}
	}

	const btnRow = document.querySelector(".queue-btn-row");
	if (btnRow) {
		if (isRunning && !isPaused) {
			btnRow.innerHTML = `
				<button type="button" class="btn btn-secondary btn-sm" onclick="pauseSkillQueue()" title="Pause queue execution">
					⏸️ Pause
				</button>
				<button type="button" class="btn btn-danger btn-sm" onclick="stopSkillQueue()" title="Stop queue execution">
					⏹️ Stop
				</button>
			`;
		} else if (isPaused) {
			btnRow.innerHTML = `
				<button type="button" class="btn btn-primary btn-sm" onclick="resumeSkillQueue()" title="Resume queue execution">
					▶️ Resume
				</button>
				<button type="button" class="btn btn-danger btn-sm" onclick="stopSkillQueue()" title="Stop queue execution">
					⏹️ Stop
				</button>
			`;
		} else {
			btnRow.innerHTML = `
				<button type="button" class="btn btn-primary btn-sm queue-main-btn" onclick="startSkillQueue()">
					▶️ Start queue
				</button>
			`;
		}
	}

	// Update auto-repeat toggle state
	const autoToggle = document.getElementById("queueAutoRepeatToggle");
	if (autoToggle) {
		autoToggle.checked = !!qState.auto_repeat_enabled;
	}

	// Update Items Container
	const container = document.getElementById("queueItemsContainer");
	if (container) {
		container.innerHTML = buildQueueListHtml(qState.items);
	}
}

async function renderQueueInspector() {
	if (typeof openAppInspector !== "function") return;

	let qState = { is_running: false, is_paused: false, auto_repeat_enabled: false, items: [], active_item: null };
	try {
		qState = await api("/api/skills/queue");
	} catch (e) {
		console.error("Error fetching queue:", e);
	}

	const isRunning = !!qState.is_running;
	const isPaused = !!qState.is_paused;

	const skillOptions = (state.skills || [])
		.map(
			(s) =>
				`<option value="${escapeHtml(s.id)}">${s.type === "import" ? "📥" : "⚡"} ${escapeHtml(s.name || s.id)}</option>`,
		)
		.join("");

	const queueListHtml = buildQueueListHtml(qState.items);

	let btnRowHtml = `
		<button type="button" class="btn btn-primary btn-sm queue-main-btn" onclick="startSkillQueue()">
			▶️ Start queue
		</button>
	`;
	if (isRunning && !isPaused) {
		btnRowHtml = `
			<button type="button" class="btn btn-secondary btn-sm" onclick="pauseSkillQueue()" title="Pause queue execution">
				⏸️ Pause
			</button>
			<button type="button" class="btn btn-danger btn-sm" onclick="stopSkillQueue()" title="Stop queue execution">
				⏹️ Stop
			</button>
		`;
	} else if (isPaused) {
		btnRowHtml = `
			<button type="button" class="btn btn-primary btn-sm" onclick="resumeSkillQueue()" title="Resume queue execution">
				▶️ Resume
			</button>
			<button type="button" class="btn btn-danger btn-sm" onclick="stopSkillQueue()" title="Stop queue execution">
				⏹️ Stop
			</button>
		`;
	}

	const inspectorHtml = `
		<div class="queue-status-card">
			<div class="queue-status-header">
				<h4 class="queue-status-title">
					<span>${isRunning && !isPaused ? "▶️" : isPaused ? "⏸️" : "⏹️"}</span> Status: ${isRunning && !isPaused ? "Running" : isPaused ? "Paused" : "Ready"}
				</h4>
				<span class="badge ${isRunning && !isPaused ? "badge-running" : isPaused ? "badge-paused" : "badge-idle"}">
					${isPaused ? `Paused (${qState.items.length})` : `${qState.items.length} Tasks`}
				</span>
			</div>
			<div class="queue-btn-row">
				${btnRowHtml}
			</div>
			<div class="queue-auto-repeat-row">
				<label class="queue-toggle-label" for="queueAutoRepeatToggle">
					<input type="checkbox" id="queueAutoRepeatToggle" aria-label="Auto-run queue every 5 min" onchange="toggleQueueAutoRepeat(this.checked)" ${qState.auto_repeat_enabled ? "checked" : ""}>
					<span>🔄 Auto-run queue every 5 min</span>
				</label>
			</div>
		</div>

		<div class="queue-list-section">
			<div class="queue-list-header-row">
				<h4 class="queue-list-title">
					📋 Queue Tasks & Skills
				</h4>
				${qState.items.length > 0 ? `
					<button type="button" class="btn btn-text btn-sm" onclick="clearSkillQueue()" title="Clear queue">
						Clear all
					</button>
				` : ""}
			</div>
			<div id="queueItemsContainer">
				${queueListHtml}
			</div>
		</div>

		<div class="queue-add-card">
			<h4 class="queue-add-title">➕ Add Skill to Queue</h4>
			<div class="queue-add-row">
				<select id="queueAddSkillSelect" class="doc-editor-input queue-add-select" aria-label="Select skill to add to queue">
					${skillOptions || '<option value="">No skills available</option>'}
				</select>
				<button type="button" class="btn btn-accent btn-sm" onclick="addSelectedSkillToQueue()">
					Add
				</button>
			</div>
		</div>
	`;

	const subtitle = isRunning && !isPaused
		? qState.active_item
			? `▶️ Running: ${escapeHtml(qState.active_item.skill_name)}`
			: "▶️ Execution running..."
		: isPaused
			? "⏸️ Queue paused"
			: qState.auto_repeat_enabled
				? "🔄 Auto-run active (every 5 min)"
				: "";

	openAppInspector({
		icon: "⚡",
		title: "Skill Queue",
		subtitle: subtitle,
		html: inspectorHtml,
	});

	updateSkillsSidebarBadge(qState);
	startQueuePolling();
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
	const card = e.currentTarget;
	if (card && !card.classList.contains("queue-drag-over")) {
		document.querySelectorAll(".queue-item-card.queue-drag-over").forEach((el) => el.classList.remove("queue-drag-over"));
		card.classList.add("queue-drag-over");
	}
}

function onQueueDragLeave(e) {
	const card = e.currentTarget;
	if (card) {
		card.classList.remove("queue-drag-over");
	}
}

function onQueueDragEnd() {
	draggedQueueItemId = null;
	document.querySelectorAll(".queue-item-card.queue-drag-over").forEach((el) => el.classList.remove("queue-drag-over"));
}

async function onQueueDrop(e, targetId) {
	e.preventDefault();
	document.querySelectorAll(".queue-item-card.queue-drag-over").forEach((el) => el.classList.remove("queue-drag-over"));
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
		const btn = document.querySelector(".queue-main-btn");
		if (btn) {
			btn.disabled = true;
			btn.textContent = "▶️ Starting...";
		}
		const res = await api("/api/skills/queue/start", { method: "POST" });
		const qState = await api("/api/skills/queue");
		updateQueueInspectorIfOpen(qState);
		updateSkillsSidebarBadge(qState);
		if (qState.is_running) {
			toast("▶️ Skill queue started!");
			startQueuePolling();
		} else {
			toast("No pending tasks in queue.", "info");
		}
	} catch (e) {
		toast("Error starting queue: " + e.message, "error");
		const qState = await api("/api/skills/queue").catch(() => null);
		if (qState) {
			updateQueueInspectorIfOpen(qState);
			updateSkillsSidebarBadge(qState);
		}
	}
}

async function pauseSkillQueue() {
	try {
		await api("/api/skills/queue/pause", { method: "POST" });
		toast("⏸️ Skill queue paused.");
		const qState = await api("/api/skills/queue");
		updateQueueInspectorIfOpen(qState);
		updateSkillsSidebarBadge(qState);
	} catch (e) {
		toast("Error pausing queue: " + e.message, "error");
	}
}

async function resumeSkillQueue() {
	try {
		await api("/api/skills/queue/resume", { method: "POST" });
		toast("▶️ Skill queue resumed.");
		const qState = await api("/api/skills/queue");
		updateQueueInspectorIfOpen(qState);
		updateSkillsSidebarBadge(qState);
		startQueuePolling();
	} catch (e) {
		toast("Error resuming queue: " + e.message, "error");
	}
}

async function stopSkillQueue() {
	try {
		const btn = document.querySelector(".queue-main-btn");
		if (btn) {
			btn.disabled = true;
			btn.textContent = "⏹️ Stopping...";
		}
		await api("/api/skills/queue/stop", { method: "POST" });
		toast("⏹️ Skill queue stopped.");
		const qState = await api("/api/skills/queue");
		updateQueueInspectorIfOpen(qState);
		updateSkillsSidebarBadge(qState);
		stopQueuePolling();
	} catch (e) {
		toast("Error stopping queue: " + e.message, "error");
	}
}

async function toggleQueueAutoRepeat(enabled) {
	try {
		const res = await api("/api/skills/queue/auto_repeat", {
			method: "POST",
			body: JSON.stringify({ enabled: enabled, interval_seconds: 300 }),
		});
		if (res.auto_repeat_enabled) {
			toast("🔄 Auto-run active (every 5 min)");
		} else {
			toast("Auto-run disabled.");
		}
		const qState = await api("/api/skills/queue");
		updateQueueInspectorIfOpen(qState);
	} catch (e) {
		toast("Error updating auto-run: " + e.message, "error");
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

async function clearSkillQueue() {
	try {
		await api("/api/skills/queue/clear", { method: "POST" });
		toast("Queue cleared.");
		const qState = await api("/api/skills/queue");
		updateQueueInspectorIfOpen(qState);
	} catch (e) {
		toast("Error clearing queue: " + e.message, "error");
	}
}
