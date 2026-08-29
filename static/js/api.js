/* ═══════════════════════════════════════════════════════════
   LIGHTWEIGHT APP EVENT BUS (PUB/SUB)
   ═══════════════════════════════════════════════════════════ */
window.AppEvents = {
	_listeners: {},
	on(event, callback) {
		if (!this._listeners[event]) this._listeners[event] = [];
		this._listeners[event].push(callback);
		return () => this.off(event, callback);
	},
	off(event, callback) {
		if (!this._listeners[event]) return;
		this._listeners[event] = this._listeners[event].filter((cb) => cb !== callback);
	},
	emit(event, data) {
		if (!this._listeners[event]) return;
		this._listeners[event].forEach((cb) => {
			try {
				cb(data);
			} catch (err) {
				console.error(`[AppEvents] Error in handler for '${event}':`, err);
			}
		});
	},
};

const state = {
	cases: [],
	inbox: [],
	config: null,
	expandedFolder: null,
	expandedFiles: [],
	sortCol: 0,
	sortAsc: true,
};

/* ═══════════════════════════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════════════════════════ */
function formatSize(bytes) {
	if (!bytes || bytes === 0) return "0 B";
	if (bytes < 1024) return bytes + " B";
	if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
	return (bytes / 1048576).toFixed(1) + " MB";
}

function escapeHtml(str) {
	if (str === null || str === undefined) return "";
	return String(str)
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#39;");
}

function safePathEncode(path) {
	if (!path) return "";
	return String(path).split("/").map(encodeURIComponent).join("/");
}

function formatDateString(dateStr) {
	if (!dateStr || dateStr === "–") return "–";
	const s = String(dateStr).trim();
	const mYmd = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
	if (mYmd) return `${mYmd[3]}.${mYmd[2]}.${mYmd[1]}`;
	const mDmy = s.match(/^(\d{1,2})[.-](\d{1,2})[.-](\d{4})$/);
	if (mDmy) return `${mDmy[1].padStart(2, "0")}.${mDmy[2].padStart(2, "0")}.${mDmy[3]}`;
	return dateStr;
}

function parseDateToTimestamp(dateStr) {
	if (!dateStr || dateStr === "–" || dateStr === "-") return null;
	const s = String(dateStr).trim();
	const mIso = s.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/);
	if (mIso) return new Date(Number(mIso[1]), Number(mIso[2]) - 1, Number(mIso[3])).getTime();
	const mDe = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
	if (mDe) return new Date(Number(mDe[3]), Number(mDe[2]) - 1, Number(mDe[1])).getTime();
	return null;
}

function isValidCalendarDate(year, month, day) {
	if (year < 1900 || year > 2100 || month < 1 || month > 12 || day < 1 || day > 31) return false;
	const d = new Date(Date.UTC(year, month - 1, day));
	return d.getUTCFullYear() === year && d.getUTCMonth() === month - 1 && d.getUTCDate() === day;
}

