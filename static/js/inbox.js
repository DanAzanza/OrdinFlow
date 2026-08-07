if (!state.selectedEingang) state.selectedEingang = new Set();

async function fetchEingang() {
	try {
		state.eingang = await api("/api/inbox");
		const pruefCount = state.eingang.filter((f) => f.is_pruefen).length;
		const bIn = document.getElementById("badgeInbox") || document.getElementById("badgeEingang");
		if (bIn) bIn.textContent = state.eingang.length;
		const bp = document.getElementById("badgePruefen");
		if (bp) {
			if (pruefCount > 0) {
				bp.textContent = pruefCount + " ⚠";
				bp.style.display = "";
			} else {
				bp.style.display = "none";
			}
		}
		const pathEl = document.getElementById("eingangWatchDirPath");
		if (pathEl && state.config && state.config.watch_dir) {
			pathEl.textContent = state.config.watch_dir;
		}
		renderEingang();
	} catch (e) {
		console.error("Error fetching Eingang:", e);
	}
}

function filterEingang() {
	renderEingang();
}

function togglePruefenFilter() {
	state.pruefenOnly = !state.pruefenOnly;
	const btn = document.getElementById("filterPruefen");
	btn.classList.toggle("btn-warning", state.pruefenOnly);
	renderEingang();
}

function updateBatchBar() {
	const bar = document.getElementById("batchActionBar");
	const countLabel = document.getElementById("batchSelectCount");
	const count = state.selectedEingang.size;
	if (bar && countLabel) {
		if (count > 0) {
			bar.style.display = "flex";
			countLabel.textContent = `${count} selected`;
		} else {
			bar.style.display = "none";
		}
	}
}

function toggleSelectAllEingang(checked) {
	if (checked) {
		state.eingang.forEach((f) => state.selectedEingang.add(f.path));
	} else {
		state.selectedEingang.clear();
	}
	renderEingang();
	updateBatchBar();
}

