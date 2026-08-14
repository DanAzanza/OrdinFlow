/* ═══════════════════════════════════════════════════════════
   CASES
   ═══════════════════════════════════════════════════════════ */
function docEmoji(type) {
	if (!type || typeof type !== "string") return "📄";
	if (!state.config || !state.config.document_types) return "📄";
	const docTypes = state.config.document_types;
	const matchKey = Object.keys(docTypes).find(
		(k) =>
			k.toLowerCase() === type.toLowerCase() ||
			type.toLowerCase().includes(k.toLowerCase()) ||
			k.toLowerCase().includes(type.toLowerCase()),
	);
	if (matchKey && docTypes[matchKey].emoji) {
		return docTypes[matchKey].emoji;
	}
	return "📄";
}
function docLabel(type) {
	if (!type || typeof type !== "string") return type || "";
	if (!state.config || !state.config.document_types) return type;
	const docTypes = state.config.document_types;
	const matchKey = Object.keys(docTypes).find(
		(k) =>
			k.toLowerCase() === type.toLowerCase() ||
			type.toLowerCase().includes(k.toLowerCase()) ||
			k.toLowerCase().includes(type.toLowerCase()),
	);
	return matchKey || type;
}

function sortCases(col) {
	if (state.sortCol === col) {
		state.sortAsc = !state.sortAsc;
	} else {
		state.sortCol = col;
		state.sortAsc = true;
	}
	renderCases();
}

function filterCases() {
	renderCases();
}

async function fetchCases() {
	try {
		state.cases = await api("/api/cases");
		const badge = document.getElementById("badgeCases");
		if (badge) badge.textContent = state.cases.length;

		if (state.expandedFolder) {
			const folderExists = state.cases.some((v) => v.folder === state.expandedFolder);
			if (folderExists) {
				try {
					const d = await api("/api/cases/" + encodeURIComponent(state.expandedFolder));
					state.expandedFiles = d.files || [];
				} catch (_) {
					state.expandedFiles = [];
				}
			} else {
				state.expandedFolder = null;
				state.expandedFiles = [];
			}
		}

		renderCases();
		bindDetailEvents();
	} catch (e) {
		console.error("Error fetching Cases:", e);
	}
}

function splitByDelimiter(str, customDelim = null) {
	if (!str) return [];
	const delim =
		customDelim || (state.config && state.config.folder_delimiter) || "--";
	return str.split(delim);
}

function parseDateToTimestamp(str) {
	if (!str) return null;
	const s = String(str).trim();
	const m1 = s.match(/^(\d{1,2})[\s.\-/]+(\d{1,2})[\s.\-/]+(\d{4})$/);
	if (m1) {
		const day = parseInt(m1[1], 10);
		const month = parseInt(m1[2], 10) - 1;
		const year = parseInt(m1[3], 10);
		return new Date(year, month, day).getTime();
	}
	const m2 = s.match(/^(\d{4})[\s.\-/]+(\d{1,2})[\s.\-/]+(\d{1,2})$/);
	if (m2) {
		const year = parseInt(m2[1], 10);
		const month = parseInt(m2[2], 10) - 1;
		const day = parseInt(m2[3], 10);
		return new Date(year, month, day).getTime();
	}
	return null;
}

