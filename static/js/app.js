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
		icon.textContent = sidebar.classList.contains("collapsed") ? "▶" : "◀";
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
			closeInspector();
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

function deleteFolder(folder) {
	state.pendingConfirm = {
		type: "folder",
		folder: folder,
		filename: folder,
	};
	const msgEl = document.getElementById("confirmMessage");
	if (msgEl) {
		msgEl.textContent =
			"Möchten Sie diesen Vorgangs-Ordner und alle enthaltenen Dokumente wirklich in den Papierkorb verschieben?";
	}
	const fnEl = document.getElementById("confirmFilename");
	if (fnEl) fnEl.textContent = folder;
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
		if (pc.type === "folder") {
			const folder = pc.folder;
			await api("/api/cases/" + encodeURIComponent(folder), {
				method: "DELETE",
			});
			if (state.expandedFolder === folder) {
				state.expandedFolder = null;
				state.expandedFiles = [];
			}
			fetchCases();
			toast("🗑️ Ordner in den Papierkorb verschoben: " + folder);
			closeInspector();
		}
	} catch (e) {
		toast("Fehler beim Löschen: " + e.message, "error");
	}
}

/* ═══════════════════════════════════════════════════════════
   DYNAMIC Dokument
   ═══════════════════════════════════════════════════════════ */
function getDokArtOptions() {
	const docTypes = typeof getImportSkillsDocTypes === "function"
		? getImportSkillsDocTypes()
		: (state.config && state.config.document_types) || {};
	const keys = Object.keys(docTypes);
	return keys.filter((k) => k.toUpperCase() !== "UNKNOWN").sort();
}

function addDokArtRow(containerId, value = "") {
	const container = document.getElementById(containerId);
	const row = document.createElement("div");
	row.style.display = "flex";
	row.style.gap = "8px";
	row.style.alignItems = "center";

	const sel = document.createElement("select");
	sel.style.flex = "1";

	// Default options
	const options = getDokArtOptions();
	options.forEach((opt) => {
		const o = document.createElement("option");
		o.value = opt;
		o.text = opt;
		sel.appendChild(o);
	});

	// If value is unknown, add it to options
	if (
		value &&
		!options.map((v) => v.toLowerCase()).includes(value.toLowerCase())
	) {
		const o = document.createElement("option");
		o.value = value;
		o.text = value;
		sel.insertBefore(o, sel.firstChild);
	}

	if (value) {
		let found = false;
		for (let i = 0; i < sel.options.length; i++) {
			if (sel.options[i].value.toLowerCase() === value.toLowerCase()) {
				sel.selectedIndex = i;
				found = true;
				break;
			}
		}
	} else {
		sel.selectedIndex = 0;
	}

	const rmBtn = document.createElement("button");
	rmBtn.type = "button";
	rmBtn.className = "btn btn-sm btn-danger";
	rmBtn.style.padding = "2px 8px";
	rmBtn.textContent = "-";
	rmBtn.title = "Remove document";
	rmBtn.onclick = () => {
		if (container.children.length > 1) {
			container.removeChild(row);
		} else {
			toast("At least one document type must be present", "error");
		}
	};

	row.appendChild(sel);
	row.appendChild(rmBtn);
	container.appendChild(row);
}

function getDokArtValues(containerId) {
	const container = document.getElementById(containerId);
	const selects = container.querySelectorAll("select");
	const vals = [];
	selects.forEach((s) => {
		if (s.value) vals.push(s.value);
	});
	return vals.join("+");
}

function initDokArtContainer(containerId, dokArtStr) {
	const container = document.getElementById(containerId);
	container.innerHTML = "";
	const parts = dokArtStr ? dokArtStr.split("+") : [""];
	parts.forEach((p) => addDokArtRow(containerId, p.trim()));
}

async function submitAssign() {
	const personStr = document.getElementById("assignPerson").value.trim();
	const datum = document.getElementById("assignDatum").value;
	const produkt = document.getElementById("assignProdukt").value.trim();
	const dok_art = getDokArtValues("assignDokArtContainer");

	if (!personStr || !datum || !produkt) {
		toast("Please fill in all required fields", "error");
		return;
	}

	let nachname = personStr,
		vorname = "";
	if (personStr.includes(",")) {
		const parts = personStr.split(",");
		nachname = parts[0].trim();
		vorname = parts.slice(1).join(",").trim();
	}

	try {
		if (state.assignType === "cases") {
			await api(
				"/api/cases/" +
					encodeURIComponent(state.assignFolder) +
					"/" +
					encodeURIComponent(state.assignFile) +
					"/edit",
				{
					method: "POST",
					body: JSON.stringify({
						nachname,
						vorname,
						datum,
						produkt,
						dokument: dok_art,
					}),
				},
			);
			state.expandedFolder = null; // Close detail to be safe
		} else {
			const safePath = state.assignFile
				.split("/")
				.map(encodeURIComponent)
				.join("/");
			await api("/api/inbox/" + safePath + "/assign", {
				method: "POST",
				body: JSON.stringify({
					nachname,
					vorname,
					datum,
					produkt,
					dokument: dok_art,
				}),
			});
		}
		toast("File moved successfully");
		closeAssign();
		fetchInbox();
		fetchCases();
	} catch (e) {
		toast("Processing error: " + e.message, "error");
	}
}

