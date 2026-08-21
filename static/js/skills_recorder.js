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
			badgeEl.textContent = `${statusData.step_count || 0} actions`;
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

async function startLiveRecording(skillName = "New Skill") {
	try {
		const res = await api("/api/skills/recorder/start", {
			method: "POST",
			body: JSON.stringify({ skill_name: skillName }),
		});

		updateRecorderFloatingWidget({
			is_recording: true,
			duration_seconds: 0,
			step_count: 0,
			last_action: "Live recording in progress... Demonstrate the action sequence on screen.",
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

		toast("🔴 Live recording started! Demonstrate the action sequence on screen.", "success");
		return res;
	} catch (e) {
		console.error("Error starting live recording:", e);
		toast("Error starting live recording: " + e.message, "error");
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
			toast("Recording stopped, no actions were captured.", "info");
		}
	} catch (e) {
		console.error("Error stopping live recording:", e);
		toast("Error stopping recording: " + e.message, "error");
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
			.map((t) => `<option value="${escapeHtml(t)}">${t === "*" ? "⭐ * (All Document Types)" : escapeHtml(t)}</option>`)
			.join("");
	}

	// Show loading state in synthesis summary
	const summaryText = document.getElementById("aiSynthesisSummaryText");
	if (summaryText) {
		summaryText.innerHTML = `
			<div class="skills-spinner-box">
				<div class="spinner-border spinner-border-sm text-primary skills-spinner-sm" role="status"></div>
				<span>Local AI is analyzing your recording (${rawSteps.length} actions) and structuring tasks & variables...</span>
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
		} else {
			renderAiSynthesisResult({
				name: (document.getElementById("editorSkillName")?.value || "").trim() || "New Skill",
				description: `Automated skill with ${rawSteps.length} actions.`,
				suggested_document_types: ["*"],
				detected_variables: [],
				tasks: [
					{
						id: "task_1",
						title: "Task 1: Execute Application Flow",
						actions: rawSteps,
					},
				],
			});
		}
	} catch (e) {
		console.error("Error during AI synthesis:", e);
		renderAiSynthesisResult({
			name: (document.getElementById("editorSkillName")?.value || "").trim() || "New Skill",
			description: `Automated skill (${rawSteps.length} actions).`,
			suggested_document_types: ["*"],
			detected_variables: [],
			tasks: [
				{
					id: "task_1",
					title: "Task 1: Execute Application Flow",
					actions: rawSteps,
				},
			],
		});
	}
}

function renderAiSynthesisResult(synthesis) {
	currentSynthesisData = synthesis;

	// Summary text
	const summaryText = document.getElementById("aiSynthesisSummaryText");
	if (summaryText) {
		summaryText.textContent = synthesis.description || "Skill structured successfully into tasks & actions.";
	}

	// Skill Name
	const nameInput = document.getElementById("aiSynthesisSkillName");
	if (nameInput) {
		nameInput.value = synthesis.name || "New Skill";
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
					<span>📦 Task ${idx + 1}:</span>
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
			<div class="skills-spinner-box">
				<div class="spinner-border spinner-border-sm text-primary skills-spinner-sm" role="status"></div>
				<span>AI is adjusting the skill based on your instructions...</span>
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
			toast("✨ Skill updated by AI!", "success");
		}
	} catch (e) {
		console.error("Error refining synthesis:", e);
		toast("Error refining skill with AI: " + e.message, "error");
	} finally {
		if (btn) btn.disabled = false;
	}
}

function applyAiSynthesisToEditor() {
	if (!currentSynthesisData) {
		closeAiSynthesisModal();
		return;
	}

	// 1. Skill Name
	const name = (document.getElementById("aiSynthesisSkillName")?.value || "").trim() || currentSynthesisData.name || "New Skill";
	const nameEl = document.getElementById("editorSkillName");
	if (nameEl) nameEl.value = name;

	// 2. Set Skill Type to Export
	const typeEl = document.getElementById("editorSkillType");
	if (typeEl) {
		typeEl.value = "export";
		if (typeof onSkillTypeChange === "function") {
			onSkillTypeChange("export");
		}
	}

	// 3. Doc Types
	const selectedDocType = document.getElementById("aiSynthesisDocTypeSelect")?.value || "";
	if (typeof renderSkillDocTypesTags === "function") {
		currentSkillDocTypes = selectedDocType && selectedDocType !== "*" ? [selectedDocType] : [];
		renderSkillDocTypesTags();
	}

	// 4. Description
	const descEl = document.getElementById("editorSkillDesc");
	if (descEl) descEl.value = currentSynthesisData.description || "";

	// 5. Tasks & Actions
	if (Array.isArray(currentSynthesisData.tasks) && currentSynthesisData.tasks.length > 0) {
		currentEditingTasks = currentSynthesisData.tasks;
	}

	isNewSkillCreation = true;
	currentEditingSkill = {
		id: name,
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

	toast(`✨ AI Skill '${name}' with ${currentEditingTasks.length} task(s) loaded into editor!`, "success");
}

function closeAiSynthesisModal() {
	const modal = document.getElementById("aiSkillSynthesisModal");
	if (modal) modal.classList.remove("active");
}
