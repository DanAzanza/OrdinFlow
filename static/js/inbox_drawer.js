/* ═══════════════════════════════════════════════════════════
   INBOX & SPLIT DRAWER INSPECTOR (Document & Folder Inspector)
   ═══════════════════════════════════════════════════════════ */

function extractFieldsFromFilenameAndFolder(docType, filename, folderName = "") {
	const extracted = {};
	const rawName = (filename || "").split("/").pop();
	const baseName = rawName.replace(/\.[^/.]+$/, "");
	const docTypes = getImportSkillsDocTypes();
	const docCfg = docTypes[docType] || (state.config && state.config.document_types ? state.config.document_types[docType] : null);

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

	if (parts.length > 0 && !extracted.Document && parts[0] !== "----") {
		extracted.Document = parts[0];
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

			if (fieldKey && val && val !== "----" && val !== "MISSING") {
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

	let context = "inbox";
	let targetFile = contextOrFilename;

	if (contextOrFilename === "folder_edit") {
		context = "folder_edit";
		targetFile = null;
	} else if (contextOrFilename === "cases" || contextOrFilename === "inbox") {
		context = contextOrFilename;
		targetFile = filename;
	} else {
		context = "inbox";
		targetFile = contextOrFilename;
	}

	state.inspectorContext = context;
	state.inspectorFolder = folder;
	state.inspectorFile = targetFile;

	if (context === "folder_edit") {
		const safeFolder = encodeURIComponent(folder);
		const delimiter = (state.config && state.config.folder_delimiter) || "--";
		const struct = (state.config && Array.isArray(state.config.folder_structure)) ? state.config.folder_structure : [];
		const parts = folder ? folder.split(delimiter) : [];

		let extractedData = {};
		struct.forEach((comp, i) => {
			const m = String(comp).match(/\{(\w+)\}/);
			if (m) {
				const fieldName = m[1];
				let val = (i < parts.length) ? parts[i].trim() : "";
				if (val === "----" || val.toUpperCase() === "MISSING") {
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
			const d = await api("/api/cases/" + safeFolder);
			if (d && d.files && d.files.length > 0) {
				const firstFile = d.files.find(f => f.has_preview) || d.files[0];
				const safeFirst = encodeURIComponent(firstFile.name);
				fileUrl = `/api/file/cases/${safeFolder}/${safeFirst}`;
				previewUrl = firstFile.preview_url || `/api/preview/Cases/${safeFolder}/${safeFirst}`;
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
								? `<iframe src="${escapeHtml(fileUrl || previewUrl)}#toolbar=0&navpanes=0&view=FitH"></iframe>`
								: `<img src="${escapeHtml(previewUrl || fileUrl)}" alt="Preview" />`)
							: `<div class="inbox-drawer-folder-empty">📁 Folder contains no preview files</div>`
						}
					</div>
				</div>
				<div class="inspector-card">
					<h4 class="inspector-section-title">
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

	if (context === "cases") {
		const safeFolder = encodeURIComponent(folder);
		const safeFile = encodeURIComponent(targetFile);
		fileUrl = `/api/file/cases/${safeFolder}/${safeFile}`;
		previewUrl = `/api/preview/Cases/${safeFolder}/${safeFile}`;
	} else {
		fileObj = (state.inbox || []).find(
			(f) => f.path === targetFile || f.name === targetFile,
		) || { name: targetFile, path: targetFile };
		fileUrl = fileObj.file_url || `/api/file/inbox/${encodeURIComponent(targetFile)}`;
		previewUrl = fileObj.preview_url || "";

		if (fileObj.extracted && Object.keys(fileObj.extracted).length > 0) {
			extractedData = Object.assign({}, fileObj.extracted);
			hasMetaFile = true;
		}
	}

	if (!hasMetaFile) {
		try {
			const metaUrl = context === "cases"
				? `/api/file/meta/cases/${encodeURIComponent(folder)}/${encodeURIComponent(targetFile)}`
				: `/api/file/meta/inbox/${encodeURIComponent(targetFile)}`;
			const metaJson = await api(metaUrl);
			if (metaJson && metaJson.extracted && Object.keys(metaJson.extracted).length > 0) {
				extractedData = Object.assign({}, metaJson.extracted);
				hasMetaFile = true;
			}
		} catch (e) {
			// No .meta file available
		}
	}

	let docType = extractedData.Document || extractedData.DocumentType || splitByDelimiter(targetFile)[0] || "";

	if (!hasMetaFile) {
		const parsedFromFilename = extractFieldsFromFilenameAndFolder(docType, targetFile, folder);
		extractedData = Object.assign({}, parsedFromFilename, extractedData);
		if (!docType && parsedFromFilename.Document) {
			docType = parsedFromFilename.Document;
		}
	}

	state.currentInspectorExtracted = extractedData;
	state.drawerDocSections = initDrawerDocSections(docType, extractedData);

	if (typeof openAppInspector === "function") {
		openAppInspector({
			icon: fileObj?.is_pruefen ? "⚠" : "📄",
			title: fileObj?.name || targetFile,
			subtitle: context === "cases" ? `Case: ${folder}` : (fileObj?.is_pruefen ? "Verification required" : "Ready for processing"),
			previewUrl: previewUrl || fileUrl,
			html: `
				<div class="inspector-card">
					<div class="inspector-preview-wrap">
						${(previewUrl || fileUrl).endsWith(".pdf") || (targetFile || "").toLowerCase().endsWith(".pdf")
								? `<iframe src="${escapeHtml(fileUrl || previewUrl)}#toolbar=0&navpanes=0&view=FitH"></iframe>`
								: `<img src="${escapeHtml(previewUrl || fileUrl)}" alt="Preview" />`
						}
					</div>
				</div>
				<div class="inspector-card">
					<h4 class="inspector-section-title">
						<span>✏️</span> Edit & Assign Document
					</h4>
					<div id="drawerFormWrapper">
						${buildGenericInspectorForm(docType, extractedData)}
					</div>
				</div>
			`
		});
	}
}

function formatPageRange(pages) {
	if (!pages || pages === "all" || pages === "*") return "all";
	if (Array.isArray(pages)) {
		if (pages.length === 0) return "all";
		const nums = pages.map(Number).filter(n => !isNaN(n)).sort((a, b) => a - b);
		if (nums.length === 0) return "all";
		const isContiguous = nums.every((n, i) => i === 0 || n === nums[i - 1] + 1);
		if (isContiguous && nums.length > 1) {
			return `${nums[0]}-${nums[nums.length - 1]}`;
		}
		return nums.join(", ");
	}
	return String(pages).trim();
}

function initDrawerDocSections(docType, extractedData = {}) {
	const dokArtOptions = getDokArtOptions();
	const pageResults = (extractedData && Array.isArray(extractedData.page_results) && extractedData.page_results.length > 0)
		? extractedData.page_results
		: null;

	if (pageResults) {
		return pageResults.map((pr, idx) => {
			const prType = pr.Document || pr.document || pr.DocumentType || docType || dokArtOptions[0] || "Document";
			const prPages = formatPageRange(pr.pages || (pageResults.length === 1 ? "all" : (idx + 1)));
			const mergedExtracted = Object.assign({}, extractedData, pr);
			return {
				id: "sec_" + Date.now() + "_" + idx + "_" + Math.floor(Math.random() * 1000),
				docType: prType,
				pages: prPages,
				extracted: mergedExtracted
			};
		});
	}

	const rawDoc = String(docType || "").trim();
	const isCompound = rawDoc.includes("+") && !dokArtOptions.includes(rawDoc);
	if (isCompound) {
		const parts = rawDoc.split("+").map(s => s.trim()).filter(Boolean);
		if (parts.length > 1) {
			return parts.map((partType, idx) => ({
				id: "sec_" + Date.now() + "_" + idx + "_" + Math.floor(Math.random() * 1000),
				docType: partType,
				pages: String(idx + 1),
				extracted: Object.assign({}, extractedData, { Document: partType, document: partType })
			}));
		}
	}

	return [
		{
			id: "sec_" + Date.now() + "_0_" + Math.floor(Math.random() * 1000),
			docType: rawDoc || dokArtOptions[0] || "Document",
			pages: "all",
			extracted: Object.assign({}, extractedData)
		}
	];
}

function saveCurrentDrawerFormState() {
	if (!state.drawerDocSections) return;
	const cards = document.querySelectorAll(".drawer-section-card");
	cards.forEach((card) => {
		const secId = card.dataset.secid;
		const sec = state.drawerDocSections.find(s => String(s.id) === String(secId));
		if (!sec) return;
		const dokArt = card.querySelector(".sec-dok-art")?.value;
		const pagesVal = card.querySelector(".sec-pages")?.value;
		if (dokArt) sec.docType = dokArt;
		if (pagesVal !== undefined) sec.pages = pagesVal;
		if (!sec.extracted) sec.extracted = {};
		card.querySelectorAll(".drawer-field").forEach((el) => {
			const k = el.dataset.field;
			if (k) sec.extracted[k] = el.value;
		});
	});
}

function addDrawerDocSection() {
	saveCurrentDrawerFormState();
	if (!state.drawerDocSections) state.drawerDocSections = [];
	const options = getDokArtOptions();
	const defaultType = options[0] || "Document";
	state.drawerDocSections.push({
		id: "sec_" + Date.now() + "_" + Math.floor(Math.random() * 1000),
		docType: defaultType,
		pages: "",
		extracted: Object.assign({}, state.currentInspectorExtracted || {})
	});
	renderDrawerSections();
}

function removeDrawerDocSection(secId) {
	saveCurrentDrawerFormState();
	if (!state.drawerDocSections || state.drawerDocSections.length <= 1) return;
	state.drawerDocSections = state.drawerDocSections.filter(s => String(s.id) !== String(secId));
	renderDrawerSections();
}

function onSectionDokArtChange(secId, newDokArt) {
	saveCurrentDrawerFormState();
	if (!state.drawerDocSections) return;
	const sec = state.drawerDocSections.find(s => String(s.id) === String(secId));
	if (sec) {
		sec.docType = newDokArt;
		renderDrawerSections();
	}
}

function renderDrawerSections() {
	const wrapper = document.getElementById("drawerFormWrapper");
	if (wrapper && state.drawerDocSections) {
		wrapper.innerHTML = buildGenericInspectorForm(null, state.currentInspectorExtracted || {});
	}
}

function buildGenericInspectorForm(docType = null, extractedData = {}) {
	if (!state.drawerDocSections || state.drawerDocSections.length === 0) {
		state.drawerDocSections = initDrawerDocSections(docType, extractedData);
	}

	const dokArtOptions = getDokArtOptions();
	const isMulti = state.drawerDocSections.length > 1;
	const isPdf = (state.inspectorFile || "").toLowerCase().endsWith(".pdf");

	let html = `<div id="drawerSectionsList" class="drawer-sections-flex">`;

	state.drawerDocSections.forEach((sec, idx) => {
		const curDokArt = sec.docType;
		const docTypes = getImportSkillsDocTypes();
		const docCfg = docTypes[curDokArt] || (state.config && state.config.document_types ? state.config.document_types[curDokArt] : null);
		const extractionFieldsConfig = (docCfg && docCfg.extraction_fields) ? docCfg.extraction_fields : null;
		const isDependent = docCfg && (docCfg.dependent === true || (docCfg.routing && docCfg.routing.dependent === true));

		const ignoredMetaKeys = new Set([
			"raw", "status", "confidence", "_confidence",
			"pages", "page_results", "document", "documenttype", "document_type",
			"dokument", "dokumentart", "dok_arts", "vision_description",
			"is_pruefen", "file_url", "preview_url", "images", "raw_images", "_img",
			"zeit", "timestamp", "filename", "dateiname", "grund", "reason"
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

		const hasMatch = dokArtOptions.includes(curDokArt);
		const optionsList = hasMatch ? dokArtOptions : (curDokArt ? [curDokArt, ...dokArtOptions] : dokArtOptions);

		html += `
			<div class="drawer-section-card" data-secid="${escapeHtml(String(sec.id))}">
				<div class="drawer-section-header">
					<span class="inbox-drawer-title-accent">
						📄 Section ${idx + 1} (${escapeHtml(curDokArt)})
					</span>
					${isMulti ? `<button type="button" class="btn btn-sm btn-danger inbox-drawer-btn-remove" data-secid="${escapeHtml(String(sec.id))}" onclick="removeDrawerDocSection(this.dataset.secid)">🗑️ Remove section</button>` : ""}
				</div>

				<div class="grid-2col">
					<div class="form-group zero-margin">
						<label for="${sanitizeDomId("sec", sec.id, "dok_art")}" class="doc-editor-label">Document Type *</label>
						<select id="${sanitizeDomId("sec", sec.id, "dok_art")}" class="doc-editor-input sec-dok-art inbox-drawer-field-select-lg" aria-label="Document Type" data-secid="${escapeHtml(String(sec.id))}" onchange="onSectionDokArtChange(this.dataset.secid, this.value)">
							${optionsList.length > 0
								? optionsList.map(opt => `<option value="${escapeHtml(opt)}" ${opt === curDokArt ? "selected" : ""}>${escapeHtml(opt)}</option>`).join("")
								: `<option value="">Empty</option>`
							}
						</select>
					</div>

					<div class="form-group zero-margin">
						<label for="${sanitizeDomId("sec", sec.id, "pages")}" class="doc-editor-label">Pages (e.g. 1 or 2-3) *</label>
						<input type="text" id="${sanitizeDomId("sec", sec.id, "pages")}" class="doc-editor-input sec-pages inbox-drawer-field-input-lg" aria-label="Pages to extract" value="${escapeHtml(sec.pages || "all")}" placeholder="all, 1, 2-3" />
					</div>
				</div>

				<div class="sec-fields-container">`;

		const keys = Object.keys(fieldValues);
		if (keys.length === 0) {
			html += `<div class="inbox-drawer-empty-box">No extraction fields for this type</div>`;
		} else {
			for (const key of keys) {
				const val = fieldValues[key] !== null && fieldValues[key] !== undefined ? String(fieldValues[key]) : "";
				const isDate = key.toLowerCase().includes("datum") || key.toLowerCase().includes("date");
				const isBool = typeof fieldValues[key] === "boolean" || key.toLowerCase() === "signed";
				const safeFieldId = sanitizeDomId("sec", sec.id, "field", key);

				let fieldControlHtml = "";
				if (isDate) {
					const isoDate = typeof normalizeDateForInput === "function" ? normalizeDateForInput(val) : null;
					if (isoDate !== null) {
						fieldControlHtml = `<input type="date" id="${safeFieldId}" class="doc-editor-input drawer-field inbox-drawer-field-date" data-field="${escapeHtml(key)}" value="${escapeHtml(isoDate)}" aria-label="${escapeHtml(key)}" />`;
					} else if (val) {
						fieldControlHtml = `<input type="text" id="${safeFieldId}" class="doc-editor-input drawer-field inbox-drawer-field-input" data-field="${escapeHtml(key)}" value="${escapeHtml(val)}" placeholder="${escapeHtml(key)}" aria-label="${escapeHtml(key)}" title="Non-standard date format" />`;
					} else {
						fieldControlHtml = `<input type="date" id="${safeFieldId}" class="doc-editor-input drawer-field inbox-drawer-field-date" data-field="${escapeHtml(key)}" value="" aria-label="${escapeHtml(key)}" />`;
					}
				} else if (isBool) {
					fieldControlHtml = `<select id="${safeFieldId}" class="doc-editor-input drawer-field inbox-drawer-field-select" data-field="${escapeHtml(key)}" aria-label="${escapeHtml(key)}">
							<option value="true" ${val === "true" || val === "Yes" || fieldValues[key] === true ? "selected" : ""}>Yes / Signed</option>
							<option value="false" ${val === "false" || val === "No" || fieldValues[key] === false ? "selected" : ""}>No / Not signed</option>
					   </select>`;
				} else {
					fieldControlHtml = `<input type="text" id="${safeFieldId}" class="doc-editor-input drawer-field inbox-drawer-field-input" data-field="${escapeHtml(key)}" value="${escapeHtml(val)}" placeholder="${escapeHtml(key)}" aria-label="${escapeHtml(key)}" />`;
				}

				html += `
					<div class="form-group drawer-field-group">
						<label for="${safeFieldId}" class="doc-field-label-sm">
							<span>${escapeHtml(key)} *</span>
						</label>
						${fieldControlHtml}
					</div>`;
			}
		}

		html += `</div></div>`;
	});

	html += `</div>

		${isPdf ? `
			<div class="inbox-drawer-add-row">
				<button type="button" class="btn btn-sm inbox-drawer-btn-full" onclick="addDrawerDocSection()">
					➕ Add another document type / page range
				</button>
			</div>
		` : ""}

		<div class="inbox-drawer-action-row">
			<button type="button" class="btn btn-primary btn-sm inbox-drawer-btn-flex" onclick="submitDrawerInspector()">✅ Approve & Move</button>
			<button type="button" class="btn btn-danger btn-sm" onclick="inspectorDeleteCurrent()">🗑️ Delete document</button>
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

	let html = `<div class="drawer-section-card">`;
	html += `<div class="folder-attributes-title">Metadata & Folder Attributes</div>`;

	fieldSet.forEach(fieldKey => {
		const label = cleanHeaderLabel ? cleanHeaderLabel(fieldKey) : fieldKey;
		const val = extractedData[fieldKey] !== undefined ? extractedData[fieldKey] : "";
		const isDate = fieldKey.toLowerCase().includes("datum") || fieldKey.toLowerCase().includes("date");
		const safeFieldId = sanitizeDomId("folder_field", fieldKey);

		let fieldControlHtml = "";
		if (isDate) {
			const isoDate = typeof normalizeDateForInput === "function" ? normalizeDateForInput(val) : null;
			if (isoDate !== null) {
				fieldControlHtml = `<input type="date" id="${safeFieldId}" class="drawer-field input-sm inbox-drawer-field-input" data-field="${escapeHtml(fieldKey)}" value="${escapeHtml(isoDate)}" aria-label="${escapeHtml(label)}" />`;
			} else if (val) {
				fieldControlHtml = `<input type="text" id="${safeFieldId}" class="drawer-field input-sm inbox-drawer-field-input" data-field="${escapeHtml(fieldKey)}" value="${escapeHtml(val)}" placeholder="Enter ${escapeHtml(label)}..." aria-label="${escapeHtml(label)}" />`;
			} else {
				fieldControlHtml = `<input type="date" id="${safeFieldId}" class="drawer-field input-sm inbox-drawer-field-input" data-field="${escapeHtml(fieldKey)}" value="" aria-label="${escapeHtml(label)}" />`;
			}
		} else {
			fieldControlHtml = `<input type="text" id="${safeFieldId}" class="drawer-field input-sm inbox-drawer-field-input" data-field="${escapeHtml(fieldKey)}" value="${escapeHtml(val)}" placeholder="Enter ${escapeHtml(label)}..." aria-label="${escapeHtml(label)}" />`;
		}

		html += `
			<div class="form-group">
				<label for="${safeFieldId}" class="doc-field-label-sm">
					${escapeHtml(label)}
				</label>
				${fieldControlHtml}
			</div>
		`;
	});

	html += `
		<div class="inbox-drawer-action-row">
			<button type="button" class="btn btn-primary btn-sm inbox-drawer-btn-flex" onclick="submitDrawerInspector()">✅ Save</button>
			<button type="button" class="btn btn-danger btn-sm" onclick="inspectorDeleteCurrent()">🗑️ Delete folder</button>
		</div>
	`;

	html += `</div>`;
	return html;
}

async function submitDrawerInspector() {
	const context = state.inspectorContext || "inbox";
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
			const res = await api("/api/cases/" + encodeURIComponent(folder), {
				method: "PUT",
				body: JSON.stringify(payload)
			});

			toast(res.message || "Folder updated successfully!");
			closeAppInspector();
			if (state.expandedFolder === folder) state.expandedFolder = res.folder || folder;
			AppEvents.emit("cases:refresh");
		} catch (e) {
			toast("Error saving folder: " + e.message, "error");
		}
		return;
	}

	if (!filename) return;

	const sectionCards = document.querySelectorAll(".drawer-section-card");
	const documentsPayload = [];

	sectionCards.forEach((card) => {
		const dokArt = card.querySelector(".sec-dok-art")?.value || "Document";
		const pagesVal = card.querySelector(".sec-pages")?.value || "all";

		const secData = {
			Document: dokArt,
			document: dokArt,
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
		AppEvents.emit("inbox:refresh");
		AppEvents.emit("cases:refresh");
	} catch (e) {
		toast("Approval error: " + e.message, "error");
	}
}

async function inspectorDeleteCurrent() {
	const context = state.inspectorContext || "inbox";
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
	if (context === "cases") {
		deleteFile("cases", folder, fn);
	} else {
		deleteFile("inbox", "", fn);
	}
}
