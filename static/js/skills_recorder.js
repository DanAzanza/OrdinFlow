/* ═══════════════════════════════════════════════════════════
   SKILL LIVE RECORDER & AI SYNTHESIS COPILOT MODULE
   ═══════════════════════════════════════════════════════════ */

let recorderPollInterval = null;
let lastRecordedSteps = [];
let currentSynthesisData = null;

function updateRecorderFloatingWidget(statusData) {
	const widget = document.getElementById("recorderFloatingWidget");
	if (!widget) return;

	if (statusData && statusData.is_recording) {
		widget.style.display = "flex";
		const timerEl = document.getElementById("recorderTimer");
		if (timerEl && statusData.duration_seconds !== undefined) {
			const m = Math.floor(statusData.duration_seconds / 60);
			const s = Math.floor(statusData.duration_seconds % 60);
			timerEl.textContent = `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
		}
		const badgeEl = document.getElementById("recorderStepBadge");
		if (badgeEl) {
			badgeEl.textContent = `${statusData.step_count || 0} Schritte`;
		}
		const actionEl = document.getElementById("recorderLastAction");
		if (actionEl && statusData.last_action) {
			actionEl.textContent = statusData.last_action;
		}
	} else {
		widget.style.display = "none";
		if (recorderPollInterval) {
			clearInterval(recorderPollInterval);
			recorderPollInterval = null;
		}
	}
}

async function startLiveRecording(skillName = "Neuer Workflow") {
	try {
		const res = await api("/api/skills/recorder/start", {
			method: "POST",
			body: JSON.stringify({ skill_name: skillName }),
		});

		updateRecorderFloatingWidget({
			is_recording: true,
			duration_seconds: 0,
			step_count: 0,
			last_action: "Live-Aufnahme läuft... Zeige der KI den Ablauf am Bildschirm.",
		});

		if (!recorderPollInterval) {
			recorderPollInterval = setInterval(async () => {
				try {
					const status = await api("/api/skills/recorder/status");
					if (status && status.is_recording) {
						updateRecorderFloatingWidget(status);
					} else {
						updateRecorderFloatingWidget({ is_recording: false });
					}
				} catch {
					// Silent catch during periodic polling
				}
			}, 1000);
		}

		toast("🔴 Live-Aufnahme gestartet! Führe den Ablauf am Bildschirm vor.", "success");
		return res;
	} catch (e) {
		console.error("Error starting live recording:", e);
		toast("Fehler beim Starten der Aufnahme: " + e.message, "error");
	}
}

async function stopLiveRecording() {
	try {
		const res = await api("/api/skills/recorder/stop", {
			method: "POST",
		});

		updateRecorderFloatingWidget({ is_recording: false });

		if (res && res.skill && Array.isArray(res.skill.steps) && res.skill.steps.length > 0) {
			lastRecordedSteps = res.skill.steps;
			await openAiSynthesisModal(lastRecordedSteps);
		} else {
			toast("Aufnahme beendet, es wurden keine Aktionen erfasst.", "info");
		}
	} catch (e) {
		console.error("Error stopping live recording:", e);
		toast("Fehler beim Beenden der Aufnahme: " + e.message, "error");
	}
}

async function openAiSynthesisModal(rawSteps = []) {
	const modal = document.getElementById("aiSkillSynthesisModal");
	if (!modal) return;

	lastRecordedSteps = rawSteps || [];
	modal.classList.add("active");

	// Populate document types dropdown
	const docSelect = document.getElementById("aiSynthesisDocTypeSelect");
	if (docSelect) {
		let knownTypes = ["*"];
		if (state.config && state.config.document_types) {
			knownTypes = ["*", ...Object.keys(state.config.document_types)];
		}
		docSelect.innerHTML = knownTypes
			.map((t) => `<option value="${escapeHtml(t)}">${t === "*" ? "⭐ * (Alle Dokumentarten)" : escapeHtml(t)}</option>`)
			.join("");
	}

	// Show loading state in synthesis summary
	const summaryText = document.getElementById("aiSynthesisSummaryText");
	if (summaryText) {
		summaryText.innerHTML = `
			<div style="display: flex; align-items: center; gap: 8px;">
				<div class="spinner-border spinner-border-sm text-primary" role="status" style="width: 14px; height: 14px; border-width: 2px;"></div>
				<span>Die lokale KI analysiert deinen Ablauf (${rawSteps.length} Aktionen) und erkennt Aufgaben & Variablen...</span>
			</div>
		`;
	}

	const tasksPreview = document.getElementById("aiSynthesisTasksPreview");
	if (tasksPreview) tasksPreview.innerHTML = "";

	const varsSection = document.getElementById("aiSynthesisVariablesSection");
	if (varsSection) varsSection.style.display = "none";

	// Call AI synthesis endpoint
	try {
		const res = await api("/api/skills/synthesize", {
			method: "POST",
			body: JSON.stringify({
				steps: rawSteps,
				user_instruction: "",
			}),
		});

		if (res && res.synthesis) {
			renderAiSynthesisResult(res.synthesis);
		}
	} catch (e) {
		console.error("Error during AI synthesis:", e);
		if (summaryText) {
			summaryText.textContent = "Synthese fehlgeschlagen. Der Workflow wird im Standardformat geladen.";
		}
	}
}

function renderAiSynthesisResult(synthesis) {
	currentSynthesisData = synthesis;

	// Summary text
	const summaryText = document.getElementById("aiSynthesisSummaryText");
	if (summaryText) {
		summaryText.textContent = synthesis.description || "Ablauf erfolgreich analysiert und in Aufgaben strukturiert.";
	}

	// Skill Name
	const nameInput = document.getElementById("aiSynthesisSkillName");
	if (nameInput) {
		nameInput.value = synthesis.name || "Neuer Workflow";
	}

	// Doc Type Select
	const docSelect = document.getElementById("aiSynthesisDocTypeSelect");
	if (docSelect && Array.isArray(synthesis.suggested_document_types) && synthesis.suggested_document_types.length > 0) {
		docSelect.value = synthesis.suggested_document_types[0] || "*";
	}

	// Detected Variables
	const varsSection = document.getElementById("aiSynthesisVariablesSection");
	const varsList = document.getElementById("aiSynthesisVariablesList");
	if (varsSection && varsList) {
		if (Array.isArray(synthesis.detected_variables) && synthesis.detected_variables.length > 0) {
			varsSection.style.display = "block";
			varsList.innerHTML = synthesis.detected_variables
				.map(
					(v) => `
				<div class="synthesis-var-card">
					<span class="synthesis-var-orig" title="${escapeHtml(v.original || "")}">${escapeHtml(v.original || "")}</span>
					<span class="synthesis-var-arrow">➔</span>
					<span class="synthesis-var-target">${escapeHtml(v.variable || "")}</span>
				</div>
			`,
				)
				.join("");
		} else {
			varsSection.style.display = "none";
		}
	}

	// Tasks Preview
	const tasksPreview = document.getElementById("aiSynthesisTasksPreview");
	const taskCountBadge = document.getElementById("aiSynthesisTaskCount");
	if (tasksPreview) {
		const tasks = synthesis.tasks || [];
		if (taskCountBadge) taskCountBadge.textContent = `${tasks.length} Tasks`;

		tasksPreview.innerHTML = tasks
			.map(
				(t, idx) => `
			<div class="synthesis-task-preview-item">
				<div class="synthesis-task-title">
					<span>📦 Aufgabe ${idx + 1}:</span>
					<span>${escapeHtml(t.title || "")}</span>
				</div>
				<div>
					${(t.actions || [])
						.map((a) => {
							const style = typeof getActionBadgeStyle === "function" ? getActionBadgeStyle(a.action_type) : { label: a.action_type, icon: "⚙️" };
							return `
							<span class="synthesis-action-pill">
								<span>${style.icon || "🎯"}</span>
								<span>${escapeHtml(a.description || style.label)}</span>
							</span>
						`;
						})
						.join("")}
				</div>
			</div>
		`,
			)
			.join("");
	}
}

async function reSynthesizeSkillWithPrompt() {
	const input = document.getElementById("aiSynthesisRefineInput");
	const instruction = (input?.value || "").trim();
	if (!instruction) return;

	const btn = document.getElementById("aiSynthesisRefineBtn");
	if (btn) btn.disabled = true;

	const summaryText = document.getElementById("aiSynthesisSummaryText");
	if (summaryText) {
		summaryText.innerHTML = `
			<div style="display: flex; align-items: center; gap: 8px;">
				<div class="spinner-border spinner-border-sm text-primary" role="status" style="width: 14px; height: 14px; border-width: 2px;"></div>
				<span>Die KI passt den Workflow anhand deiner Anweisung an...</span>
			</div>
		`;
	}

	try {
		const res = await api("/api/skills/synthesize", {
			method: "POST",
			body: JSON.stringify({
				steps: lastRecordedSteps,
				user_instruction: instruction,
			}),
		});

		if (res && res.synthesis) {
			renderAiSynthesisResult(res.synthesis);
			toast("✨ Workflow wurde von der KI angepasst!", "success");
		}
	} catch (e) {
		console.error("Error refining synthesis:", e);
		toast("Fehler bei der KI-Anpassung: " + e.message, "error");
	} finally {
		if (btn) btn.disabled = false;
	}
}

function applyAiSynthesisToEditor() {
	if (!currentSynthesisData) {
		closeAiSynthesisModal();
		return;
	}

	// 1. Skill Name & ID
	const name = (document.getElementById("aiSynthesisSkillName")?.value || "").trim() || currentSynthesisData.name || "Neuer Workflow";
	const nameEl = document.getElementById("editorSkillName");
	if (nameEl) nameEl.value = name;

	const newSkillId = (typeof slugifySkillName === "function" ? slugifySkillName(name) : "custom_skill") || "new_recorded_skill";
	const idEl = document.getElementById("editorSkillId");
	if (idEl) idEl.value = newSkillId;

	// 2. Set Skill Type to Export
	const typeEl = document.getElementById("editorSkillType");
	if (typeEl) {
		typeEl.value = "export";
		if (typeof onSkillTypeChange === "function") {
			onSkillTypeChange("export");
		}
	}

	// 3. Doc Types
	const selectedDocType = document.getElementById("aiSynthesisDocTypeSelect")?.value || "*";
	const docTypesEl = document.getElementById("editorSkillDocTypes");
	if (docTypesEl) docTypesEl.value = selectedDocType;

	// 4. Description
	const descEl = document.getElementById("editorSkillDesc");
	if (descEl) descEl.value = currentSynthesisData.description || "";

	// 5. Tasks & Actions
	if (Array.isArray(currentSynthesisData.tasks) && currentSynthesisData.tasks.length > 0) {
		currentEditingTasks = currentSynthesisData.tasks;
	}

	isNewSkillCreation = true;
	currentEditingSkill = {
		id: newSkillId,
		name: name,
		type: "export",
		description: currentSynthesisData.description || "",
		document_types: [selectedDocType],
		tasks: currentEditingTasks,
	};

	closeAiSynthesisModal();

	if (typeof renderEditorSteps === "function") {
		renderEditorSteps();
	}

	toast(`✨ KI-Workflow '${name}' mit ${currentEditingTasks.length} Aufgaben in den Editor geladen!`, "success");
}

function closeAiSynthesisModal() {
	const modal = document.getElementById("aiSkillSynthesisModal");
	if (modal) modal.classList.remove("active");
}
