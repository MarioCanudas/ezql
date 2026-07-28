from backend.services.agent.nodes.base import SpecialistNodeBase
from backend.services.agent.tools import statistics_tools
from backend.prompts.statistics_agent import STATISTICS_AGENT_SYSTEM_PROMPT
from langchain_core.messages import SystemMessage


class StatisticsNode(SpecialistNodeBase):
    step = "statistics"
    system_prompt = STATISTICS_AGENT_SYSTEM_PROMPT
    tools = statistics_tools

    def context_messages(self, state, active_step):
        grants = state.get("statistics_grants", []) if isinstance(state, dict) else state.statistics_grants
        grant = next((item for item in grants if item.step_id == active_step.id), None)
        if grant is None:
            return []
        return [SystemMessage(content=(
            "[DATASET_AUTORIZADO]\n"
            f"grant_id: {grant.grant_id}\nstep_id: {grant.step_id}\n"
            f"modo: {grant.mode}; filas: {grant.row_count}; columnas: {grant.columns}\n"
            "Puedes usar run_statistics_python únicamente con estos grant_id y step_id."
        ))]
