function switchTab(name) {
	resetAppInspectorContent();

	document
		.querySelectorAll(".tab-btn, .nav-item")
		.forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
	document
		.querySelectorAll(".tab-content")
		.forEach((c) => c.classList.toggle("active", c.id === "tab-" + name));

	const inspector = document.getElementById("appInspector");
	if (inspector) {
		inspector.style.display = (name === "config") ? "none" : "flex";
	}

	if (name === "log") {
		if (typeof startLogPolling === "function") startLogPolling();
		if (typeof updateLogInspectorAnalytics === "function") updateLogInspectorAnalytics();
		setTimeout(() => {
			const c = document.getElementById("logLines");
			if (c) c.scrollTop = c.scrollHeight;
		}, 50);
	} else if (name === "config") {
		if (typeof stopLogPolling === "function") stopLogPolling();
		if (typeof loadConfigTab === "function") loadConfigTab();
	} else if (name === "skills") {
		if (typeof stopLogPolling === "function") stopLogPolling();
		if (typeof loadSkills === "function") loadSkills();
		if (typeof renderQueueInspector === "function") renderQueueInspector();
	} else if (name === "cases") {
		if (typeof stopLogPolling === "function") stopLogPolling();
		if (typeof renderLegend === "function") renderLegend();
		if (typeof renderCases === "function") renderCases();
	} else {
		if (typeof stopLogPolling === "function") stopLogPolling();
	}
}

function resetAppInspectorContent() {
	const icon = document.getElementById("inspectorHeaderIcon");
	const title = document.getElementById("inspectorHeaderTitle");
	const subtitle = document.getElementById("inspectorHeaderSubtitle");
	const body = document.getElementById("appInspectorBody");

	if (icon) icon.textContent = "📄";
	if (title) title.textContent = "Document Inspector";
	if (subtitle) subtitle.textContent = "No document selected";
	if (body) {
		body.innerHTML = `
			<div class="inspector-empty-state">
				<div class="empty-icon">✨</div>
				<h4>Welcome to Inspector</h4>
				<p>Click on a document in <strong>Inbox</strong> or <strong>Cases</strong> to inspect preview and extracted AI fields.</p>
			</div>
		`;
	}
}

function toggleAppInspector() {
	const activeTab = document.querySelector(".nav-item.active")?.dataset?.tab || 
	                  document.querySelector(".tab-content.active")?.id?.replace("tab-", "");
	if (activeTab === "log" && typeof updateLogInspectorAnalytics === "function") {
		updateLogInspectorAnalytics();
	} else if (activeTab === "config" && typeof updateConfigInspector === "function") {
		updateConfigInspector();
	} else if (activeTab === "skills" && typeof loadSkills === "function" && state.skills && state.skills.length > 0) {
		const selected = (typeof selectedSkillId !== "undefined" && selectedSkillId) ? selectedSkillId : state.skills[0].id;
		if (typeof selectSkill === "function") selectSkill(selected);
	}
}

function toggleSidebar() {
	const sidebar = document.getElementById("appSidebar");
	if (!sidebar) return;
	sidebar.classList.toggle("collapsed");
	const icon = document.getElementById("sidebarToggleIcon");
	if (icon) {
		icon.textContent = sidebar.classList.contains("collapsed") ? "▶️" : "◀️";
	}
}

function closeAppInspector() {
	resetAppInspectorContent();
}

function openAppInspector(data) {
	const inspector = document.getElementById("appInspector");
	const body = document.getElementById("appInspectorBody");
	const icon = document.getElementById("inspectorHeaderIcon");
	const title = document.getElementById("inspectorHeaderTitle");
	const subtitle = document.getElementById("inspectorHeaderSubtitle");

	if (!inspector || !body) return;

	inspector.classList.remove("hidden-inspector");

	if (icon) icon.textContent = data.icon || "📄";
	if (title) title.textContent = data.title || "Document Inspector";
	if (subtitle) subtitle.textContent = data.subtitle || "";

	if (data.html) {
		body.innerHTML = data.html;
	} else {
		let fieldsHtml = "";
		if (data.fields) {
			fieldsHtml = Object.entries(data.fields)
				.map(
					([k, v]) => `
				<div class="inspector-field-row">
					<span class="inspector-field-label">${escapeHtml(k)}</span>
					<span class="inspector-field-value">${escapeHtml(String(v))}</span>
				</div>`,
				)
				.join("");
		}

		body.innerHTML = `
			${
				data.previewUrl
					? `
			<div class="inspector-card">
				<div class="inspector-preview-wrap">
					${
						data.previewUrl.endsWith(".pdf")
							? `<iframe src="${data.previewUrl}"></iframe>`
							: `<img src="${data.previewUrl}" alt="Preview" />`
					}
				</div>
			</div>`
					: ""
			}
			<div class="inspector-card">
				<h4 class="inspector-extracted-title">📋 Extracted AI Data</h4>
				<div class="inspector-field-group">
					${fieldsHtml || '<p class="inspector-extracted-empty">No extraction data available.</p>'}
				</div>
			</div>
			${
				data.actionsHtml
					? `
			<div class="inspector-actions">
				${data.actionsHtml}
			</div>`
					: ""
			}
		`;
	}
}

