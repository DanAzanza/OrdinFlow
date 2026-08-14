"""OrdinFlow — Skills Execution & Automation Engine.

Fully domain- and data-agnostic system for executing desktop/RDP automations.
This module re-exports components from `core.skills` for backward compatibility.
"""

from core.skills.executor import SkillExecutor
from core.skills.grounder import SoMGrounder
from core.skills.manager import SkillManager
from core.skills.queue import (
    SkillQueueManager,
    get_skill_queue_manager,
)
from core.skills.shield import (
    _emergency_unblock,
    input_shield,
    set_block_input,
)

__all__ = [
    "set_block_input",
    "_emergency_unblock",
    "input_shield",
    "SoMGrounder",
    "SkillManager",
    "SkillExecutor",
    "SkillQueueManager",
    "get_skill_queue_manager",
]
