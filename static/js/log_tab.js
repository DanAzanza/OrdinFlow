/* ═══════════════════════════════════════════════════════════
   LIVE LOG (IN-MEMORY DELTA POLLING)
   ═══════════════════════════════════════════════════════════ */
if (!state.logRecords) state.logRecords = [];
if (state.lastLogId === undefined) state.lastLogId = 0;
if (!state.logLevelFilter) state.logLevelFilter = "ALL";
if (state.autoScroll === undefined) state.autoScroll = true;

function startLogPolling() {
	stopLogPolling();
	fetchLogDelta();
	state.logPollInterval = setInterval(fetchLogDelta, 1200);
}

function stopLogPolling() {
	if (state.logPollInterval) {
		clearInterval(state.logPollInterval);
		state.logPollInterval = null;
	}
}

async function fetchLogDelta() {
	try {
		const d = await api(`/api/log?since_id=${state.lastLogId}&limit=300`);
		if (d.max_id !== undefined && d.max_id < state.lastLogId) {
			// Server rebooted or logs were cleared
			state.logRecords = d.logs || [];
			state.lastLogId = d.max_id;
			renderLogLines();
			return;
		}
		if (d.logs && d.logs.length > 0) {
			state.logRecords.push(...d.logs);
			state.lastLogId = d.max_id !== undefined ? d.max_id : state.lastLogId;
			if (state.logRecords.length > 1500) {
				state.logRecords = state.logRecords.slice(-1500);
			}
			renderLogLines();
		} else if (d.max_id !== undefined) {
			state.lastLogId = d.max_id;
		}
	} catch (e) {
		console.error("Error fetching log delta:", e);
	}
}

function setLogFilter(level) {
	state.logLevelFilter = level;
	["All", "Info", "Warn", "Error"].forEach((lvl) => {
		const btn = document.getElementById("logFilter" + lvl);
		if (btn) {
			if (
				(lvl.toUpperCase() === "ALL" && level === "ALL") ||
				(lvl.toUpperCase() === "WARN" &&
					(level === "WARN" || level === "WARNING")) ||
				lvl.toUpperCase() === level
			) {
				btn.className = "btn btn-sm active";
			} else {
				btn.className = "btn btn-sm";
			}
		}
	});
	renderLogLines();
}

function filterLogs() {
	renderLogLines();
}

const setLogLevelFilter = setLogFilter;

function renderLogLines() {
	const container = document.getElementById("logLines");
	if (!container) return;

	const q = (
		document.getElementById("logSearchInput")?.value || ""
	).toLowerCase().trim();
	const filter = state.logLevelFilter || "ALL";

	const filtered = state.logRecords.filter((item) => {
		const lvl = (item.level || "").toUpperCase();
		if (filter === "INFO" && lvl !== "INFO") return false;
		if (filter === "WARN" && lvl !== "WARNING" && lvl !== "WARN") return false;
		if (filter === "ERROR" && lvl !== "ERROR" && lvl !== "CRITICAL")
			return false;

		if (q) {
			const full = `${item.time || ""} ${item.level || ""} ${item.message || ""}`.toLowerCase();
			return full.includes(q);
		}
		return true;
	});

	const countBadge = document.getElementById("logCountBadge");
	if (countBadge) {
		countBadge.textContent = `${filtered.length} entries`;
	}

	container.innerHTML = filtered
		.map((item) => {
			const rawLvl = (item.level || "").toLowerCase();
			const lvlClass =
				rawLvl === "error" || rawLvl === "critical"
					? "error"
					: rawLvl.includes("warn")
						? "warning"
						: "info";

			return `<div class="log-line ${lvlClass}"><span class="log-time">[${escapeHtml(item.time || "")}]</span><span class="log-level">[${escapeHtml(item.level || "INFO")}]</span><span class="log-msg">${escapeHtml(item.message || "")}</span></div>`;
		})
		.join("");

	if (state.autoScroll) {
		requestAnimationFrame(() => {
			container.scrollTop = container.scrollHeight;
		});
	}

	updateLogInspectorAnalytics();
}

