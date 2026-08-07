const state = {
	cases: [],
	inbox: [],
	config: null,
	expandedFolder: null,
	expandedFiles: [],
	sortCol: 0,
	sortAsc: true,
	paused: false,
	selectedInboxFile: null,
	editingFolder: null,
	editingFile: null,
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
	const div = document.createElement("div");
	div.textContent = str;
	return div.innerHTML;
}

function formatDateString(dateStr) {
	if (!dateStr || dateStr === "–") return "–";
	// Match YYYY-MM-DD
	const mYmd = String(dateStr)
		.trim()
		.match(/^(\d{4})-(\d{2})-(\d{2})$/);
	if (mYmd) {
		return `${mYmd[3]}.${mYmd[2]}.${mYmd[1]}`;
	}
	// Match DD-MM-YYYY
	const mDmy = String(dateStr)
		.trim()
		.match(/^(\d{2})-(\d{2})-(\d{4})$/);
	if (mDmy) {
		return `${mDmy[1]}.${mDmy[2]}.${mDmy[3]}`;
	}
	return dateStr;
}

function cleanHeaderLabel(str) {
	if (!str) return "";
	// Add space between adjacent placeholders: }{ -> } {
	const s = str.replace(/\}\{/g, "} {");
	// Remove curly braces
	const cleaned = s.replace(/\{/g, "").replace(/\}/g, "");
	return cleaned.trim();
}

function getDynamicHeaders() {
	const struct = (state.config && state.config.folder_structure) || [];
	return struct.map(cleanHeaderLabel);
}

function renderValidationBadges(ext) {
	if (!ext || typeof ext !== "object") return "";
	const hasSign = ext.Signed !== undefined ? ext.Signed : null;

	if (hasSign === null) return "";

	let html =
		'<div style="margin-top:6px; display:flex; gap:6px; flex-wrap:wrap;">';
	html += `<span class="val-badge ${hasSign ? "success" : "danger"}">${hasSign ? "✍️ Signed" : "❌ Not Signed"}</span>`;
	html += "</div>";
	return html;
}

function toast(message, type = "success") {
	const container = document.getElementById("toasts");
	const el = document.createElement("div");
	el.className = `toast ${type}`;
	el.innerHTML = `${type === "success" ? "✅" : "❌"} ${escapeHtml(message)}`;
	container.appendChild(el);
	setTimeout(() => {
		el.style.opacity = "0";
		el.style.transform = "translateY(10px)";
		setTimeout(() => el.remove(), 300);
	}, 3500);
}

async function api(url, options = {}) {
	try {
		const res = await fetch(url, {
			headers: { "Content-Type": "application/json" },
			...options,
		});
		if (!res.ok) throw new Error(`HTTP ${res.status}`);
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
		state.paused = d.paused;
		// Badge
		const badge = document.getElementById("statusBadge");
		const txt = document.getElementById("statusText");
		if (badge) {
			badge.className = "status-badge " + (d.paused ? "paused" : "active");
		}
		if (txt) {
			txt.textContent = d.paused ? "Paused" : "Active";
		}

		const tgl = document.getElementById("toggleLabel");
		if (tgl) {
			tgl.textContent = d.paused ? "Resume" : "Pause";
		}

		const ico = document.getElementById("toggleIcon");
		if (ico) {
			ico.setAttribute(
				"d",
				d.paused
					? "M11.596 8.697l-6.363 3.692c-.54.313-1.233-.066-1.233-.697V4.308c0-.63.692-1.01 1.233-.696l6.363 3.692a.802.802 0 0 1 0 1.393z"
					: "M5.5 3.5A1.5 1.5 0 0 1 7 5v6a1.5 1.5 0 0 1-3 0V5a1.5 1.5 0 0 1 1.5-1.5zm5 0A1.5 1.5 0 0 1 12 5v6a1.5 1.5 0 0 1-3 0V5a1.5 1.5 0 0 1 1.5-1.5z",
			);
		}

		// Stats
		const statAvg = document.getElementById("statAvg");
		if (statAvg) statAvg.textContent = (d.avg_duration ?? 0).toFixed(1);
	} catch (e) {
		console.error("Error fetching status:", e);
	}
}

async function toggleRouter() {
	try {
		const url = state.paused ? "/api/router/resume" : "/api/router/pause";
		await api(url, { method: "POST" });
		await fetchStatus();
		toast(state.paused ? "Router paused" : "Router resumed");
	} catch (e) {
		toast("Error: " + e.message, "error");
	}
}

async function shutdownApp() {
	if (
		confirm(
			"Are you sure you want to exit DMS? The system will shut down completely.",
		)
	) {
		try {
			await api("/api/router/shutdown", { method: "POST" });
			toast("System shutting down...", "success");
			setTimeout(() => window.close(), 1500);
		} catch (e) {
			toast("Shutdown error: " + e.message, "error");
		}
	}
}

/* ═══════════════════════════════════════════════════════════
   TABS
   ═══════════════════════════════════════════════════════════ */

async function ensureSkillsLoaded() {
	if (!state.skills || state.skills.length === 0) {
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

function getImportSkillsDocTypes() {
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

function getDokArtOptions() {
	const docTypes = getImportSkillsDocTypes();
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
