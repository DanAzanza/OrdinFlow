/* ═══════════════════════════════════════════════════════════
   CONVERSATIONAL AI SKILL COPILOT CHAT
   ═══════════════════════════════════════════════════════════ */

const skillCopilotChatMap = {};

function getSkillCopilotHistory(skillId) {
	const id = skillId || selectedSkillId || "temp";
	if (!skillCopilotChatMap[id]) {
		skillCopilotChatMap[id] = [
			{
				role: "assistant",
				content: "Hello! I am your AI Copilot for this export skill. Simply describe in natural language how the workflow should look or what changes to make (e.g. add clicks, adjust delays, or change target window titles).",
				time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
			},
		];
	}
	return skillCopilotChatMap[id];
}

function initSkillCopilotChat(skillId) {
	const feed = document.getElementById("skillCopilotChatFeed");
	if (!feed) return;
	const history = getSkillCopilotHistory(skillId);
	renderSkillChatFeed(history);
}

function clearSkillCopilotChat() {
	const id = selectedSkillId || "temp";
	skillCopilotChatMap[id] = [
		{
			role: "assistant",
			content: "Chat history reset. How can I assist you with this skill?",
			time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
		},
	];
	renderSkillChatFeed(skillCopilotChatMap[id]);
}

function renderSkillChatFeed(history) {
	const feed = document.getElementById("skillCopilotChatFeed");
	if (!feed) return;
	feed.innerHTML = history
		.map((msg) => {
			const isUser = msg.role === "user";
			const timeClass = isUser ? "chat-timestamp-user" : "chat-timestamp-assistant";
			return `
			<div class="skill-chat-msg ${isUser ? "user" : "assistant"}">
				<div class="skill-chat-msg-icon">${isUser ? "👤" : "✨"}</div>
				<div class="skill-chat-msg-bubble">
					<div>${escapeHtml(msg.content)}</div>
					${
						msg.time
							? `<div class="${timeClass}">${escapeHtml(msg.time)}</div>`
							: ""
					}
				</div>
			</div>
		`;
		})
		.join("");
	feed.scrollTop = feed.scrollHeight;
}

async function sendSkillCopilotMessage() {
	const input = document.getElementById("skillCopilotChatInput");
	const promptText = (input?.value || "").trim();
	if (!promptText) return;

	const id = selectedSkillId || "temp";
	const history = getSkillCopilotHistory(id);
	const nowTime = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

	// Append user message
	history.push({
		role: "user",
		content: promptText,
		time: nowTime,
	});
	if (input) input.value = "";
	renderSkillChatFeed(history);

	// Append typing indicator
	const feed = document.getElementById("skillCopilotChatFeed");
	const typingId = "skillChatTypingIndicator";
	if (feed) {
		const typingEl = document.createElement("div");
		typingEl.id = typingId;
		typingEl.className = "skill-chat-msg assistant";
		typingEl.innerHTML = `
			<div class="skill-chat-msg-icon">✨</div>
			<div class="skill-chat-typing">
				<div class="skill-chat-dot"></div>
				<div class="skill-chat-dot"></div>
				<div class="skill-chat-dot"></div>
			</div>
		`;
		feed.appendChild(typingEl);
		feed.scrollTop = feed.scrollHeight;
	}

	const sendBtn = document.getElementById("btnSkillCopilotSend");
	if (sendBtn) sendBtn.disabled = true;

	const currentPayload = typeof getSkillPayloadFromForm === "function" ? getSkillPayloadFromForm() : {};

	try {
		const res = await api("/api/skills/ai_modify", {
			method: "POST",
			body: JSON.stringify({
				skill: currentPayload,
				instruction: promptText,
				history: history.slice(0, -1),
			}),
		});

		// Remove typing indicator
		document.getElementById(typingId)?.remove();

		if (res && res.skill) {
			const updated = res.skill;
			if (updated.name) {
				setSkillFormVal("name", updated.name);
				onSkillNameInput(updated.name);
			}
			if (updated.description) {
				setSkillFormVal("description", updated.description);
			}
			if (updated.target_window) {
				const winEl = document.getElementById("editorSkillTargetWindow");
				if (winEl) winEl.value = updated.target_window;
			}
			if (updated.document_types !== undefined) {
				currentSkillDocTypes = Array.isArray(updated.document_types)
					? updated.document_types.filter((t) => t && t !== "*")
					: typeof updated.document_types === "string"
						? updated.document_types.split(",").map((s) => s.trim()).filter((s) => s && s !== "*")
						: [];
				renderSkillDocTypesTags();
			}
			if (Array.isArray(updated.tasks) && updated.tasks.length > 0) {
				currentEditingTasks = updated.tasks;
			} else if (Array.isArray(updated.steps) && updated.steps.length > 0) {
				currentEditingTasks = [
					{
						id: "task_1",
						title: "Task 1: Execute Application Flow",
						actions: updated.steps,
					},
				];
			}

			if (currentEditingSkill) {
				Object.assign(currentEditingSkill, updated);
				currentEditingSkill.tasks = currentEditingTasks;
			}

			renderEditorSteps();
			if (typeof syncYamlFromVisual === "function") {
				syncYamlFromVisual();
			}

			// Append assistant reply
			const replyText = res.reply || "I have updated the skill according to your instruction.";
			history.push({
				role: "assistant",
				content: replyText,
				time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
			});
			renderSkillChatFeed(history);
			toast("✨ Skill updated by AI Copilot!", "success");
		} else {
			history.push({
				role: "assistant",
				content: "Sorry, I was unable to apply this modification.",
				time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
			});
			renderSkillChatFeed(history);
		}
	} catch (e) {
		document.getElementById(typingId)?.remove();
		console.error("Skill copilot chat error:", e);
		history.push({
			role: "assistant",
			content: "Failed to apply changes: " + e.message,
			time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
		});
		renderSkillChatFeed(history);
		toast("Error: " + e.message, "error");
	} finally {
		if (sendBtn) sendBtn.disabled = false;
		input?.focus();
	}
}