async function deleteFile(type, folder, filename) {
	try {
		if (type === "cases") {
			await api(
				"/api/cases/" +
					encodeURIComponent(folder) +
					"/" +
					encodeURIComponent(filename),
				{ method: "DELETE" },
			);
			if (state.expandedFolder === folder) {
				const d = await api("/api/cases/" + encodeURIComponent(folder));
				state.expandedFiles = d.files || [];
			}
			fetchCases();
			toast("🗑️ In den Papierkorb verschoben: " + filename);
		} else {
			const safePath = filename.split("/").map(encodeURIComponent).join("/");
			await api("/api/inbox/" + safePath, {
				method: "DELETE",
			});
			fetchInbox();
			toast("🗑️ In den Papierkorb verschoben: " + filename);
		}
		const curInspect = document.getElementById("inspectorHeaderSubtitle")?.textContent;
		if (curInspect && curInspect.includes(filename)) {
			closeAppInspector();
		}
	} catch (e) {
		toast("Fehler beim Löschen: " + e.message, "error");
	}
}

function openConfirm(message, filename, onConfirm) {
	state.pendingConfirm = {
		type: "custom",
		callback: onConfirm,
		filename: filename || "",
	};
	const msgEl = document.getElementById("confirmMessage");
	if (msgEl) msgEl.textContent = message || "Möchten Sie diese Aktion wirklich ausführen?";
	const fnEl = document.getElementById("confirmFilename");
	if (fnEl) fnEl.textContent = filename || "";
	const modal = document.getElementById("confirmModal");
	if (modal) modal.classList.add("show");
}

function closeConfirm() {
	const modal = document.getElementById("confirmModal");
	if (modal) modal.classList.remove("show");
	state.pendingConfirm = null;
}

async function confirmAction() {
	if (!state.pendingConfirm) return;
	const pc = state.pendingConfirm;
	closeConfirm();
	try {
		if (typeof pc.callback === "function") {
			await pc.callback();
			return;
		}
	} catch (e) {
		toast("Fehler: " + e.message, "error");
	}
}



/* ═══════════════════════════════════════════════════════════
   LOADING SKELETONS
   ═══════════════════════════════════════════════════════════ */
function showSkeletons() {
	const tbody = document.getElementById("casesBody");
	let html = "";
	for (let i = 0; i < 6; i++) {
		html += `<tr><td><div class="skeleton skeleton-cell-name">&nbsp;</div></td>
      <td><div class="skeleton skeleton-cell-date">&nbsp;</div></td>
      <td><div class="skeleton skeleton-cell-cat">&nbsp;</div></td>
      <td><div class="skeleton skeleton-cell-pill"></div></td>
      <td><div class="skeleton skeleton-cell-sm">&nbsp;</div></td></tr>`;
	}
	tbody.innerHTML = html;

	const list = document.getElementById("inboxList");
	let ehtml = "";
	for (let i = 0; i < 4; i++) {
		ehtml += `<div class="inbox-item"><div class="file-icon skeleton skeleton-icon-lg">&nbsp;</div>
      <div class="inbox-info"><div class="skeleton skeleton-title-md">&nbsp;</div>
      <div class="skeleton skeleton-sub-sm">&nbsp;</div></div></div>`;
	}
	list.innerHTML = ehtml;
}

/* ═══════════════════════════════════════════════════════════
   CLOSE MODALS ON ESCAPE / BACKDROP
   ═══════════════════════════════════════════════════════════ */
document.addEventListener("keydown", (e) => {
	if (e.key === "Escape") {
		closeConfirm();
		if (typeof closeLegal === "function") closeLegal();
		if (typeof closeFolderEdit === "function") closeFolderEdit();
		if (typeof closeSystemPathPicker === "function") closeSystemPathPicker();
		if (typeof closeCreateSkillModal === "function") closeCreateSkillModal();
		if (typeof closeAiSynthesisModal === "function") closeAiSynthesisModal();
		if (typeof closeAppInspector === "function") closeAppInspector();
	}
});
document.getElementById("confirmModal")?.addEventListener("click", (e) => {
	if (e.target === e.currentTarget) closeConfirm();
});