function calculateLogStatistics() {
	const records = state.logRecords || [];
	let infoCount = 0, warnCount = 0, errorCount = 0;
	records.forEach((rec) => {
		const lvl = (rec.level || "").toUpperCase();
		if (lvl === "INFO") infoCount++;
		else if (lvl === "WARNING" || lvl === "WARN") warnCount++;
		else if (lvl === "ERROR" || lvl === "CRITICAL") errorCount++;
	});

	return {
		recordsCount: records.length,
		totalFiles: 0,
		completedFiles: 0,
		manualReviewFiles: 0,
		abortedFiles: 0,
		emptyFiles: 0,
		splitBatches: 0,
		partialDocsSaved: 0,
		directDocsMoved: 0,
		totalArchivedDocs: 0,
		totalProcessingTime: "0.0",
		maxProcessingTime: "0.0",
		avgTimePerFile: "0.0",
		avgTimePerPage: "0.0",
		totalPages: 0,
		categoryCounts: {},
		tier1Count: 0,
		tier1DirectConsensus: 0,
		tier2Count: 0,
		tier2Resolved: 0,
		tier3Count: 0,
		tier3Resolved: 0,
		earlyStopCount: 0,
		successRate: "100.0",
		infoCount,
		warnCount,
		errorCount,
	};
}