function renderCases() {
	const struct = (state.config && state.config.folder_structure) || [];

	// Determine sort column index
	const sortIdx = typeof state.sortCol === "number" ? state.sortCol : 0;

	// Render dynamic table headers
	const headerRow = document.getElementById("casesHeaderRow");
	if (headerRow) {
		let headerHtml = "";
		struct.forEach((comp, idx) => {
			const label = cleanHeaderLabel(comp);
			const isSorted = sortIdx === idx;
			const arrow = isSorted ? (state.sortAsc ? "▲" : "▼") : "▲";
			headerHtml += `<th onclick="sortCases(${idx})" class="${isSorted ? "sorted" : ""} cases-table-th">
                            <span>${escapeHtml(label)}</span> <span class="sort-arrow">${isSorted ? arrow : ""}</span>
                        </th>`;
		});
		headerHtml += `<th>Documents</th>`;
		headerRow.innerHTML = headerHtml;
	}

	const q = document.getElementById("searchCases").value.toLowerCase();
	const data = state.cases.filter(
		(a) =>
			!q ||
			(a.folder || "").toLowerCase().includes(q) ||
			(a.parts || []).some((p) => String(p).toLowerCase().includes(q)),
	);

	// Sort
	data.sort((a, b) => {
		let va = a.parts && a.parts[sortIdx] ? a.parts[sortIdx] : "";
		let vb = b.parts && b.parts[sortIdx] ? b.parts[sortIdx] : "";

		const tsA = parseDateToTimestamp(va);
		const tsB = parseDateToTimestamp(vb);
		if (tsA !== null && tsB !== null) {
			return state.sortAsc ? tsA - tsB : tsB - tsA;
		}
		if (typeof va === "number" && typeof vb === "number")
			return state.sortAsc ? va - vb : vb - va;
		va = String(va).toLowerCase();
		vb = String(vb).toLowerCase();
		return state.sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
	});

	const tbody = document.getElementById("casesBody");
	document.getElementById("emptyCases").style.display = data.length
		? "none"
		: "block";
	const casesWrap = document.querySelector("#tab-cases .table-wrap");
	if (casesWrap) casesWrap.style.display = data.length ? "" : "none";

	let html = "";
	data.forEach((a, i) => {
		const isExpanded = state.expandedFolder === a.folder;
		const docKeys =
			state.config && state.config.document_types
				? Object.keys(state.config.document_types)
				: [];
		const sortedTypes = (a.doc_types || []).slice().sort((x, y) => {
			const ix = docKeys.findIndex(
				(k) => k.toLowerCase() === (x || "").toLowerCase(),
			);
			const iy = docKeys.findIndex(
				(k) => k.toLowerCase() === (y || "").toLowerCase(),
			);
			return (ix === -1 ? 99 : ix) - (iy === -1 ? 99 : iy);
		});
		const dots = sortedTypes
			.map(
				(d) =>
					`<span class="doc-emoji" title="${escapeHtml(docLabel(d))}">${docEmoji(d)}</span>`,
			)
			.join("");

		// Render cells dynamically
		let cellsHtml = "";
		struct.forEach((comp, idx) => {
			let val = a.parts && a.parts[idx] ? a.parts[idx] : "–";
			// If it matches a date pattern, format it
			if (/^\d{4}-\d{2}-\d{2}$/.test(val) || /^\d{2}-\d{2}-\d{4}$/.test(val)) {
				val = formatDateString(val);
			}

			if (idx === 1 && struct.length > 2) {
				// Render second column as badge (typically Produkt/Kategorie)
				cellsHtml += `<td class="cases-table-td"><span class="badge cases-badge-col">${escapeHtml(val)}</span></td>`;
			} else {
				cellsHtml += `<td class="cases-table-td"><div class="cases-text-col">${escapeHtml(val)}</div></td>`;
			}
		});

		html += `<tr class="${isExpanded ? "expanded" : ""}" data-folder="${escapeHtml(a.folder)}">
                        ${cellsHtml}
                        <td>
                            <div class="cases-actions-wrapper">
                                <div class="doc-dots">${dots}</div>
                                <div class="cases-actions-btn-group">
                                    ${
                                        a.is_approved
                                            ? `<span class="badge cases-badge-approved" title="This folder has already been approved">✅ Approved</span>`
                                            : `<button type="button" class="btn btn-sm cases-btn-approve" onclick="event.stopPropagation(); triggerApproveAndRunSkill('${escapeHtml(a.folder)}')" title="Approve & Run Skill">🚀 Approve</button>`
                                    }
                                    <button type="button" class="btn btn-sm btn-accent" onclick="event.stopPropagation(); openFolderEdit('${escapeHtml(a.folder)}')" title="Edit">✏️</button>
                                    <button type="button" class="btn btn-sm btn-danger" onclick="event.stopPropagation(); deleteFolder('${escapeHtml(a.folder)}')" title="Delete Case Folder">🗑️</button>
                                </div>


                            </div>
                        </td>
                    </tr>`;

		if (isExpanded) {
			html += `<tr class="detail-row">
                            <td colspan="${struct.length + 1}">
                                <div class="detail-content" id="detailContent">
                                    ${renderDetailFiles()}
                                </div>
                            </td>
                        </tr>`;
		}
	});
	tbody.innerHTML = html;

	// Event delegation for secure folder names click
	tbody.querySelectorAll("tr[data-folder]").forEach((tr) => {
		tr.addEventListener("click", () => toggleDetail(tr.dataset.folder));
	});
}