function normalizeDateForInput(val) {
	if (val === null || val === undefined) return null;
	let s = String(val).trim();
	if (!s) return null;

	s = s.split(/[T\s]/)[0].trim();
	let y, m, d;

	let match = s.match(/^(\d{4})[./-](\d{1,2})[./-](\d{1,2})$/);
	if (match) {
		y = parseInt(match[1], 10);
		m = parseInt(match[2], 10);
		d = parseInt(match[3], 10);
	} else {
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

function splitByDelimiter(folderName, delimiter) {
	if (!folderName) return [];
	const delim = delimiter || (state.config && state.config.folder_delimiter) || "--";
	if (folderName.includes(delim)) return folderName.split(delim);
	if (folderName.includes("__")) return folderName.split("__");
	return [folderName];
}

function cleanHeaderLabel(str) {
	if (!str) return "";
	const s = str.replace(/\}\{/g, "} {");
	return s.replace(/\{/g, "").replace(/\}/g, "").trim();
}

function renderValidationBadges(ext) {
	if (!ext || typeof ext !== "object") return "";
	const hasSign = ext.Signed !== undefined ? ext.Signed : null;
	if (hasSign === null) return "";

	let html = '<div class="validation-badges-container">';
	html += `<span class="val-badge ${hasSign ? "success" : "danger"}">${hasSign ? "✍️ Signed" : "❌ Not Signed"}</span>`;
	html += "</div>";
	return html;
}

function toast(message, type = "success") {
	const container = document.getElementById("toasts");
	if (!container) return;
	const el = document.createElement("div");
	el.className = `toast ${type}`;
	el.innerHTML = `${type === "success" ? "✅" : "❌"} ${escapeHtml(message)}`;
	container.appendChild(el);
	setTimeout(() => {
		el.classList.add("toast-fade-out");
		setTimeout(() => el.remove(), 300);
	}, 3500);
}

async function api(url, options = {}) {
	try {
		const res = await fetch(url, {
			headers: { "Content-Type": "application/json" },
			...options,
		});
		if (!res.ok) {
			let errorMsg = `HTTP ${res.status}`;
			try {
				const errData = await res.json();
				errorMsg = errData.error || errData.message || errData.detail || errorMsg;
			} catch (_) {
				try {
					const textData = await res.text();
					if (textData) errorMsg = textData.slice(0, 120);
				} catch (_) {}
			}
			throw new Error(errorMsg);
		}
		return await res.json();
	} catch (e) {
		console.error("API Error:", url, e);
		throw e;
	}
}

/* ═══════════════════════════════════════════════════════════
   STATUS POLLING
   ═══════════════════════════════════════════════════════════ */
async function fetchStatus() {
	try {
		const d = await api("/api/status");

		// Skill Queue status check
		if (d.skill_queue) {
			state.skillQueue = d.skill_queue;
			if (typeof updateSkillsSidebarBadge === "function") {
				updateSkillsSidebarBadge(d.skill_queue);
			}
			if (typeof updateQueueInspectorIfOpen === "function") {
				updateQueueInspectorIfOpen(d.skill_queue);
			}
		}
	} catch (e) {
		console.error("Error fetching status:", e);
	}
}

/* ═══════════════════════════════════════════════════════════
   TABS
   ═══════════════════════════════════════════════════════════ */

async function ensureSkillsLoaded(forceRefresh = false) {
	if (forceRefresh || !state.skills || state.skills.length === 0) {
		try {
			const data = await api("/api/skills");
			state.skills = data.skills || [];
		} catch (e) {
			console.error("Error loading skills for inspector:", e);
			state.skills = [];
		}
	}
	return state.skills;
}

function getEffectiveDocTypes() {
	const skills = state.skills || [];
	const importSkills = skills.filter((s) => s.type === "import" && s.enabled !== false);
	const docTypes = {};

	for (const skill of importSkills) {
		if (skill.document_types && typeof skill.document_types === "object") {
			for (const [dtName, dtConfig] of Object.entries(skill.document_types)) {
				docTypes[dtName] = dtConfig;
			}
		}
	}

	if (Object.keys(docTypes).length === 0 && state.config && state.config.document_types) {
		return state.config.document_types;
	}

	return docTypes;
}

const getImportSkillsDocTypes = getEffectiveDocTypes;

function getDocTypeConfig(name) {
	if (!name) return null;
	const docTypes = getEffectiveDocTypes();
	if (docTypes[name]) return docTypes[name];
	const lower = String(name).toLowerCase();
	for (const [k, v] of Object.entries(docTypes)) {
		if (k.toLowerCase() === lower) return v;
	}
	return null;
}

function getDocTypeEmoji(name) {
	const cfg = getDocTypeConfig(name);
	return (cfg && cfg.emoji) || "📄";
}

function getDokArtOptions() {
	const docTypes = getEffectiveDocTypes();
	const keys = Object.keys(docTypes);
	return keys.length > 0 ? keys.sort() : [];
}

async function fetchConfig() {
	try {
		state.config = await api("/api/config");
		await ensureSkillsLoaded();
		renderLegend();
		renderCases();
		renderInbox();
	} catch (e) {
		console.error("Error fetching config:", e);
	}
}
