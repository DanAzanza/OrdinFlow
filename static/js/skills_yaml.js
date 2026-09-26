/* ═══════════════════════════════════════════════════════════
   SKILL VIEW MODE & YAML EXPERT MODE MODULE
   ═══════════════════════════════════════════════════════════ */

let currentSkillViewMode = "visual";

function switchSkillView(mode) {
	currentSkillViewMode = mode;
	const visualSection = document.getElementById("skillVisualSection");
	const yamlSection = document.getElementById("skillYamlSection");
	const btnVisual = document.getElementById("btnSkillViewVisual");
	const btnYaml = document.getElementById("btnSkillViewYaml");

	if (mode === "yaml") {
		if (visualSection) visualSection.style.display = "none";
		if (yamlSection) yamlSection.style.display = "block";
		if (btnVisual) btnVisual.classList.remove("active");
		if (btnYaml) btnYaml.classList.add("active");
		syncYamlFromVisual();
	} else {
		if (visualSection) visualSection.style.display = "block";
		if (yamlSection) yamlSection.style.display = "none";
		if (btnVisual) btnVisual.classList.add("active");
		if (btnYaml) btnYaml.classList.remove("active");
	}
}

async function syncYamlFromVisual() {
	const textarea = document.getElementById("skillYamlEditorTextarea");
	if (!textarea) return;
	const payload = getSkillPayloadFromForm();
	try {
		const res = await api("/api/skills/to_yaml", {
			method: "POST",
			body: JSON.stringify({ skill: payload }),
		});
		if (res && res.yaml) {
			textarea.value = res.yaml;
		}
	} catch (e) {
		console.error("Error generating YAML:", e);
	}
}

async function applyYamlToVisualAndSave() {
	const textarea = document.getElementById("skillYamlEditorTextarea");
	if (!textarea) return;
	const yamlStr = textarea.value.trim();
	if (!yamlStr) {
		toast("YAML content cannot be empty", "error");
		return;
	}

	try {
		const res = await api("/api/skills/from_yaml", {
			method: "POST",
			body: JSON.stringify({ yaml: yamlStr }),
		});

		if (res && res.skill) {
			const skillObj = res.skill;
			await api("/api/skills", {
				method: "POST",
				body: JSON.stringify(skillObj),
			});

			selectedSkillId = skillObj.id;
			isNewSkillCreation = false;
			await loadSkills(true);
			await selectSkill(skillObj.id);
			switchSkillView("visual");
			toast(`✨ YAML for skill '${skillObj.name || skillObj.id}' saved successfully!`, "success");
		}
	} catch (e) {
		toast("Error applying YAML: " + e.message, "error");
	}
}
