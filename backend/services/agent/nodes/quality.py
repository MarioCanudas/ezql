from backend.prompts.quality_agent import QUALITY_AGENT_SYSTEM_PROMPT
from backend.services.agent.nodes.base import SpecialistNodeBase
from backend.services.agent.tools import quality_tools


class QualityNode(SpecialistNodeBase):
    step = "quality"
    system_prompt = QUALITY_AGENT_SYSTEM_PROMPT
    tools = quality_tools