async function updateLogInspectorAnalytics() {
	const activeTab = document.querySelector(".nav-item.active")?.dataset?.tab || 
	                  document.querySelector(".tab-content.active")?.id?.replace("tab-", "");
	if (activeTab !== "log") return;

	let stats;
	try {
		stats = await api("/api/log/stats");
	} catch (e) {
		stats = calculateLogStatistics();
	}
	
	const elInfo = document.getElementById("badgeHealthInfo");
	const elWarn = document.getElementById("badgeHealthWarn");
	const elErr = document.getElementById("badgeHealthErr");
	if (elInfo) elInfo.textContent = `INFO: ${stats.infoCount || 0}`;
	if (elWarn) elWarn.textContent = `WARN: ${stats.warnCount || 0}`;
	if (elErr) elErr.textContent = `ERR: ${stats.errorCount || 0}`;

	const icon = document.getElementById("inspectorHeaderIcon");
	const title = document.getElementById("inspectorHeaderTitle");
	const subtitle = document.getElementById("inspectorHeaderSubtitle");
	const body = document.getElementById("appInspectorBody");
	const inspector = document.getElementById("appInspector");

	if (inspector) inspector.classList.remove("hidden-inspector");

	if (icon) icon.textContent = "📊";
	if (title) title.textContent = "Live Log Analytics";
	if (subtitle) subtitle.textContent = "Real-time system stream statistics";

	if (!body) return;

	const catEntries = Object.entries(stats.categoryCounts || {}).sort((a, b) => b[1] - a[1]);
	let catHtml = "";
	if (catEntries.length === 0) {
		catHtml = `<div class="analytics-empty-note">No page types classified yet.</div>`;
	} else {
		catHtml = catEntries.map(([cat, count]) => {
			const pct = stats.totalPages > 0 ? Math.round((count / stats.totalPages) * 100) : 0;
			return `
				<div class="analytics-cat-row">
					<div class="analytics-cat-head">
						<span class="analytics-cat-name">${escapeHtml(cat)}</span>
						<span class="analytics-cat-stat">${count} pages (${pct}%)</span>
					</div>
					<div class="analytics-bar-track">
						<div class="analytics-bar-fill" style="width: ${pct}%;"></div>
					</div>
				</div>
			`;
		}).join("");
	}

	const totalExtracted = stats.tier1Count || stats.totalFiles || 1;
	const t1Consensus = stats.tier1DirectConsensus || stats.earlyStopCount || 0;
	const t1ConsensusPct = Math.round((t1Consensus / totalExtracted) * 100);

	const t2Count = stats.tier2Count || 0;
	const t2InvPct = Math.round((t2Count / totalExtracted) * 100);
	const t2Resolved = stats.tier2Resolved !== undefined ? stats.tier2Resolved : Math.max(0, t2Count - (stats.tier3Count || 0));
	const t2ResolvedPct = Math.round((t2Resolved / totalExtracted) * 100);

	const t3Count = stats.tier3Count || 0;
	const t3InvPct = Math.round((t3Count / totalExtracted) * 100);
	const t3Resolved = stats.tier3Resolved !== undefined ? stats.tier3Resolved : t3Count;
	const t3ResolvedPct = Math.round((t3Resolved / totalExtracted) * 100);

	const archivedDocsCount = stats.totalArchivedDocs || (stats.completedFiles || 0);

	body.innerHTML = `
		<!-- KPI Summary Grid -->
		<div class="analytics-grid-2col">
			<div class="analytics-kpi-card analytics-kpi-card-indigo">
				<div class="analytics-kpi-title-indigo">📥 Source Files</div>
				<div class="analytics-kpi-val">${stats.totalFiles || 0}</div>
				<div class="analytics-kpi-sub">${stats.completedFiles || 0} Auto / ${stats.manualReviewFiles || 0} Review</div>
			</div>

			<div class="analytics-kpi-card analytics-kpi-card-emerald">
				<div class="analytics-kpi-title-emerald">📂 Archived Docs</div>
				<div class="analytics-kpi-val">${archivedDocsCount}</div>
				<div class="analytics-kpi-sub">${stats.partialDocsSaved || 0} Split / ${stats.directDocsMoved || 0} Direct</div>
			</div>

			<div class="analytics-kpi-card analytics-kpi-card-blue">
				<div class="analytics-kpi-title-blue">🎯 Automation Rate</div>
				<div class="analytics-kpi-val">${stats.successRate || "100.0"}%</div>
				<div class="analytics-kpi-sub">without manual review</div>
			</div>

			<div class="analytics-kpi-card analytics-kpi-card-purple">
				<div class="analytics-kpi-title-purple">⚡ Avg Speed / Page</div>
				<div class="analytics-kpi-val">${stats.avgTimePerPage || "0.0"}s <span class="analytics-kpi-unit">/ page</span></div>
				<div class="analytics-kpi-sub">Ø ${stats.avgTimePerFile || "0.0"}s / file • ${stats.totalPages || 0} pages total</div>
			</div>
		</div>

		<!-- Document Types Distribution Card -->
		<div class="inspector-card">
			<h4 class="inspector-section-title">
				<span>📑</span> Document Types (Classified)
			</h4>
			${catHtml}
		</div>

		<!-- AI Pipeline Performance Card -->
		<div class="inspector-card">
			<h4 class="inspector-section-title">
				<span>🤖</span> AI Pipeline Stages
			</h4>
			<div class="stat-tier-card">
				<div class="stat-tier-header">
					<span>🟢 Tier 1 (Base & OCR Pass)</span>
					<span class="stat-tier1-val">${stats.tier1Count || 0} Runs (100%)</span>
				</div>
				<div class="stat-tier-detail">
					<span>Direct Consensus (Early Stop): <strong>${t1Consensus}</strong></span>
					<span>${t1ConsensusPct}% of docs</span>
				</div>
				<div class="stat-tier-bar-track">
					<div class="stat-tier1-fill" style="width: ${t1ConsensusPct}%;"></div>
				</div>
			</div>

			<div class="stat-tier-card">
				<div class="stat-tier-header">
					<span>🟡 Tier 2 (High-Res Verification)</span>
					<span class="stat-tier2-val">${t2Count} Runs (${t2InvPct}%)</span>
				</div>
				<div class="stat-tier-detail">
					<span>Resolved in Tier 2: <strong>${t2Resolved}</strong></span>
					<span>${t2ResolvedPct}% of docs</span>
				</div>
				<div class="stat-tier-bar-track">
					<div class="stat-tier2-fill" style="width: ${t2ResolvedPct}%;"></div>
				</div>
			</div>

			<div class="stat-tier-card">
				<div class="stat-tier-header">
					<span>🔴 Tier 3 (Tiebreaker Audit)</span>
					<span class="stat-tier3-val">${t3Count} Runs (${t3InvPct}%)</span>
				</div>
				<div class="stat-tier-detail">
					<span>Resolved in Tier 3: <strong>${t3Resolved}</strong></span>
					<span>${t3ResolvedPct}% of docs</span>
				</div>
				<div class="stat-tier-bar-track">
					<div class="stat-tier3-fill" style="width: ${t3ResolvedPct}%;"></div>
				</div>
			</div>
		</div>
	`;
}

function toggleAutoScroll() {
	state.autoScroll = !state.autoScroll;
	const btn = document.getElementById("autoScrollBtn");
	if (btn)
		btn.textContent = "Auto-Scroll: " + (state.autoScroll ? "On" : "Off");
	if (state.autoScroll) {
		const c = document.getElementById("logLines");
		if (c) c.scrollTop = c.scrollHeight;
	}
}


async function clearLog() {
	try {
		await api("/api/log/clear", { method: "POST" });
		state.logRecords = [];
		state.lastLogId = 0;
		renderLogLines();
		toast("Log geleert.");
	} catch (e) {
		state.logRecords = [];
		state.lastLogId = 0;
		renderLogLines();
		toast("Fehler beim Leeren des Logs auf dem Server: " + e.message, "error");
	}
}
