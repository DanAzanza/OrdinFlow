"""OrdinFlow — Skills Subsystem Package.

Provides modularized desktop and RDP automation components:
- input shielding
- Set-of-Mark (SoM) visual grounding
- skill YAML storage management
- step execution engine
- sequential background execution queue
"""

from core.skills.executor import SkillExecutor
from core.skills.grounder import SoMGrounder
from core.skills.manager import SkillManager
from core.skills.queue import SkillQueueManager, get_skill_queue_manager
from core.skills.shield import input_shield, set_block_input

__all__ = [
    "input_shield",
    "set_block_input",
    "SoMGrounder",
    "SkillManager",
    "SkillExecutor",
    "SkillQueueManager",
    "get_skill_queue_manager",
]
