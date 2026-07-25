from backend.services.agent.nodes.base import SpecialistNodeBase
from backend.services.agent.tools import statistics_tools
from backend.prompts.statistics_agent import STATISTICS_AGENT_SYSTEM_PROMPT


class StatisticsNode(SpecialistNodeBase):
    step = "statistics"
    system_prompt = STATISTICS_AGENT_SYSTEM_PROMPT
    tools = statistics_tools