function openFileEdit(folder, filename) {
	state.editFileFolder = folder;
	state.editFile = filename;

	document.getElementById("fileEditFilename").textContent = filename;

	const folderData = state.cases.find((v) => v.folder === folder);

	const fileParts = splitByDelimiter(
		filename.replace(".pdf", "").replace(".jpg", "").replace(/_\d+$/, ""),
	);
	const dokArt = fileParts[0] || "";
	let produkt = fileParts[1] || "";
	let datum = fileParts[2] || "";

	if (!datum) datum = folderData ? folderData.datum : "";
	if (!produkt) produkt = folderData ? folderData.produkt : "";

	document.getElementById("fileEditDatum").value = datum;
	document.getElementById("fileEditProdukt").value = produkt;

	initDokArtContainer("fileEditDokArtContainer", dokArt);

	document.getElementById("fileEditModal").classList.add("show");
}

function closeFileEdit() {
	document.getElementById("fileEditModal").classList.remove("show");
	state.editFile = null;
}

async function submitFileEdit() {
	const datum = document.getElementById("fileEditDatum").value;
	const produkt = document.getElementById("fileEditProdukt").value.trim();
	const dok_art = getDokArtValues("fileEditDokArtContainer");

	if (!datum || !produkt) {
		toast("Please fill in all required fields", "error");
		return;
	}

	// Extract person from original folder name
	const editFolderData = state.cases.find(
		(v) => v.folder === state.editFileFolder,
	);
	const personStr = editFolderData ? editFolderData.person : "";
	let nachname = personStr,
		vorname = "";
	if (personStr.includes(",")) {
		const parts = personStr.split(",");
		nachname = parts[0].trim();
		vorname = parts.slice(1).join(",").trim();
	}

	try {
		await api(
			"/api/cases/" +
				encodeURIComponent(state.editFileFolder) +
				"/" +
				encodeURIComponent(state.editFile) +
				"/edit",
			{
				method: "POST",
				body: JSON.stringify({
					nachname,
					vorname,
					datum,
					produkt,
					dokument: dok_art,
					move: false,
				}),
			},
		);
		toast("File updated successfully");
		closeFileEdit();
		if (state.expandedFolder === state.editFileFolder)
			state.expandedFolder = null;
		fetchCases();
	} catch (e) {
		toast("Processing error: " + e.message, "error");
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
		closeAssign();
		if (typeof closeLegal === "function") closeLegal();
		if (typeof closeFolderEdit === "function") closeFolderEdit();
		if (typeof closeFolderEditModal === "function") closeFolderEditModal();
		if (typeof closeFileEdit === "function") closeFileEdit();
		if (typeof closeFileEditModal === "function") closeFileEditModal();
		if (typeof closeSelectSkillModal === "function") closeSelectSkillModal();
		if (typeof closeSystemPathPicker === "function") closeSystemPathPicker();
		if (typeof closeSystemPathPickerModal === "function") closeSystemPathPickerModal();
		if (typeof closeCreateSkillModal === "function") closeCreateSkillModal();
		if (typeof closeAiSynthesisModal === "function") closeAiSynthesisModal();
		if (typeof closeAiSkillModal === "function") closeAiSkillModal();
		if (typeof closeAppInspector === "function") closeAppInspector();
	}
});
document.getElementById("confirmModal").addEventListener("click", (e) => {
	if (e.target === e.currentTarget) closeConfirm();
});
document.getElementById("assignModal").addEventListener("click", (e) => {
	if (e.target === e.currentTarget) closeAssign();
});

document.getElementById("legalModal").addEventListener("click", (e) => {
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
function renderCategoryLegend() {
	const container = document.getElementById("categoryLegend");
	const docTypes =
		typeof getImportSkillsDocTypes === "function"
			? getImportSkillsDocTypes()
			: (state.config && state.config.document_types) || {};

	const entries = Object.entries(docTypes).filter(([name]) => name.toUpperCase() !== "UNKNOWN");
	if (entries.length === 0) {
		container.style.display = "none";
		return;
	}

	container.style.display = "flex";
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
