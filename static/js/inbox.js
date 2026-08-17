if (!state.selectedInbox) state.selectedInbox = new Set();

async function fetchInbox() {
	try {
		state.inbox = await api("/api/inbox");
		const pruefCount = state.inbox.filter((f) => f.is_pruefen).length;
		const bIn = document.getElementById("badgeInbox");
		if (bIn) bIn.textContent = state.inbox.length;
		const bp = document.getElementById("badgePruefen");
		if (bp) {
			if (pruefCount > 0) {
				bp.textContent = pruefCount + " ⚠";
				bp.style.display = "";
			} else {
				bp.style.display = "none";
			}
		}
		const pathEl = document.getElementById("inboxWatchDirPath");
		if (pathEl && state.config && state.config.watch_dir) {
			pathEl.textContent = state.config.watch_dir;
		}
		renderInbox();
	} catch (e) {
		console.error("Error fetching Inbox:", e);
	}
}

function filterInbox() {
	renderInbox();
}

function togglePruefenFilter() {
	state.pruefenOnly = !state.pruefenOnly;
	const btn = document.getElementById("filterPruefen");
	btn.classList.toggle("btn-warning", state.pruefenOnly);
	renderInbox();
}

function updateBatchBar() {
	const bar = document.getElementById("batchActionBar");
	const countLabel = document.getElementById("batchSelectCount");
	const count = state.selectedInbox.size;
	if (bar && countLabel) {
		if (count > 0) {
			bar.style.display = "flex";
			countLabel.textContent = `${count} selected`;
		} else {
			bar.style.display = "none";
		}
	}
}

function toggleSelectAllInbox(checked) {
	if (checked) {
		state.inbox.forEach((f) => state.selectedInbox.add(f.path));
	} else {
		state.selectedInbox.clear();
	}
	renderInbox();
	updateBatchBar();
}

let inboxThumbObserver = null;
let inboxSentinelObserver = null;
let lastInboxRenderHash = "";
let isInboxDelegated = false;
let currentInboxData = [];
let inboxRenderedCount = 48;

const INBOX_PLACEHOLDER_IMG = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 11'%3E%3Crect width='16' height='11' fill='%23060911'/%3E%3C/svg%3E";

function setupInboxThumbObserver(container) {
	if (!container) return;
	const scrollRoot = document.getElementById("tab-inbox") || null;
	if ("IntersectionObserver" in window) {
		if (!inboxThumbObserver) {
			inboxThumbObserver = new IntersectionObserver(
				(entries) => {
					entries.forEach((entry) => {
						if (entry.isIntersecting) {
							const img = entry.target;
							const src = img.dataset.src;
							if (src) {
								img.src = src;
								img.removeAttribute("data-src");
							}
							inboxThumbObserver.unobserve(img);
						}
					});
				},
				{ root: scrollRoot, rootMargin: "250px 0px", threshold: 0.01 }
			);
		}
		container
			.querySelectorAll("img[data-src]")
			.forEach((img) => inboxThumbObserver.observe(img));
	} else {
		container.querySelectorAll("img[data-src]").forEach((img) => {
			img.src = img.dataset.src;
			img.removeAttribute("data-src");
		});
	}
}

function initInboxDelegation(list) {
	if (isInboxDelegated || !list) return;
	isInboxDelegated = true;

	list.addEventListener("click", (e) => {
		const autoAssignBtn = e.target.closest("button[data-autoassign]");
		if (autoAssignBtn) {
			e.stopPropagation();
			autoAssignFile(decodeURIComponent(autoAssignBtn.dataset.autoassign));
			return;
		}

		const retryBtn = e.target.closest("button[data-retryfile]");
		if (retryBtn) {
			e.stopPropagation();
			retryFile(decodeURIComponent(retryBtn.dataset.retryfile));
			return;
		}

		const delBtn = e.target.closest("button[data-delinbox]");
		if (delBtn) {
			e.stopPropagation();
			deleteFile("inbox", "", decodeURIComponent(delBtn.dataset.delinbox));
			return;
		}

		const inspectEl = e.target.closest("[data-inspect]");
		if (inspectEl) {
			e.stopPropagation();
			openSplitInspector(decodeURIComponent(inspectEl.dataset.inspect));
			return;
		}
	});

	list.addEventListener("change", (e) => {
		const chk = e.target.closest("input[data-selectfile]");
		if (chk) {
			e.stopPropagation();
			const path = decodeURIComponent(chk.dataset.selectfile);
			if (chk.checked) {
				state.selectedInbox.add(path);
			} else {
				state.selectedInbox.delete(path);
			}
			updateBatchBar();
		}
	});
}

