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
		if (d.logs && d.logs.length > 0) {
			state.logRecords.push(...d.logs);
			state.lastLogId = d.max_id || state.lastLogId;
			if (state.logRecords.length > 1000) {
				state.logRecords = state.logRecords.slice(-1000);
			}
			renderLogLines();
		}
	} catch (e) {
		console.error("Error fetching log delta:", e);
	}
}

function setLogLevelFilter(level) {
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
				btn.className = "btn btn-sm btn-accent";
			} else {
				btn.className = "btn btn-sm";
			}
		}
	});
	renderLogLines();
}

function renderLogLines() {
	const container = document.getElementById("logLines");
	if (!container) return;

	const q = (
		document.getElementById("logSearchInput")?.value || ""
	).toLowerCase();
	const filter = state.logLevelFilter;

	const filtered = state.logRecords.filter((item) => {
		const lvl = (item.level || "").toUpperCase();
		if (filter === "INFO" && lvl !== "INFO") return false;
		if (filter === "WARN" && lvl !== "WARNING" && lvl !== "WARN") return false;
		if (filter === "ERROR" && lvl !== "ERROR" && lvl !== "CRITICAL")
			return false;

		if (q) {
			const msg = (item.message || "").toLowerCase();
			return msg.includes(q);
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
	let completedFiles = 0;
	let manualReviewFiles = 0;
	let totalProcessingTime = 0;
	let maxProcessingTime = 0;
	let totalPages = 0;
	
	const categoryCounts = {};
	let tier1Count = 0;
	let tier2Count = 0;
	let tier3Count = 0;
	let earlyStopCount = 0;

	let infoCount = 0;
	let warnCount = 0;
	let errorCount = 0;

	records.forEach((rec) => {
		const msg = rec.message || "";
		const lvl = (rec.level || "").toUpperCase();

		if (lvl === "INFO") infoCount++;
		else if (lvl === "WARNING" || lvl === "WARN") warnCount++;
		else if (lvl === "ERROR" || lvl === "CRITICAL") errorCount++;

		const matchTime = msg.match(/Processing of .* completed successfully after ([\d\.]+) seconds/i);
		if (matchTime) {
			completedFiles++;
			const secs = parseFloat(matchTime[1]);
			totalProcessingTime += secs;
			if (secs > maxProcessingTime) maxProcessingTime = secs;
		}

		const matchIncomplete = msg.match(/Processing of .* incomplete \(([\d\.]+)s\)/i) || msg.includes("manual review required");
		if (matchIncomplete) {
			manualReviewFiles++;
			if (matchIncomplete[1] && !isNaN(parseFloat(matchIncomplete[1]))) {
				const secs = parseFloat(matchIncomplete[1]);
				totalProcessingTime += secs;
				if (secs > maxProcessingTime) maxProcessingTime = secs;
			}
		}

		const matchClass = msg.match(/Page \d+ classification:\s*(.+)/i);
		if (matchClass) {
			totalPages++;
			const cat = matchClass[1].trim();
			categoryCounts[cat] = (categoryCounts[cat] || 0) + 1;
		}

		if (msg.includes("Early stop after Tier 1")) earlyStopCount++;
		if (msg.includes("Starting Tier 1")) tier1Count++;
		if (msg.includes("Starting Tier 2")) tier2Count++;
		if (msg.includes("Starting Tier 3")) tier3Count++;
	});

	const totalFiles = completedFiles + manualReviewFiles;
	const avgTimePerFile = totalFiles > 0 ? (totalProcessingTime / totalFiles).toFixed(1) : "0.0";
	const avgTimePerPage = totalPages > 0 ? (totalProcessingTime / totalPages).toFixed(1) : "0.0";
	const successRate = totalFiles > 0 ? (((totalFiles - manualReviewFiles) / totalFiles) * 100).toFixed(1) : "100.0";

	return {
		recordsCount: records.length,
		totalFiles,
		completedFiles,
		manualReviewFiles,
		totalProcessingTime: totalProcessingTime.toFixed(1),
		maxProcessingTime: maxProcessingTime.toFixed(1),
		avgTimePerFile,
		avgTimePerPage,
		totalPages,
		categoryCounts,
		tier1Count,
		tier2Count,
		tier3Count,
		earlyStopCount,
		successRate,
		infoCount,
		warnCount,
		errorCount
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

	const catEntries = Object.entries(stats.categoryCounts).sort((a, b) => b[1] - a[1]);
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

	body.innerHTML = `
		<!-- KPI Summary Grid -->
		<div class="analytics-grid-2col">
			<div class="analytics-kpi-card analytics-kpi-card-indigo">
				<div class="analytics-kpi-title-indigo">📄 Files Processed</div>
				<div class="analytics-kpi-val">${stats.totalFiles}</div>
				<div class="analytics-kpi-sub">${stats.completedFiles} Auto / ${stats.manualReviewFiles} Review</div>
			</div>

			<div class="analytics-kpi-card analytics-kpi-card-emerald">
				<div class="analytics-kpi-title-emerald">🎯 Automation Rate</div>
				<div class="analytics-kpi-val">${stats.successRate}%</div>
				<div class="analytics-kpi-sub">without manual review</div>
			</div>

			<div class="analytics-kpi-card analytics-kpi-card-blue">
				<div class="analytics-kpi-title-blue">⚡ Avg Time / File</div>
				<div class="analytics-kpi-val">${stats.avgTimePerFile}s</div>
				<div class="analytics-kpi-sub">Max: ${stats.maxProcessingTime}s</div>
			</div>

			<div class="analytics-kpi-card analytics-kpi-card-purple">
				<div class="analytics-kpi-title-purple">⏱️ Avg Time / Page</div>
				<div class="analytics-kpi-val">${stats.avgTimePerPage}s</div>
				<div class="analytics-kpi-sub">Total ${stats.totalPages} pages</div>
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
			<div class="inspector-field-group">
				<div class="inspector-field-row">
					<span class="inspector-field-label">🟢 Tier 1 (Direct Consensus)</span>
					<span class="inspector-field-value stat-tier1-val">${stats.earlyStopCount > 0 ? stats.earlyStopCount : stats.tier1Count} Multi-Pass</span>
				</div>
				<div class="inspector-field-row">
					<span class="inspector-field-label">🟡 Tier 2 (High-Res Verification)</span>
					<span class="inspector-field-value stat-tier2-val">${stats.tier2Count}</span>
				</div>
				<div class="inspector-field-row">
					<span class="inspector-field-label">🔴 Tier 3 (Tiebreaker Audit)</span>
					<span class="inspector-field-value stat-tier3-val">${stats.tier3Count}</span>
				</div>
			</div>
		</div>

		<!-- Log Health Card -->
		<div class="inspector-card">
			<h4 class="inspector-section-title">
				<span>📡</span> Stream Health & Log Level
			</h4>
			<div class="health-badge-row">
				<span class="badge badge-health-info">INFO: ${stats.infoCount}</span>
				<span class="badge badge-health-warn">WARN: ${stats.warnCount}</span>
				<span class="badge badge-health-err">ERR: ${stats.errorCount}</span>
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
	} catch (_) {}
	state.logRecords = [];
	state.lastLogId = 0;
	renderLogLines();
}