function renderEingang() {
	const q = document.getElementById("searchEingang").value.toLowerCase();
	let data = state.eingang;
	if (state.pruefenOnly) data = data.filter((f) => f.is_pruefen);
	if (q) data = data.filter((f) => (f.name || "").toLowerCase().includes(q));

	const list = document.getElementById("eingangList");
	document.getElementById("emptyEingang").style.display = data.length
		? "none"
		: "block";

	list.className = "file-grid";
	list.innerHTML = data
		.map((f) => {
			const hasPreview = !!f.preview_url;
			const fileUrl = f.file_url || "";
			const isChecked = state.selectedEingang.has(f.path);

			// Check if filename has all information for auto assign
			const parts = splitByDelimiter(f.name.split(".")[0]);
			const hasAllInfo = parts.length === 4;

			return `<div class="file-card ${f.is_pruefen ? "pruefen" : ""}" style="position:relative;">
      <div style="position: absolute; top: 8px; left: 8px; z-index: 10;" onclick="event.stopPropagation();">
        <input type="checkbox" class="file-select-checkbox" data-selectfile="${encodeURIComponent(f.path)}" ${isChecked ? "checked" : ""} style="width:18px;height:18px;cursor:pointer;">
      </div>
      <div class="preview" data-inspect="${encodeURIComponent(f.path)}" style="cursor:pointer">
        ${
					hasPreview
						? `<img src="${f.preview_url}" alt="Vorschau" loading="lazy" onerror="this.parentElement.innerHTML='<span class=no-preview>Vorschau nicht verfügbar</span>'">`
						: '<span class="no-preview">Keine Vorschau</span>'
				}
      </div>
      <div class="file-info" data-inspect="${encodeURIComponent(f.path)}" style="cursor:pointer">
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
          <button class="btn btn-sm btn-accent" data-retryfile="${encodeURIComponent(f.path)}" title="Reprocess">🔄</button>
          ${
						hasAllInfo
							? `<button class="btn btn-sm btn-success" data-autoassign="${encodeURIComponent(f.path)}">✅ Assign</button>`
							: `<button class="btn btn-sm btn-accent" data-inspect="${encodeURIComponent(f.path)}">🔍 Inspector</button>`
					}
          <button class="btn btn-sm btn-danger" data-deleingang="${encodeURIComponent(f.path)}">🗑️</button>
        `
						: `<button class="btn btn-sm btn-accent" data-inspect="${encodeURIComponent(f.path)}">🔍 Open Document</button>`
				}
      </div>
    </div>`;
		})
		.join("");

	updateBatchBar();

	// Bind event listeners via delegation
	list.querySelectorAll("[data-inspect]").forEach((el) => {
		el.addEventListener("click", (e) => {
			e.stopPropagation();
			openSplitInspector(decodeURIComponent(el.dataset.inspect));
		});
	});
	list.querySelectorAll("input[data-selectfile]").forEach((chk) => {
		chk.addEventListener("change", (e) => {
			e.stopPropagation();
			const path = decodeURIComponent(chk.dataset.selectfile);
			if (chk.checked) {
				state.selectedEingang.add(path);
			} else {
				state.selectedEingang.delete(path);
			}
			updateBatchBar();
		});
	});
	list.querySelectorAll("button[data-retryfile]").forEach((btn) => {
		btn.addEventListener("click", (e) => {
			e.stopPropagation();
			retryFile(decodeURIComponent(btn.dataset.retryfile));
		});
	});
	list.querySelectorAll("button[data-deleingang]").forEach((btn) => {
		btn.addEventListener("click", (e) => {
			e.stopPropagation();
			deleteFile("eingang", "", decodeURIComponent(btn.dataset.deleingang));
		});
	});
	list.querySelectorAll("button[data-autoassign]").forEach((btn) => {
		btn.addEventListener("click", (e) => {
			e.stopPropagation();
			autoAssignFile(decodeURIComponent(btn.dataset.autoassign));
		});
	});
}

async function autoAssignFile(filename) {
	try {
		const safePath = filename.split("/").map(encodeURIComponent).join("/");
		await api("/api/eingang/" + safePath + "/auto_assign", {
			method: "POST",
		});
		toast("File assigned successfully");
		fetchEingang();
		fetchVorgaenge();
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
		fetchEingang();
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
	state.assignType = type; // 'eingang' or 'vorgaenge'
	state.assignFolder = folder;
	state.assignFile = filename;

	document.getElementById("assignFilename").textContent = filename
		.split("/")
		.pop();

	let personStr = "",
		datum = "",
		produkt = "",
		dokArt = "";

	if (type === "vorgaenge") {
		const folderData = state.vorgaenge.find((v) => v.folder === folder);
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
	state.vorgaenge.forEach((a) => {
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
               SPLIT-SCREEN INSPECTOR & BATCH OPERATIONS
               ═══════════════════════════════════════════════════════════ */

async function batchAutoAssignEingang() {
	const files = Array.from(state.selectedEingang);
	if (files.length === 0) return;

	let successCount = 0;
	for (const filename of files) {
		try {
			const safePath = filename.split("/").map(encodeURIComponent).join("/");
			await api("/api/eingang/" + safePath + "/auto_assign", {
				method: "POST",
			});
			successCount++;
		} catch (e) {
			console.error("Batch assign error for " + filename, e);
		}
	}
	toast(`${successCount} of ${files.length} file(s) assigned successfully.`);
	state.selectedEingang.clear();
	fetchEingang();
	fetchVorgaenge();
}

async function batchDeleteEingang() {
	const files = Array.from(state.selectedEingang);
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
	state.selectedEingang.clear();
	fetchEingang();
}

function extractFieldsFromFilenameAndFolder(dokArt, filename, folderName = "") {
	const extracted = {};
	if (!filename) return extracted;

	const baseName = filename.split("/").pop().split(".")[0];
	const docTypes = getImportSkillsDocTypes();
	const docCfg = docTypes[dokArt] || (state.config && state.config.document_types ? state.config.document_types[dokArt] : null);

	const filenameTemplate = (docCfg && docCfg.routing && docCfg.routing.filename_template)
		? docCfg.routing.filename_template
		: "";

	if (filenameTemplate && filenameTemplate.includes("{")) {
		const paramNames = [];
		const templateParts = filenameTemplate.split(/\{(\w+)\}/g);

		let patternStr = "^";
		for (let i = 0; i < templateParts.length; i++) {
			if (i % 2 === 1) {
				paramNames.push(templateParts[i]);
				patternStr += "(.*?)";
			} else {
				patternStr += templateParts[i].replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
			}
		}
		patternStr += "(?:_[\\d]+)?$";

		try {
			const rx = new RegExp(patternStr, "i");
			const match = baseName.match(rx);
			if (match && match.length > 1) {
				paramNames.forEach((param, idx) => {
					const val = match[idx + 1];
					if (val && val !== "----") {
						extracted[param] = val;
					}
				});
			}
		} catch (e) {
			console.debug("Filename template regex match error:", e);
		}
	}

	const delimiter = baseName.includes("__") ? "__" : (baseName.includes("--") ? "--" : "_");
	const parts = baseName.split(delimiter).map(p => p.trim()).filter(Boolean);

	if (parts.length > 0 && !extracted.Dokument && parts[0] !== "----") {
		extracted.Dokument = parts[0];
	}

	if (folderName) {
		const folderStruct = (state.config && Array.isArray(state.config.folder_structure))
			? state.config.folder_structure
			: [];

		const fDelimiter = (state.config && state.config.folder_delimiter)
			? state.config.folder_delimiter
			: (folderName.includes("--") ? "--" : (folderName.includes("__") ? "__" : "-"));

		const fParts = folderName.split(fDelimiter).map(p => p.trim());

		folderStruct.forEach((comp, idx) => {
			if (idx >= fParts.length) return;
			const val = fParts[idx];

			let fieldKey = typeof comp === "string" ? comp.replace(/^\{|\}$/g, "").trim() : "";
			if (!fieldKey && typeof comp === "object" && comp.template) {
				fieldKey = comp.template.replace(/^\{|\}$/g, "").trim();
			}

			if (fieldKey && val && val !== "----" && val !== "MISSING" && val !== "FEHLT") {
				if (!extracted[fieldKey]) {
					extracted[fieldKey] = val;
				}
			}
		});
	}

	return extracted;
}

async function openSplitInspector(contextOrFilename, folder = null, filename = null) {
	await ensureSkillsLoaded();
	state.drawerDocSections = null;

	let context = "eingang";
	let targetFile = contextOrFilename;

	if (contextOrFilename === "folder_edit") {
		context = "folder_edit";
		targetFile = null;
	} else if (contextOrFilename === "vorgaenge" || contextOrFilename === "eingang") {
		context = contextOrFilename;
		targetFile = filename;
	} else {
		context = "eingang";
		targetFile = contextOrFilename;
	}

	state.inspectorContext = context;
	state.inspectorFolder = folder;
	state.inspectorFile = targetFile;

	if (context === "folder_edit") {
		const safeFolder = encodeURIComponent(folder);
		const folderData = (state.vorgaenge || []).find((v) => v.folder === folder);

		const delimiter = (state.config && state.config.folder_delimiter) || "--";
		const struct = (state.config && Array.isArray(state.config.folder_structure)) ? state.config.folder_structure : [];
		const parts = folder ? folder.split(delimiter) : [];

		let extractedData = {};
		struct.forEach((comp, i) => {
			const m = String(comp).match(/\{(\w+)\}/);
			if (m) {
				const fieldName = m[1];
				let val = (i < parts.length) ? parts[i].trim() : "";
				if (val === "----" || val.toUpperCase() === "FEHLT" || val.toUpperCase() === "MISSING") {
					val = "";
				}
				extractedData[fieldName] = val;
			}
		});

		const matchFields = (state.config && Array.isArray(state.config.match_folder_by)) ? state.config.match_folder_by : [];
		matchFields.forEach(f => {
			if (extractedData[f] === undefined) extractedData[f] = "";
		});

		let fileUrl = "";
		let previewUrl = "";
		try {
			const d = await api("/api/vorgaenge/" + safeFolder);
			if (d && d.files && d.files.length > 0) {
				const firstFile = d.files.find(f => f.has_preview) || d.files[0];
				const safeFirst = encodeURIComponent(firstFile.name);
				fileUrl = `/api/file/vorgaenge/${safeFolder}/${safeFirst}`;
				previewUrl = firstFile.preview_url || `/api/preview/Vorgaenge/${safeFolder}/${safeFirst}`;
				state.inspectorFile = firstFile.name;
			}
		} catch (e) {
			console.debug("Could not fetch folder files:", e);
		}

		state.currentInspectorExtracted = extractedData;

		openAppInspector({
			icon: "📂",
			title: "Edit Folder",
			subtitle: `Case: ${folder}`,
			previewUrl: previewUrl || fileUrl,
			html: `
				<div class="inspector-card">
					<div class="inspector-preview-wrap">
						${(previewUrl || fileUrl)
							? ((previewUrl || fileUrl).endsWith(".pdf") || (state.inspectorFile || "").toLowerCase().endsWith(".pdf")
								? `<iframe src="${fileUrl || previewUrl}#toolbar=0&navpanes=0&view=FitH"></iframe>`
								: `<img src="${previewUrl || fileUrl}" alt="Preview" />`)
							: `<div style="padding: 40px; text-align: center; color: var(--text-muted);">📁 Folder contains no preview files</div>`
						}
					</div>
				</div>
				<div class="inspector-card">
					<h4 style="font-size: 0.85rem; margin-bottom: 10px; color: var(--accent); display: flex; align-items: center; gap: 6px;">
						<span>✏️</span> Edit Case Folder
					</h4>
					<div id="drawerFormWrapper">
						${buildFolderInspectorForm(folder, extractedData)}
					</div>
				</div>
			`
		});
		return;
	}

	let fileObj = null;
	let fileUrl = "";
	let previewUrl = "";
	let extractedData = {};
	let hasMetaFile = false;

	if (context === "vorgaenge") {
		const safeFolder = encodeURIComponent(folder);
		const safeFile = encodeURIComponent(targetFile);
		fileUrl = `/api/file/vorgaenge/${safeFolder}/${safeFile}`;
		previewUrl = `/api/preview/Vorgaenge/${safeFolder}/${safeFile}`;
	} else {
		fileObj = (state.eingang || []).find(
			(f) => f.path === targetFile || f.name === targetFile,
		) || { name: targetFile, path: targetFile };
		fileUrl = fileObj.file_url || `/api/file/eingang/${encodeURIComponent(targetFile)}`;
		previewUrl = fileObj.preview_url || "";

		if (fileObj.extracted && Object.keys(fileObj.extracted).length > 0) {
			extractedData = Object.assign({}, fileObj.extracted);
			hasMetaFile = true;
		}
	}

	// 1. Try fetching .meta sidecar file if not already loaded from state
	if (!hasMetaFile) {
		try {
			const metaUrl = context === "vorgaenge"
				? `/api/file/meta/vorgaenge/${encodeURIComponent(folder)}/${encodeURIComponent(targetFile)}`
				: `/api/file/meta/eingang/${encodeURIComponent(targetFile)}`;
			const metaRes = await fetch(metaUrl);
			if (metaRes.ok) {
				const metaJson = await metaRes.json();
				if (metaJson && metaJson.extracted && Object.keys(metaJson.extracted).length > 0) {
					extractedData = Object.assign({}, metaJson.extracted);
					hasMetaFile = true;
				}
			}
		} catch (e) {
			// No .meta file available
		}
	}

	let dokArt = extractedData.Dokument || extractedData.Dokumentart || splitByDelimiter(targetFile)[0] || "";

	// 2. If NO .meta file exists, parse field values from filename & folder based on import skill definition
	if (!hasMetaFile) {
		const parsedFromFilename = extractFieldsFromFilenameAndFolder(dokArt, targetFile, folder);
		extractedData = Object.assign({}, parsedFromFilename, extractedData);
		if (!dokArt && parsedFromFilename.Dokument) {
			dokArt = parsedFromFilename.Dokument;
		}
	}

	state.currentInspectorExtracted = extractedData;

	if (typeof openAppInspector === "function") {
		openAppInspector({
			icon: fileObj?.is_pruefen ? "⚠" : "📄",
			title: fileObj?.name || targetFile,
			subtitle: context === "vorgaenge" ? `Case: ${folder}` : (fileObj?.is_pruefen ? "Verification required" : "Ready for processing"),
			previewUrl: previewUrl || fileUrl,
			html: `
				<div class="inspector-card">
					<div class="inspector-preview-wrap">
						${(previewUrl || fileUrl).endsWith(".pdf") || (targetFile || "").toLowerCase().endsWith(".pdf")
								? `<iframe src="${fileUrl || previewUrl}#toolbar=0&navpanes=0&view=FitH"></iframe>`
								: `<img src="${previewUrl || fileUrl}" alt="Preview" />`
						}
					</div>
				</div>
				<div class="inspector-card">
					<h4 style="font-size: 0.85rem; margin-bottom: 10px; color: var(--accent); display: flex; align-items: center; gap: 6px;">
						<span>✏️</span> Edit & Assign Document
					</h4>
					<div id="drawerFormWrapper">
						${buildGenericInspectorForm(dokArt, "", "", "", extractedData)}
					</div>
				</div>
			`
		});
	}
}

function addDrawerDocSection() {
	if (!state.drawerDocSections) state.drawerDocSections = [];
	const options = getDokArtOptions();
	const defaultType = options[0] || "Dokument";
	state.drawerDocSections.push({
		id: Date.now() + Math.random(),
		dokArt: defaultType,
		pages: "",
		extracted: {}
	});
	renderDrawerSections();
}

function removeDrawerDocSection(secId) {
	if (!state.drawerDocSections || state.drawerDocSections.length <= 1) return;
	state.drawerDocSections = state.drawerDocSections.filter(s => s.id !== secId);
	renderDrawerSections();
}

function onSectionDokArtChange(secId, newDokArt) {
	if (!state.drawerDocSections) return;
	const sec = state.drawerDocSections.find(s => s.id === secId);
	if (sec) {
		sec.dokArt = newDokArt;
		renderDrawerSections();
	}
}

function renderDrawerSections() {
	const wrapper = document.getElementById("drawerFormWrapper");
	if (wrapper && state.drawerDocSections) {
		wrapper.innerHTML = buildGenericInspectorForm(null, "", "", "", state.currentInspectorExtracted || {});
	}
}

function buildGenericInspectorForm(dokArt, personStr, datum, produkt, extractedData = {}) {
	if (!state.drawerDocSections || state.drawerDocSections.length === 0) {
		const initialType = dokArt || getDokArtOptions()[0] || "Dokument";
		state.drawerDocSections = [
			{ id: 1, dokArt: initialType, pages: "alle", extracted: extractedData }
		];
	}

	const dokArtOptions = getDokArtOptions();
	const isMulti = state.drawerDocSections.length > 1;

	let html = `<div id="drawerSectionsList" style="display: flex; flex-direction: column; gap: 14px;">`;

	state.drawerDocSections.forEach((sec, idx) => {
		const curDokArt = sec.dokArt;
		const docTypes = getImportSkillsDocTypes();
		const docCfg = docTypes[curDokArt] || (state.config && state.config.document_types ? state.config.document_types[curDokArt] : null);
		const extractionFieldsConfig = (docCfg && docCfg.extraction_fields) ? docCfg.extraction_fields : null;
		const isDependent = docCfg && (docCfg.dependent === true || (docCfg.routing && docCfg.routing.dependent === true));

		const ignoredMetaKeys = new Set([
			"raw", "status", "confidence", "_confidence", "_confidence",
			"pages", "page_results", "dokument", "dokumentart", "dok_arts",
			"vision_description", "is_pruefen", "file_url", "preview_url"
		]);

		const targetFieldKeys = new Set();

		if (extractionFieldsConfig && typeof extractionFieldsConfig === "object") {
			Object.keys(extractionFieldsConfig).forEach(k => {
				if (!ignoredMetaKeys.has(k.toLowerCase())) {
					targetFieldKeys.add(k);
				}
			});
		}

		if (isDependent) {
			const matchFolderBy = (state.config && Array.isArray(state.config.match_folder_by))
				? state.config.match_folder_by
				: ((docCfg && docCfg.routing && Array.isArray(docCfg.routing.match_folder_by))
					? docCfg.routing.match_folder_by
					: ["Nachname", "Vorname", "Titel"]);

			matchFolderBy.forEach(k => {
				if (!ignoredMetaKeys.has(k.toLowerCase())) {
					targetFieldKeys.add(k);
				}
			});
		}

		const fieldValues = {};
		const extData = sec.extracted && Object.keys(sec.extracted).length > 0 ? sec.extracted : extractedData;

		if (targetFieldKeys.size > 0) {
			for (const key of targetFieldKeys) {
				let val = extData[key];
				if (val === undefined || val === null) {
					const matchKey = Object.keys(extData).find(k => k.toLowerCase() === key.toLowerCase());
					if (matchKey) val = extData[matchKey];
				}
				fieldValues[key] = val !== undefined && val !== null ? val : "";
			}
		} else if (extData && typeof extData === "object") {
			for (const [k, v] of Object.entries(extData)) {
				const lowerK = k.toLowerCase();
				if (ignoredMetaKeys.has(lowerK) || lowerK.startsWith("_")) continue;
				fieldValues[k] = v !== undefined && v !== null ? v : "";
			}
		}

		html += `
			<div class="drawer-section-card" data-secid="${sec.id}" style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border); border-radius: 8px; padding: 12px;">
				<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
					<span style="font-size: 0.8rem; font-weight: 700; color: var(--accent);">
						📄 Section ${idx + 1} ${isMulti ? `(${escapeHtml(curDokArt)})` : ""}
					</span>
					${isMulti ? `<button type="button" class="btn btn-sm btn-danger" onclick="removeDrawerDocSection(${sec.id})" style="padding: 2px 8px; font-size: 0.72rem;">🗑️ Remove section</button>` : ""}
				</div>

				<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px;">
					<div class="form-group">
						<label style="font-size: 0.74rem; color: var(--text-dim); margin-bottom: 4px; display: block; font-weight: 600;">Document Type *</label>
						<select class="doc-editor-input sec-dok-art" onchange="onSectionDokArtChange(${sec.id}, this.value)" style="width:100%; padding: 6px 8px; border-radius: 6px; background: #0a0d15; border: 1px solid var(--border); color: var(--text); font-size: 0.82rem;">
							${dokArtOptions.length > 0
								? dokArtOptions.map(opt => `<option value="${escapeHtml(opt)}" ${opt === curDokArt ? "selected" : ""}>${escapeHtml(opt)}</option>`).join("")
								: `<option value="">Empty</option>`
							}
						</select>
					</div>

					<div class="form-group">
						<label style="font-size: 0.74rem; color: var(--text-dim); margin-bottom: 4px; display: block; font-weight: 600;">Pages (e.g. 1 or 2-3) *</label>
						<input type="text" class="doc-editor-input sec-pages" value="${escapeHtml(sec.pages || "all")}" placeholder="all, 1, 2-3" style="width:100%; padding: 6px 8px; border-radius: 6px; background: #0a0d15; border: 1px solid var(--border); color: var(--text); font-size: 0.82rem;" />
					</div>
				</div>

				<div class="sec-fields-container">`;

		const keys = Object.keys(fieldValues);
		if (keys.length === 0) {
			html += `<div style="padding: 10px; text-align: center; color: var(--text-dim); font-size: 0.78rem; background: rgba(0,0,0,0.15); border-radius: 6px; border: 1px dashed var(--border);">No extraction fields for this type</div>`;
		} else {
			for (const key of keys) {
				const val = fieldValues[key] !== null && fieldValues[key] !== undefined ? String(fieldValues[key]) : "";
				const isDate = key.toLowerCase().includes("datum");
				const isBool = typeof fieldValues[key] === "boolean" || key.toLowerCase() === "signed";

				html += `
					<div class="form-group drawer-field-group" style="margin-bottom: 8px;">
						<label style="font-size: 0.74rem; color: var(--text-dim); margin-bottom: 3px; display: block;">
							<span>${escapeHtml(key)} *</span>
						</label>
						${isDate ? `<input type="date" class="doc-editor-input drawer-field" data-field="${escapeHtml(key)}" value="${escapeHtml(val)}" style="width:100%; padding: 5px 8px; border-radius: 6px; background: #0a0d15; border: 1px solid var(--border); color: var(--text); font-size: 0.8rem;" />`
								: isBool
								? `<select class="doc-editor-input drawer-field" data-field="${escapeHtml(key)}" style="width:100%; padding: 5px 8px; border-radius: 6px; background: #0a0d15; border: 1px solid var(--border); color: var(--text); font-size: 0.8rem;">
										<option value="true" ${val === "true" || val === "Ja" || fieldValues[key] === true ? "selected" : ""}>Yes / Signed</option>
										<option value="false" ${val === "false" || val === "Nein" || fieldValues[key] === false ? "selected" : ""}>No / Not signed</option>
								   </select>`
								: `<input type="text" class="doc-editor-input drawer-field" data-field="${escapeHtml(key)}" value="${escapeHtml(val)}" placeholder="${escapeHtml(key)}" style="width:100%; padding: 5px 8px; border-radius: 6px; background: #0a0d15; border: 1px solid var(--border); color: var(--text); font-size: 0.8rem;" />`
						}
					</div>`;
			}
		}

		html += `</div></div>`;
	});

	html += `</div>

		<div style="margin-top: 12px; margin-bottom: 14px;">
			<button type="button" class="btn btn-sm" onclick="addDrawerDocSection()" style="width:100%; font-size: 0.78rem; background: rgba(99, 102, 241, 0.12); border: 1px dashed rgba(99, 102, 241, 0.4); color: #a5b4fc; padding: 7px;">
				➕ Add another document type / page range
			</button>
		</div>

		<div style="display: flex; gap: 8px; margin-top: 14px;">
			<button class="btn btn-primary btn-sm" onclick="submitDrawerInspector()" style="flex:1;">✅ Approve & Move</button>
			<button class="btn btn-danger btn-sm" onclick="inspectorDeleteCurrent()">🗑️ Delete document</button>
		</div>`;

	return html;
}

function buildFolderInspectorForm(folder, extractedData = {}) {
	const struct = (state.config && Array.isArray(state.config.folder_structure)) ? state.config.folder_structure : [];
	const matchFields = (state.config && Array.isArray(state.config.match_folder_by)) ? state.config.match_folder_by : [];

	const fieldSet = new Set();
	struct.forEach(comp => {
		const m = String(comp).match(/\{(\w+)\}/);
		if (m) fieldSet.add(m[1]);
	});
	matchFields.forEach(f => fieldSet.add(f));

	let html = `<div class="drawer-section-card" style="padding: 12px; background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 8px;">`;
	html += `<div style="font-weight: 600; font-size: 0.85rem; margin-bottom: 10px; color: var(--text);">Metadata & Folder Attributes</div>`;

	fieldSet.forEach(fieldKey => {
		const label = cleanHeaderLabel ? cleanHeaderLabel(fieldKey) : fieldKey;
		const val = extractedData[fieldKey] !== undefined ? extractedData[fieldKey] : "";
		const inputType = (fieldKey.toLowerCase().includes("datum")) ? "date" : "text";

		html += `
			<div class="form-group" style="margin-bottom: 8px;">
				<label style="font-size: 0.75rem; font-weight: 600; color: var(--text-muted); display: block; margin-bottom: 2px;">
					${escapeHtml(label)}
				</label>
				<input type="${inputType}" class="drawer-field input-sm" data-field="${escapeHtml(fieldKey)}" value="${escapeHtml(val)}" placeholder="Enter ${escapeHtml(label)}..." style="width: 100%; font-size: 0.82rem; padding: 4px 8px;" />
			</div>
		`;
	});

	html += `
		<div style="display: flex; gap: 8px; margin-top: 14px;">
			<button class="btn btn-primary btn-sm" onclick="submitDrawerInspector()" style="flex:1;">✅ Save</button>
			<button class="btn btn-danger btn-sm" onclick="inspectorDeleteCurrent()">🗑️ Delete folder</button>
		</div>
	`;

	html += `</div>`;
	return html;
}

function onDrawerDokArtChange(newDokArt) {
	if (state.drawerDocSections && state.drawerDocSections.length > 0) {
		state.drawerDocSections[0].dokArt = newDokArt;
	}
	renderDrawerSections();
}

async function submitDrawerInspector() {
	const context = state.inspectorContext || "eingang";
	const filename = state.inspectorFile;
	const folder = state.inspectorFolder;

	if (context === "folder_edit") {
		if (!folder) return;
		const card = document.querySelector(".drawer-section-card");
		if (!card) return;

		const payload = {};
		card.querySelectorAll(".drawer-field").forEach((el) => {
			const fieldKey = el.dataset.field;
			if (fieldKey) payload[fieldKey] = el.value.trim();
		});

		try {
			const res = await api("/api/vorgaenge/" + encodeURIComponent(folder), {
				method: "PUT",
				body: JSON.stringify(payload)
			});

			toast(res.message || "Folder updated successfully!");
			closeAppInspector();
			if (state.expandedFolder === folder) state.expandedFolder = res.folder || folder;
			fetchVorgaenge();
		} catch (e) {
			toast("Error saving folder: " + e.message, "error");
		}
		return;
	}

	if (!filename) return;

	const sectionCards = document.querySelectorAll(".drawer-section-card");
	const documentsPayload = [];

	sectionCards.forEach((card) => {
		const dokArt = card.querySelector(".sec-dok-art")?.value || "Dokument";
		const pagesVal = card.querySelector(".sec-pages")?.value || "alle";

		const secData = {
			Dokument: dokArt,
			dokument: dokArt,
			pages: pagesVal
		};

		card.querySelectorAll(".drawer-field").forEach((el) => {
			const fieldKey = el.dataset.field;
			if (fieldKey) secData[fieldKey] = el.value.trim();
		});

		documentsPayload.push(secData);
	});

	if (documentsPayload.length === 0) return;

	const payload = {
		context,
		folder,
		filename,
		documents: documentsPayload
	};

	try {
		const res = await api("/api/split_inspector/submit", {
			method: "POST",
			body: JSON.stringify(payload)
		});

		toast(res.message || "Approved successfully!");
		closeAppInspector();
		fetchEingang();
		fetchVorgaenge();
	} catch (e) {
		toast("Approval error: " + e.message, "error");
	}
}

function closeSplitInspector() {
	const viewer = document.getElementById("inspectorViewerContainer");
	if (viewer) viewer.innerHTML = "";
	state.inspectorFile = null;
	state.inspectorFolder = null;
	state.inspectorContext = null;
	state.drawerDocSections = null;
}

async function inspectorDeleteCurrent() {
	const context = state.inspectorContext || "eingang";
	const fn = state.inspectorFile;
	const folder = state.inspectorFolder;

	if (context === "folder_edit") {
		if (!folder) return;
		closeAppInspector();
		deleteFolder(folder);
		return;
	}

	if (!fn) return;
	closeAppInspector();
	if (context === "vorgaenge") {
		deleteFile("vorgaenge", folder, fn);
	} else {
		deleteFile("eingang", "", fn);
	}
}
