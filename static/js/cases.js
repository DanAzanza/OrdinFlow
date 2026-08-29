/* ═══════════════════════════════════════════════════════════
   CASES MANAGEMENT & EXPORT STATUS TRACKING
   ═══════════════════════════════════════════════════════════ */

function docLabel(type) {
	if (!type || typeof type !== "string") return type || "";
	return type;
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
		if (typeof renderLegend === "function") renderLegend();
	} catch (e) {
		console.error("Error fetching Cases:", e);
	}
}

async function triggerApproveFolder(folderName, currentApproved) {
	try {
		const targetApproved = !currentApproved;
		const res = await api("/api/cases/approve", {
			method: "POST",
			body: JSON.stringify({ folder: folderName, approved: targetApproved }),
		});

		if (res.status === "ok") {
			toast(
				targetApproved
					? "✅ Case approved! Ready for export skills."
					: "Case approval revoked.",
				"success"
			);
			await fetchCases();
		}
	} catch (e) {
		console.error("Error approving folder:", e);
		toast("Error updating approval: " + e.message, "error");
	}
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

	const q = (document.getElementById("searchCases")?.value || "").toLowerCase();
	const data = (state.cases || []).filter(
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
	if (!tbody) return;

	const emptyEl = document.getElementById("emptyCases");
	if (emptyEl) emptyEl.style.display = data.length ? "none" : "block";
	const casesWrap = document.querySelector("#tab-cases .table-wrap");
	if (casesWrap) casesWrap.style.display = data.length ? "" : "none";

	const docTypesMap = typeof getImportSkillsDocTypes === "function"
		? getImportSkillsDocTypes()
		: (state.config && state.config.document_types) || {};
	const docKeys = Object.keys(docTypesMap);

	let html = "";
	data.forEach((a, i) => {
		const isExpanded = state.expandedFolder === a.folder;
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
					`<span class="doc-emoji" title="${escapeHtml(docLabel(d))}">${getDocTypeEmoji(d)}</span>`,
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
				cellsHtml += `<td class="cases-table-td"><span class="badge cases-badge-col">${escapeHtml(val)}</span></td>`;
			} else {
				cellsHtml += `<td class="cases-table-td"><div class="cases-text-col">${escapeHtml(val)}</div></td>`;
			}
		});

		// Dynamic Status Badge
		let statusBadgeHtml = "";
		let rowStatusClass = "case-row-pending";

		if (a.export_status === "completed") {
			rowStatusClass = "case-row-completed";
			statusBadgeHtml = `<span class="badge cases-badge-completed" title="All files have been processed by all export skills">🟢 Completed</span>`;
		} else if (a.export_status === "partially_exported") {
			rowStatusClass = "case-row-partial";
			const taskInfo = a.total_applicable_tasks ? ` (${a.completed_applicable_tasks}/${a.total_applicable_tasks})` : "";
			statusBadgeHtml = `<span class="badge cases-badge-partial" title="${a.completed_applicable_tasks} of ${a.total_applicable_tasks} skills executed">🟡 In Progress${taskInfo}</span>`;
		} else if (a.is_approved) {
			rowStatusClass = "case-row-approved";
			statusBadgeHtml = `<button type="button" class="btn btn-sm cases-badge-approved clickable" data-folder="${escapeHtml(a.folder)}" onclick="event.stopPropagation(); triggerApproveFolder(this.dataset.folder, true)" title="Click to revoke approval">🔵 Approved</button>`;
		} else {
			rowStatusClass = "case-row-pending";
			statusBadgeHtml = `<button type="button" class="btn btn-sm cases-btn-approve" data-folder="${escapeHtml(a.folder)}" onclick="event.stopPropagation(); triggerApproveFolder(this.dataset.folder, false)" title="Approve case for export skills">🚀 Approve</button>`;
		}

		html += `<tr class="${isExpanded ? "expanded" : ""} ${rowStatusClass}" data-folder="${escapeHtml(a.folder)}">
                        ${cellsHtml}
                        <td>
                            <div class="cases-actions-wrapper">
                                <div class="doc-dots">${dots}</div>
                                <div class="cases-actions-btn-group">
                                    ${statusBadgeHtml}
                                    <button type="button" class="btn btn-sm btn-accent" data-folder="${escapeHtml(a.folder)}" onclick="event.stopPropagation(); openFolderEdit(this.dataset.folder)" title="Edit folder">✏️</button>
                                    <button type="button" class="btn btn-sm btn-danger" data-folder="${escapeHtml(a.folder)}" onclick="event.stopPropagation(); deleteFolder(this.dataset.folder)" title="Delete case folder">🗑️</button>
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
	initCasesDelegation();
}

let isCasesDelegated = false;
function initCasesDelegation() {
	if (isCasesDelegated) return;
	const tbody = document.getElementById("casesBody");
	if (!tbody) return;
	isCasesDelegated = true;

	tbody.addEventListener("click", (e) => {
		const delBtn = e.target.closest("button[data-delfile]");
		if (delBtn) {
			e.stopPropagation();
			const filename = decodeURIComponent(delBtn.dataset.delfile);
			deleteFile("cases", state.expandedFolder, filename);
			return;
		}

		const inspectEl = e.target.closest("[data-inspectvorgang]");
		if (inspectEl) {
			e.stopPropagation();
			const filename = decodeURIComponent(inspectEl.dataset.inspectvorgang);
			openSplitInspector("cases", state.expandedFolder, filename);
			return;
		}

		const tr = e.target.closest("tr[data-folder]");
		if (tr && !e.target.closest("button") && !e.target.closest(".detail-row")) {
			toggleDetail(tr.dataset.folder);
			return;
		}
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
				let skillBadgesHtml = "";
				if (f.executed_skills && f.executed_skills.length > 0) {
					skillBadgesHtml = f.executed_skills
						.map((s) => `<span class="badge file-skill-executed-badge" title="Executed by: ${escapeHtml(s)}">⚡ ${escapeHtml(s)} ✅</span>`)
						.join(" ");
				} else {
					skillBadgesHtml = `<span class="badge file-skill-pending-badge" title="No export skill executed on this file yet">⏳ Ready</span>`;
				}

				return `<div class="file-card ${f.executed_skills && f.executed_skills.length > 0 ? "file-card-exported" : ""}">
      <div class="preview clickable file-card-preview-clickable" data-inspectvorgang="${encodeURIComponent(f.name)}">
        ${
					f.has_preview
						? `<img src="${escapeHtml(f.preview_url)}" alt="Preview" loading="lazy" onerror="this.parentElement.innerHTML='<span class=no-preview>Preview unavailable</span>'">`
						: '<span class="no-preview">No preview</span>'
				}
      </div>
      <div class="file-card-body file-card-body-flex">
        <div class="file-info file-info-flex" data-inspectvorgang="${encodeURIComponent(f.name)}">
          <div class="file-name clickable" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</div>
          <div class="file-meta">${formatSize(f.size)} · ${escapeHtml(f.modified || "")}</div>
          <div class="file-skill-badges file-skill-badges-flex">
              <span class="badge file-doctype-badge">${getDocTypeEmoji(f.doc_type)} ${escapeHtml(docLabel(f.doc_type || "Document"))}</span>
              ${skillBadgesHtml}
          </div>
        </div>
        <button type="button" class="btn-icon-subtle btn-icon-danger btn-delfile-compact" data-delfile="${encodeURIComponent(f.name)}" title="Delete file">
          🗑️
        </button>
      </div>
    </div>`;
			})
			.join("") +
		"</div>";
	return html;
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
	} catch (e) {
		console.error("Error loading case files:", e);
		state.expandedFiles = [];
	}
	renderCases();
}

async function deleteFolder(folder) {
	openConfirm(
		`Are you sure you want to delete case "${folder}" and all its documents?`,
		folder,
		async () => {
			try {
				await api("/api/cases/" + encodeURIComponent(folder), {
					method: "DELETE",
				});
				toast("Case deleted");
				if (state.expandedFolder === folder) {
					state.expandedFolder = null;
					state.expandedFiles = [];
				}
				AppEvents.emit("cases:refresh");
			} catch (e) {
				toast("Error deleting case: " + e.message, "error");
			}
		},
	);
}

function openFolderEdit(folderName) {
	const c = (state.cases || []).find((x) => x.folder === folderName);
	if (!c) return;

	document.getElementById("editFolderOldName").value = folderName;
	const struct = (state.config && state.config.folder_structure) || [];
	const formContainer = document.getElementById("editFolderFields");
	formContainer.innerHTML = "";

	struct.forEach((comp, idx) => {
		const label = cleanHeaderLabel(comp);
		const val = c.parts && c.parts[idx] ? c.parts[idx] : "";
		const fieldId = `edit_folder_part_${idx}`;

		const group = document.createElement("div");
		group.className = "form-group";
		group.innerHTML = `
			<label for="${fieldId}" class="doc-editor-label">${escapeHtml(label)}</label>
			<input type="text" id="${fieldId}" class="doc-editor-input" name="part_${idx}" data-idx="${idx}" value="${escapeHtml(val)}" aria-label="${escapeHtml(label)}" />
		`;
		formContainer.appendChild(group);
	});

	document.getElementById("editFolderModal").classList.add("open");
}

function closeFolderEdit() {
	document.getElementById("editFolderModal").classList.remove("open");
}

async function submitFolderEdit() {
	const oldName = document.getElementById("editFolderOldName").value;
	const struct = (state.config && state.config.folder_structure) || [];
	const inputs = document.querySelectorAll("#editFolderFields input");

	const payload = {};
	inputs.forEach((input) => {
		const idx = parseInt(input.dataset.idx, 10);
		const comp = struct[idx];
		if (comp) {
			payload[comp] = input.value.trim();
		}
	});

	try {
		const res = await api("/api/cases/" + encodeURIComponent(oldName), {
			method: "PUT",
			body: JSON.stringify(payload),
		});

		if (res.status === "ok") {
			toast("Case folder updated!");
			closeFolderEdit();
			if (state.expandedFolder === oldName) {
				state.expandedFolder = res.folder;
			}
			AppEvents.emit("cases:refresh");
		}
	} catch (e) {
		toast("Error updating case folder: " + e.message, "error");
	}
}



