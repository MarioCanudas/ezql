from backend.services.agent.nodes.base import SpecialistNodeBase
from backend.services.agent.tools import visualization_tools
from backend.prompts.visualization import VISUALIZATION_SYSTEM_PROMPT


class VisualizationNode(SpecialistNodeBase):
    step = "visualization"
    system_prompt = VISUALIZATION_SYSTEM_PROMPT
    tools = visualization_tools