function renderFileCardHtml(f) {
	const hasPreview = !!f.preview_url;
	const isChecked = state.selectedInbox.has(f.path);

	// Check if filename has all information for auto assign
	const parts = splitByDelimiter(f.name.split(".")[0]);
	const hasAllInfo = parts.length === 4;

	return `<div class="file-card ${f.is_pruefen ? "pruefen" : ""}">
      <div class="inbox-card-checkbox-wrap" onclick="event.stopPropagation();">
        <input type="checkbox" class="file-select-checkbox inbox-select-checkbox" data-selectfile="${encodeURIComponent(f.path)}" ${isChecked ? "checked" : ""}>
      </div>
      <div class="preview clickable-preview" data-inspect="${encodeURIComponent(f.path)}">
        ${
					hasPreview
						? `<img data-src="${f.preview_url}" src="${INBOX_PLACEHOLDER_IMG}" alt="Preview" class="lazy-thumb" onerror="this.parentElement.innerHTML='<span class=no-preview>Preview unavailable</span>'">`
						: '<span class="no-preview">No preview</span>'
				}
      </div>
      <div class="file-info clickable-file-info" data-inspect="${encodeURIComponent(f.path)}">
        <div class="file-name">${escapeHtml(f.name)}</div>
        <div class="file-meta">${formatSize(f.size)} · ${escapeHtml(f.modified || "")}</div>
        ${f.is_pruefen && f.grund ? `<div class="file-meta file-meta-warning">⚠ ${escapeHtml(f.grund)}</div>` : ""}
        ${renderValidationBadges(f.extracted)}
      </div>
      <span class="inbox-tag ${f.is_pruefen ? "review" : "processing"} file-inbox-tag">${f.is_pruefen ? "⚠ Review" : "Processing"}</span>
      <div class="file-actions">
        ${
					f.is_pruefen
						? `
          <button type="button" class="btn btn-sm btn-accent" data-retryfile="${encodeURIComponent(f.path)}" title="Reprocess">🔄</button>
          ${
						hasAllInfo
							? `<button type="button" class="btn btn-sm btn-success" data-autoassign="${encodeURIComponent(f.path)}">✅ Assign</button>`
							: ""
					}
          <button type="button" class="btn btn-sm btn-danger" data-delinbox="${encodeURIComponent(f.path)}" title="Delete">🗑️</button>
        `
						: `
          <button type="button" class="btn btn-sm btn-danger" data-delinbox="${encodeURIComponent(f.path)}" title="Delete">🗑️</button>
        `
				}
      </div>
    </div>`;
}

function appendMoreInboxCards() {
	const list = document.getElementById("inboxList");
	if (!list) return;
	const nextSlice = currentInboxData.slice(inboxRenderedCount, inboxRenderedCount + 36);
	if (nextSlice.length === 0) return;

	inboxRenderedCount += nextSlice.length;

	const oldSentinel = document.getElementById("inboxSentinel");
	if (oldSentinel) oldSentinel.remove();

	const tempDiv = document.createElement("div");
	tempDiv.innerHTML = nextSlice.map(renderFileCardHtml).join("");
	while (tempDiv.firstChild) {
		list.appendChild(tempDiv.firstChild);
	}

	if (inboxRenderedCount < currentInboxData.length) {
		const sentinel = document.createElement("div");
		sentinel.id = "inboxSentinel";
		sentinel.style.cssText = "grid-column: 1 / -1; height: 36px; display: flex; align-items: center; justify-content: center; color: var(--text-muted); font-size: 0.72rem;";
		sentinel.textContent = `Showing ${inboxRenderedCount} of ${currentInboxData.length} files...`;
		list.appendChild(sentinel);
		if (inboxSentinelObserver) inboxSentinelObserver.observe(sentinel);
	}

	setupInboxThumbObserver(list);
}