document.getElementById("legalModal")?.addEventListener("click", (e) => {
	if (e.target === e.currentTarget) closeLegal();
});

/* ═══════════════════════════════════════════════════════════
   LEGAL MODAL
   ═══════════════════════════════════════════════════════════ */
async function openLegal(docName) {
	const titles = {
		license: "License & Terms (GNU AGPL v3.0)",
		privacy: "Data Privacy Policy (PRIVACY_POLICY.md)",
		thirdparty: "Third-Party Open-Source Licenses",
		checklist: "Compliance Checklist (COMPLIANCE_CHECKLIST.md)",
	};
	document.getElementById("legalModalTitle").textContent =
		titles[docName] || "Legal & Compliance";
	document.getElementById("legalModalBody").innerHTML =
		'<div class="legal-loading">Loading document...</div>';
	document.getElementById("legalModal").classList.add("show");

	try {
		const res = await api(`/api/legal/${docName}`);
		document.getElementById("legalModalBody").innerHTML =
			res.content || "<p>No content available.</p>";
	} catch (e) {
		document.getElementById("legalModalBody").innerHTML =
			`<p style="color:var(--danger)">Error loading document: ${escapeHtml(e.message)}</p>`;
	}
}

function closeLegal() {
	document.getElementById("legalModal").classList.remove("show");
}

/* ═══════════════════════════════════════════════════════════
   CATEGORY LEGEND
   ═══════════════════════════════════════════════════════════ */
function renderLegend() {
	const container = document.getElementById("legendContainer");
	if (!container) return;
	const docTypes =
		typeof getImportSkillsDocTypes === "function"
			? getImportSkillsDocTypes()
			: (state.config && state.config.document_types) || {};

	const entries = Object.entries(docTypes).filter(([name]) => name.toUpperCase() !== "UNKNOWN");
	if (entries.length === 0) {
		container.classList.add("hidden");
		return;
	}

	container.classList.remove("hidden");
	let html = '<span class="legend-title">Legend:</span>';

	for (const [name, info] of entries) {
		if (info && info.routing && info.routing.archive === false) continue;
		const emoji = (info && info.emoji) || "📄";
		html += `<span class="legend-item"><span class="doc-emoji">${emoji}</span>${escapeHtml(name)}</span>`;
	}
	container.innerHTML = html;
}

/* ═══════════════════════════════════════════════════════════
               JOB POLLING & CONFIG EDITOR TAB
               ═══════════════════════════════════════════════════════════ */
let _hadActiveJobs = false;
async function pollJobs() {
	try {
		const res = await fetch("/api/jobs");
		if (!res.ok) return;
		const data = await res.json();
		const jobs = data.jobs || [];
		const activeJobs = jobs.filter(
			(j) => j.status === "RUNNING" || j.status === "PENDING",
		);
		const ticker = document.getElementById("jobTicker");
		if (ticker) {
			if (activeJobs.length > 0) {
				_hadActiveJobs = true;
				ticker.style.display = "flex";
				const running =
					activeJobs.find((j) => j.status === "RUNNING") || activeJobs[0];
				const tickerText = document.getElementById("jobTickerText");
				if (tickerText) tickerText.textContent = `🔄 Processing job: ${running.name} ...`;
				const tickerCount = document.getElementById("jobTickerCount");
				if (tickerCount) tickerCount.textContent = activeJobs.length === 1 ? "1 active" : `${activeJobs.length} active`;
			} else {
				ticker.style.display = "none";
				if (_hadActiveJobs) {
					_hadActiveJobs = false;
					fetchCases();
					fetchInbox();
				}
			}
		}
	} catch (e) {
		console.debug("[pollJobs] Network issue or polling aborted:", e);
	}
}


let _isSyncing = false;
async function syncAppState() {
	if (_isSyncing) return;
	_isSyncing = true;
	try {
		await Promise.allSettled([
			fetchStatus(),
			fetchCases(),
			fetchInbox(),
			ensureSkillsLoaded(),
			pollJobs(),
		]);
	} catch (e) {
		console.error("Error during syncAppState:", e);
	} finally {
		_isSyncing = false;
	}
}

// Register global event listeners on AppEvents bus
AppEvents.on("inbox:refresh", () => {
	if (typeof fetchInbox === "function") fetchInbox();
});
AppEvents.on("cases:refresh", () => {
	if (typeof fetchCases === "function") fetchCases();
});
AppEvents.on("skills:refresh", () => {
	if (typeof ensureSkillsLoaded === "function") ensureSkillsLoaded(true);
	if (typeof fetchSkills === "function") fetchSkills();
});
AppEvents.on("config:refresh", () => {
	if (typeof fetchConfig === "function") fetchConfig();
});

