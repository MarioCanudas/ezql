from backend.services.agent.nodes.base import SpecialistNodeBase
from backend.prompts import SQL_AGENT_SYSTEM_PROMPT
from backend.services.agent.tools import sql_tools


class SqlNode(SpecialistNodeBase):
    step = "sql"
    system_prompt = SQL_AGENT_SYSTEM_PROMPT
    tools = sql_tools