function renderDetailFiles() {
	if (!state.expandedFiles.length) {
		return '<div class="cases-loading-state"><div class="cases-loading-spinner">⏳</div> Loading files...</div>';
	}

	const html =
		'<div class="file-grid">' +
		state.expandedFiles
			.map((f) => {
				return `<div class="file-card">
      <div class="preview clickable" data-inspectvorgang="${encodeURIComponent(f.name)}" style="cursor:pointer">
        ${
					f.has_preview
						? `<img src="${f.preview_url}" alt="Preview" loading="lazy" onerror="this.parentElement.innerHTML='<span class=no-preview>Preview unavailable</span>'">`
						: '<span class="no-preview">No preview</span>'
				}
      </div>
      <div class="file-info" data-inspectvorgang="${encodeURIComponent(f.name)}" style="cursor:pointer">
        <div class="file-name clickable">${escapeHtml(f.name)}</div>
        <div class="file-meta">${formatSize(f.size)} · ${escapeHtml(f.modified || "")}</div>
      </div>
      <div class="file-actions" style="gap: 4px;">
        <button class="btn btn-sm btn-danger" data-delfile="${encodeURIComponent(f.name)}" title="Delete">
          🗑️
        </button>
      </div>
    </div>`;
			})
			.join("") +
		"</div>";
	return html;
}

function bindDetailEvents() {
	const detail = document.getElementById("detailContent");
	if (!detail) return;

	// Open file in Split-Screen Inspector on click
	detail.querySelectorAll("[data-inspectvorgang]").forEach((el) => {
		el.addEventListener("click", (e) => {
			e.stopPropagation();
			const filename = decodeURIComponent(el.dataset.inspectvorgang);
			openSplitInspector("cases", state.expandedFolder, filename);
		});
	});

	// Delete buttons
	detail.querySelectorAll("button[data-delfile]").forEach((btn) => {
		btn.addEventListener("click", (e) => {
			e.stopPropagation();
			const filename = decodeURIComponent(btn.dataset.delfile);
			deleteFile("cases", state.expandedFolder, filename);
		});
	});
}

async function toggleDetail(folder) {
	if (state.expandedFolder === folder) {
		state.expandedFolder = null;
		state.expandedFiles = [];
		renderCases();
		return;
	}
	state.expandedFolder = folder;
	state.expandedFiles = [];
	renderCases(); // show loading
	try {
		const d = await api("/api/cases/" + encodeURIComponent(folder));
		state.expandedFiles = d.files || [];
	} catch (_) {
		state.expandedFiles = [];
	}
	renderCases();
	bindDetailEvents();
}

/* ═══════════════════════════════════════════════════════════
   FOLDER EDITING
   ═══════════════════════════════════════════════════════════ */
function openFolderEdit(folder) {
	openSplitInspector("folder_edit", folder, null);
}

/* ═══════════════════════════════════════════════════════════
   INIT & POLLING
   ═══════════════════════════════════════════════════════════ */
function renderLegend() {
	const container = document.getElementById("legendContainer");
	if (!container) return;

	if (!state.config || !state.config.document_types) {
		container.style.display = "none";
		return;
	}

	container.style.display = "flex";
	let html = '<span class="legend-title">Legend:</span>';

	const docTypes = state.config.document_types;
	for (const [name, info] of Object.entries(docTypes)) {
		if (name.toUpperCase() === "UNKNOWN") continue;
		if (info.routing && info.routing.archive === false) continue;
		const emoji = info.emoji || "📄";
		html += `<span class="legend-item"><span class="doc-emoji">${emoji}</span>${name}</span>`;
	}
	container.innerHTML = html;
}
