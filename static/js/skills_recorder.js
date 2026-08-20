/* ═══════════════════════════════════════════════════════════
   SKILL LIVE RECORDER CONTROLLER & FLOATING BAR
   ═══════════════════════════════════════════════════════════ */

let recorderPollInterval = null;
let recorderStartTime = null;

function updateRecorderFloatingWidget(status) {
	const widget = document.getElementById("recorderFloatingWidget");
	const timerEl = document.getElementById("recorderTimer");
	const stepBadgeEl = document.getElementById("recorderStepBadge");
	const lastActionEl = document.getElementById("recorderLastAction");

	if (!widget) return;

	if (status && status.is_recording) {
		widget.style.display = "flex";
		if (stepBadgeEl) {
			stepBadgeEl.textContent = `${status.step_count || 0} steps`;
		}
		if (lastActionEl && status.last_action) {
			lastActionEl.textContent = status.last_action;
		}

		if (recorderStartTime && timerEl) {
			const elapsedSec = Math.floor((Date.now() - recorderStartTime) / 1000);
			const mins = String(Math.floor(elapsedSec / 60)).padStart(2, "0");
			const secs = String(elapsedSec % 60).padStart(2, "0");
			timerEl.textContent = `${mins}:${secs}`;
		}
	} else {
		widget.style.display = "none";
		if (recorderPollInterval) {
			clearInterval(recorderPollInterval);
			recorderPollInterval = null;
		}
		recorderStartTime = null;
	}
}

async function startLiveRecording(skillName = "New Recorded Skill") {
	try {
		const res = await api("/api/skills/recorder/start", {
			method: "POST",
			body: JSON.stringify({ skill_name: skillName }),
		});

		recorderStartTime = Date.now();
		updateRecorderFloatingWidget({ is_recording: true, step_count: 0 });

		if (!recorderPollInterval) {
			recorderPollInterval = setInterval(async () => {
				try {
					const status = await api("/api/skills/recorder/status");
					updateRecorderFloatingWidget(status);
				} catch (err) {
					console.error("Error polling recorder status:", err);
				}
			}, 1000);
		}

		toast("🔴 Live-Aufnahme gestartet! Aktionen werden erfasst.", "success");
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
			const recordedSteps = res.skill.steps;

			// If the user was in the skill editor, inject recorded steps into active editing session
			if (currentEditingSkill) {
				// Update target window if recorder detected a specific window
				if (
					res.skill.target_window &&
					(!currentEditingSkill.target_window || currentEditingSkill.target_window === "Remote Desktop*")
				) {
					currentEditingSkill.target_window = res.skill.target_window;
					const winInput = document.getElementById("editorSkillTargetWindow");
					if (winInput) {
						winInput.value = res.skill.target_window;
					}
				}

				// If currently there is only 1 placeholder step, replace it with the recorded sequence
				const isPlaceholderOnly =
					currentEditingSteps.length <= 1 &&
					(!currentEditingSteps[0] ||
						currentEditingSteps[0].action_type === "FOCUS_WINDOW" ||
						!currentEditingSteps[0].description);

				if (isPlaceholderOnly) {
					currentEditingSteps = recordedSteps;
				} else {
					currentEditingSteps.push(...recordedSteps);
				}

				// Re-index all steps cleanly
				currentEditingSteps.forEach((s, idx) => {
					s.id = `step_${idx + 1}`;
				});

				// Auto-expand the first step
				if (currentEditingSteps.length > 0 && typeof stepExpandedMap !== "undefined") {
					stepExpandedMap[currentEditingSteps[0].id] = true;
				}

				if (typeof renderEditorSteps === "function") {
					renderEditorSteps();
				}

				toast(
					`⏹️ Aufnahme beendet! ${recordedSteps.length} Schritte wurden in den Workflow übernommen.`,
					"success",
				);
			} else {
				// Fallback if no skill was selected: save as new skill and load it
				const saveRes = await api("/api/skills", {
					method: "POST",
					body: JSON.stringify(res.skill),
				});
				if (saveRes && saveRes.skill_id) {
					selectedSkillId = saveRes.skill_id;
				}
				if (typeof loadSkills === "function") {
					await loadSkills(true);
				}
				toast(`⏹️ Aufnahme beendet! Skill '${res.skill.name}' gespeichert.`, "success");
			}
		} else {
			toast("⏹️ Aufnahme beendet (keine Schritte erfasst).", "info");
		}

		return res;
	} catch (e) {
		console.error("Error stopping live recording:", e);
		toast("Fehler beim Beenden der Aufnahme: " + e.message, "error");
	}
}