showSkeletons();
Promise.allSettled([
	fetchConfig(),
	ensureSkillsLoaded(),
	fetchStatus(),
	fetchCases(),
	fetchInbox(),
	pollJobs(),
]);

// Background Tab Lifecycle & Polling Controller
let statusPollTimer = null;
let jobsPollTimer = null;
let syncPollTimer = null;

function startUiPolling() {
	if (!statusPollTimer) statusPollTimer = setInterval(fetchStatus, 4000);
	if (!jobsPollTimer) jobsPollTimer = setInterval(pollJobs, 2000);
	if (!syncPollTimer) syncPollTimer = setInterval(syncAppState, 6000);
}

function stopUiPolling() {
	if (statusPollTimer) {
		clearInterval(statusPollTimer);
		statusPollTimer = null;
	}
	if (jobsPollTimer) {
		clearInterval(jobsPollTimer);
		jobsPollTimer = null;
	}
	if (syncPollTimer) {
		clearInterval(syncPollTimer);
		syncPollTimer = null;
	}
}

startUiPolling();

// Dedicated heartbeat keepalive every 12s - runs continuously even when tab is backgrounded
setInterval(() => {
	fetch("/api/heartbeat", { method: "POST" }).catch(() => {});
}, 12000);

// On tab visibility change (pause UI polling when hidden, resume & sync immediately on return)
document.addEventListener("visibilitychange", () => {
	if (document.visibilityState === "visible") {
		fetch("/api/heartbeat", { method: "POST" }).catch(() => {});
		startUiPolling();
		syncAppState();
		const activeTab = document.querySelector(".nav-item.active")?.dataset?.tab;
		if (activeTab === "log" && typeof fetchLogDelta === "function") {
			fetchLogDelta();
			if (typeof updateLogInspectorAnalytics === "function") updateLogInspectorAnalytics();
		} else if (activeTab === "skills" && typeof renderQueueInspector === "function") {
			renderQueueInspector();
		}
	} else {
		stopUiPolling();
	}
});

// On window focus force immediate sync
window.addEventListener("focus", () => {
	fetch("/api/heartbeat", { method: "POST" }).catch(() => {});
	syncAppState();
});

/* ── Shared UI/UX & Data Formatting Utilities ── */

/**
 * Validates real Gregorian calendar dates (including leap years).
 */
function isValidCalendarDate(year, month, day) {
	if (year < 1900 || year > 2100 || month < 1 || month > 12 || day < 1 || day > 31) return false;
	const d = new Date(Date.UTC(year, month - 1, day));
	return d.getUTCFullYear() === year && d.getUTCMonth() === month - 1 && d.getUTCDate() === day;
}

/**
 * Normalizes varied date strings (DD.MM.YYYY, DD/MM/YY, ISO timestamps) to strict ISO YYYY-MM-DD.
 * Returns null if input cannot be safely parsed into a valid Gregorian date.
 */
function normalizeDateForInput(val) {
	if (val === null || val === undefined) return null;
	let s = String(val).trim();
	if (!s) return null;

	// Strip time portions if present (e.g. "2026-08-24T12:00:00Z" or "2026-08-24 10:00")
	s = s.split(/[T\s]/)[0].trim();

	let y, m, d;

	// Pattern 1: ISO formats YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD
	let match = s.match(/^(\d{4})[./-](\d{1,2})[./-](\d{1,2})$/);
	if (match) {
		y = parseInt(match[1], 10);
		m = parseInt(match[2], 10);
		d = parseInt(match[3], 10);
	} else {
		// Pattern 2: European formats DD.MM.YYYY, DD-MM-YYYY, DD/MM/YYYY or 2-digit years
		match = s.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})$/);
		if (match) {
			d = parseInt(match[1], 10);
			m = parseInt(match[2], 10);
			let rawYear = parseInt(match[3], 10);
			y = rawYear < 100 ? (rawYear <= 50 ? 2000 + rawYear : 1900 + rawYear) : rawYear;
		}
	}

	if (y && m && d && isValidCalendarDate(y, m, d)) {
		return `${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
	}

	return null;
}

/**
 * Sanitizes strings into safe DOM ID tokens (only [a-zA-Z0-9_-]).
 */
function sanitizeDomId(prefix, ...parts) {
	const cleanParts = parts.map((p) => encodeURIComponent(String(p || "")).replace(/[^a-zA-Z0-9_-]/g, "_"));
	return `${prefix}_${cleanParts.join("_")}`;
}