function setupSentinelObserver() {
	if (inboxSentinelObserver) {
		inboxSentinelObserver.disconnect();
	}
	const sentinel = document.getElementById("inboxSentinel");
	if (!sentinel) return;

	const scrollRoot = document.getElementById("tab-inbox") || null;
	inboxSentinelObserver = new IntersectionObserver(
		(entries) => {
			entries.forEach((entry) => {
				if (entry.isIntersecting) {
					appendMoreInboxCards();
				}
			});
		},
		{ root: scrollRoot, rootMargin: "400px 0px", threshold: 0.01 }
	);
	inboxSentinelObserver.observe(sentinel);
}

function renderInbox() {
	const searchEl = document.getElementById("searchInbox");
	const q = searchEl ? searchEl.value.toLowerCase() : "";
	let data = state.inbox || [];
	if (state.pruefenOnly) data = data.filter((f) => f.is_pruefen);
	if (q) data = data.filter((f) => (f.name || "").toLowerCase().includes(q));

	currentInboxData = data;
	const list = document.getElementById("inboxList");
	if (!list) return;

	const emptyEl = document.getElementById("emptyInbox");
	if (emptyEl) {
		emptyEl.style.display = data.length ? "none" : "block";
	}

	initInboxDelegation(list);

	// Compute hash of data to avoid destroying DOM and resetting image loads if nothing changed
	const currentHash = `${q}|${state.pruefenOnly}|${data.length}|` +
		data.map((f) => `${f.path}:${f.is_pruefen}:${f.grund || ""}:${f.size}`).join("|");

	if (currentHash === lastInboxRenderHash) {
		// Sync checkboxes only without DOM rebuild
		list.querySelectorAll("input[data-selectfile]").forEach((chk) => {
			const path = decodeURIComponent(chk.dataset.selectfile);
			chk.checked = state.selectedInbox.has(path);
		});
		updateBatchBar();
		return;
	}

	lastInboxRenderHash = currentHash;
	list.className = "file-grid";
	inboxRenderedCount = Math.min(48, data.length);

	const initialSlice = data.slice(0, inboxRenderedCount);
	let html = initialSlice.map(renderFileCardHtml).join("");
	if (inboxRenderedCount < data.length) {
		html += `<div id="inboxSentinel" class="inbox-sentinel">Showing ${inboxRenderedCount} of ${data.length} files...</div>`;
	}
	list.innerHTML = html;

	updateBatchBar();
	setupInboxThumbObserver(list);
	setupSentinelObserver();
}

async function autoAssignFile(filename) {
	try {
		const safePath = filename.split("/").map(encodeURIComponent).join("/");
		await api("/api/inbox/" + safePath + "/auto_assign", {
			method: "POST",
		});
		toast("File assigned successfully");
		fetchInbox();
		fetchCases();
	} catch (e) {
		toast("Assignment error: " + e.message, "error");
	}
}

async function retryFile(filename) {
	try {
		const safePath = filename.split("/").map(encodeURIComponent).join("/");
		await api("/api/inbox/" + safePath + "/retry", {
			method: "POST",
		});
		toast("Reprocessing file: " + filename);
		fetchInbox();
	} catch (e) {
		toast("Error: " + e.message, "error");
	}
}

/* ═══════════════════════════════════════════════════════════
   DELETE WITH CONFIRM
   ═══════════════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════════════════════
   MANUAL ASSIGNMENT & FILE EDITING
   ═══════════════════════════════════════════════════════════ */
