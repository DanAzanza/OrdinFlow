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
		toast("⏹️ Aufnahme beendet und Skill gespeichert.", "success");

		if (typeof loadSkills === "function") {
			await loadSkills();
		}
		return res;
	} catch (e) {
		console.error("Error stopping live recording:", e);
		toast("Fehler beim Beenden der Aufnahme: " + e.message, "error");
	}
}