function openAssign(type, folder, filename) {
	state.assignType = type; // 'inbox' or 'cases'
	state.assignFolder = folder;
	state.assignFile = filename;

	document.getElementById("assignFilename").textContent = filename
		.split("/")
		.pop();

	let personStr = "",
		datum = "",
		produkt = "",
		dokArt = "";

	if (type === "cases") {
		const folderData = state.cases.find((v) => v.folder === folder);
		datum = folderData ? folderData.datum : "";
		produkt = folderData ? folderData.produkt : "";
		personStr = folderData ? folderData.person : "";
		dokArt = splitByDelimiter(filename)[0] || "";
	} else {
		const baseName = filename.split("/").pop();
		const parts = splitByDelimiter(baseName.split(".")[0]);
		if (parts.length >= 4) {
			dokArt = parts[0] || "";
			produkt = parts[1] || "";
			datum = parts[2] || "";
			const delim = (state.config && state.config.folder_delimiter) || "--";
			personStr = parts.slice(3).join(delim) || "";
		} else if (parts.length > 0) {
			// Best effort parsing for incomplete names
			dokArt = parts[0] || "";
			if (parts.length > 1) produkt = parts[1];
			if (parts.length > 2) datum = parts[2];

			// Try to find a date if it's not in the 3rd position
			const dateRegex = /\d{4}-\d{2}-\d{2}/;
			const dateMatch = baseName.match(dateRegex);
			if (dateMatch) datum = dateMatch[0];
		}
	}

	document.getElementById("assignPerson").value = personStr;
	document.getElementById("assignDatum").value = (datum && datum !== "----" && /^\d{4}-\d{2}-\d{2}$/.test(datum)) ? datum : "";
	document.getElementById("assignProdukt").value = produkt;

	// Populate datalist with existing unique folders
	const personList = document.getElementById("personList");
	personList.innerHTML = "";
	state.cases.forEach((a) => {
		if (a.parts && a.parts.length) {
			const opt = document.createElement("option");
			opt.value = a.parts.join(" | ");
			personList.appendChild(opt);
		}
	});

	// Auto-fill form fields when a folder option is selected from datalist
	document.getElementById("assignPerson").oninput = (e) => {
		const val = e.target.value;
		if (val.includes(" | ")) {
			const parts = val.split(" | ");
			if (parts.length >= 3) {
				document.getElementById("assignPerson").value = parts[0].trim();
				document.getElementById("assignDatum").value = parts[1].trim();
				document.getElementById("assignProdukt").value = parts[2].trim();
			}
		}
	};

	initDokArtContainer("assignDokArtContainer", dokArt);

	document.getElementById("assignModal").classList.add("show");
}

function closeAssign() {
	document.getElementById("assignModal").classList.remove("show");
	state.assignFile = null;
}

/* ═══════════════════════════════════════════════════════════
   BATCH INBOX OPERATIONS
   ═══════════════════════════════════════════════════════════ */

async function batchAutoAssignInbox() {
	const files = Array.from(state.selectedInbox);
	if (files.length === 0) return;

	let successCount = 0;
	for (const filename of files) {
		try {
			const safePath = filename.split("/").map(encodeURIComponent).join("/");
			await api("/api/inbox/" + safePath + "/auto_assign", {
				method: "POST",
			});
			successCount++;
		} catch (e) {
			console.error("Batch assign error for " + filename, e);
		}
	}
	toast(`${successCount} of ${files.length} file(s) assigned successfully.`);
	state.selectedInbox.clear();
	fetchInbox();
	fetchCases();
}

async function batchDeleteInbox() {
	const files = Array.from(state.selectedInbox);
	if (files.length === 0) return;
	if (!confirm(`Do you really want to delete ${files.length} file(s)?`))
		return;

	let deleteCount = 0;
	for (const filename of files) {
		try {
			const safePath = filename.split("/").map(encodeURIComponent).join("/");
			await api("/api/inbox/" + safePath, { method: "DELETE" });
			deleteCount++;
		} catch (e) {
			console.error("Batch delete error for " + filename, e);
		}
	}
	toast(`${deleteCount} file(s) deleted.`);
	state.selectedInbox.clear();
	fetchInbox();
}

async function batchReprocessInbox() {
	const files = Array.from(state.selectedInbox);
	if (files.length === 0) return;

	let successCount = 0;
	for (const filename of files) {
		try {
			const safePath = filename.split("/").map(encodeURIComponent).join("/");
			await api("/api/inbox/" + safePath + "/retry", {
				method: "POST",
			});
			successCount++;
		} catch (e) {
			console.error("Batch retry error for " + filename, e);
		}
	}
	toast(`${successCount} of ${files.length} file(s) queued for reprocessing.`);
	state.selectedInbox.clear();
	fetchInbox();
}

// Side drawer & Split Inspector functions are modularized in inbox_drawer.js
