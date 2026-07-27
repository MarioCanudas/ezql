import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from backend.models.blocks import AgentResponse, ChartBlock, MarkdownBlock, UIBlock
from backend.prompts.orchestrator import (
    ORCHESTRATOR_FORMATTER_PROMPT,
    ORCHESTRATOR_PLANNER_PROMPT,
    ORCHESTRATOR_REVIEW_PROMPT,
    ORCHESTRATOR_SELECTION_PROMPT,
)
from backend.services.agent.agent_chat import LLMGenerationError
from backend.services.agent.nodes.base import NodeBase, sanitize_tool_calls_in_messages
from backend.services.agent.metadata import (
    safe_template,
    sanitize_generated_block,
    state_candidates,
    state_metadata,
)
from backend.services.agent.state import (
    AgentConfiguration,
    AgentState,
    ExecutionPlan,
    InvestigationDecision,
    PlanStep,
    PresentationCandidate,
    ResponseSelection,
)

MAX_REPLANS = 2
VISUALIZATION_KEYWORDS = ("gráfica", "grafica", "chart", "graficar", "visualizar", "visualización", "visualizacion", "dashboard")
STATISTICS_KEYWORDS = (
    "anomal", "atípic", "outlier", "tendencia", "evolución", "crecimiento",
    "caída", "caida", "promedio", "media", "mediana", "percentil", "desviación",
    "distribución", "variabilidad", "nulo", "faltante", "calidad de datos",
    "ranking", "participación", "participacion", "segmento", "compar", "kpi",
)


def _normalize_steps(
    steps: list[PlanStep], *, round_number: int, completed: list[PlanStep]
) -> list[PlanStep]:
    completed_objectives = {
        (step.specialist, step.objective.strip().casefold()) for step in completed
    }
    normalized: list[PlanStep] = []
    for index, step in enumerate(steps, start=1):
        objective = step.objective.strip()
        key = (step.specialist, objective.casefold())
        if not objective or key in completed_objectives:
            continue
        normalized.append(
            PlanStep(
                id=f"round-{round_number}-{index}-{step.specialist}",
                specialist=step.specialist,
                objective=objective,
            )
        )
        completed_objectives.add(key)
    return normalized


def _latest_user_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content).casefold()
    return ""


def _enforce_visualization_step(steps: list[PlanStep], messages: list[Any]) -> list[PlanStep]:
    """Guarantee a visual request reaches the visualization specialist."""
    if not any(keyword in _latest_user_text(messages) for keyword in VISUALIZATION_KEYWORDS):
        return steps

    specialists = {step.specialist for step in steps}
    enriched = list(steps)
    if "sql" not in specialists:
        enriched.insert(0, PlanStep(specialist="sql", objective="Preparar y validar los datos para la visualización solicitada."))
    if "visualization" not in specialists:
        enriched.append(PlanStep(specialist="visualization", objective="Crear la gráfica solicitada con los datos validados."))
    return enriched


def _requires_statistics(messages: list[Any]) -> bool:
    user_text = _latest_user_text(messages)
    return any(keyword in user_text for keyword in STATISTICS_KEYWORDS)


def _enforce_statistics_step(steps: list[PlanStep], messages: list[Any]) -> list[PlanStep]:
    """Ensure business-analysis requests receive verified statistical evidence.

    The planner still supplies the objective, while this guard prevents a SQL-only
    answer when the user's wording explicitly requests an analytical conclusion.
    """
    if not _requires_statistics(messages):
        return steps

    enriched = list(steps)
    specialists = {step.specialist for step in enriched}
    if "sql" not in specialists:
        enriched.insert(0, PlanStep(specialist="sql", objective="Identificar y validar los datos necesarios para el análisis estadístico."))
    if "statistics" not in specialists:
        statistics_step = PlanStep(
            specialist="statistics",
            objective="Calcular las métricas y hallazgos estadísticos solicitados con evidencia verificable.",
        )
        visualization_index = next(
            (index for index, step in enumerate(enriched) if step.specialist == "visualization"),
            len(enriched),
        )
        enriched.insert(visualization_index, statistics_step)
    return enriched


def _evidence(state: AgentState) -> str:
    payload = {
        "artifacts": [artifact.model_dump(exclude={"debug_metadata"}) for artifact in state.artifacts],
        "contributions": [contribution.model_dump() for contribution in state.contributions],
        "completed_steps": [step.model_dump() for step in state.completed_steps],
        "metadata": {key: value.model_dump() for key, value in state_metadata(state.artifacts).items()},
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _candidate_evidence(
    candidates: list[PresentationCandidate], metadata: dict[str, Any]
) -> str:
    """Expose only selection-relevant evidence to the final editor."""
    payload = {
        "facts": {key: value.model_dump() for key, value in metadata.items()},
        "candidates": [
            {
                "id": candidate.id,
                "tool_call_id": candidate.tool_call_id,
                "block_type": candidate.block.type,
                "label": getattr(candidate.block, "label", None),
                "title": getattr(candidate.block, "title", None),
                "fact_keys": candidate.fact_keys,
            }
            for candidate in candidates
        ],
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _references(text: str) -> set[str]:
    import re

    return set(re.findall(r"\{\{meta\.([A-Za-z0-9_.-]+)\}\}", text))


def _selected_presentation(
    candidates: list[PresentationCandidate], selection: ResponseSelection, metadata: dict[str, Any]
) -> tuple[list[UIBlock], dict[str, Any]]:
    """Validate editor choices and keep a useful verified fallback on bad IDs."""
    by_id = {candidate.id: candidate for candidate in candidates}
    selected: list[PresentationCandidate] = []
    seen: set[str] = set()
    for candidate_id in selection.candidate_ids:
        candidate = by_id.get(candidate_id)
        if candidate and candidate_id not in seen:
            selected.append(candidate)
            seen.add(candidate_id)

    # An empty or invalid selection must not erase verified specialist output.
    if not selected and candidates:
        selected = candidates

    selected_keys = {
        key for candidate in selected for key in candidate.fact_keys if key in metadata
    }
    selected_keys.update(
        key for key in _references(selection.summary + "\n" + selection.narrative) if key in metadata
    )
    return [candidate.block for candidate in selected], {
        key: metadata[key] for key in selected_keys
    }


def _contribution_blocks(state: AgentState) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    seen: set[str] = set()

    def append_once(block: dict[str, Any]) -> None:
        fingerprint = json.dumps(block, ensure_ascii=False, sort_keys=True, default=str)
        if fingerprint not in seen:
            seen.add(fingerprint)
            blocks.append(block)

    for contribution in state.contributions:
        for block in contribution.blocks:
            append_once(block.model_dump())

    # Una visualización que la herramienta ya validó no puede perderse porque
    # el modelo olvidó proponerla al construir su contribución. Los artefactos
    # son la fuente de verdad para los datos que Streamlit puede renderizar.
    for artifact in state.artifacts:
        if not artifact.ok or not isinstance(artifact.data, dict):
            continue
        chart = artifact.data.get("chart")
        if not isinstance(chart, dict):
            continue
        try:
            append_once(ChartBlock.model_validate(chart).model_dump())
        except ValidationError:
            # Un artefacto inválido no debe romper la respuesta completa.
            continue
    return blocks


class OrchestratorNode(NodeBase):
    """Plans, reviews evidence, and assembles a single composable response."""

    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        try:
            agent_config = AgentConfiguration.model_validate(config.get("configurable", {}))
        except ValidationError as exc:
            raise ValueError(f"Invalid configuration in config['configurable']: {exc}") from exc

        agent_config.database_service.get_database(
            agent_config.runtime_db_id, user_id=agent_config.user_id
        )
        llm = agent_config.llm_service._build_client()
        messages = sanitize_tool_calls_in_messages(list(state.messages))

        if not state.planning_started:
            try:
                plan = llm.with_structured_output(ExecutionPlan, method="json_schema").invoke(
                    [SystemMessage(content=ORCHESTRATOR_PLANNER_PROMPT)] + messages,
                    config={"configurable": config.get("configurable", {})},
                )
                plan = ExecutionPlan.model_validate(plan)
            except Exception:
                plan = ExecutionPlan(
                    steps=[PlanStep(specialist="sql", objective="Descubrir los datos necesarios.")]
                )
            steps = _enforce_statistics_step(
                _enforce_visualization_step(plan.steps, messages), messages
            )
            return {
                "planning_started": True,
                "plan_round": 1,
                "pending_steps": _normalize_steps(steps, round_number=1, completed=[]),
            }

        if state.pending_steps:
            return {}

        if state.replan_count < MAX_REPLANS:
            review_messages = [
                SystemMessage(content=ORCHESTRATOR_REVIEW_PROMPT),
                *messages,
                HumanMessage(content="[EVIDENCIA_ACUMULADA]\n" + _evidence(state)),
            ]
            try:
                decision = llm.with_structured_output(
                    InvestigationDecision, method="json_schema"
                ).invoke(
                    review_messages,
                    config={"configurable": config.get("configurable", {})},
                )
                decision = InvestigationDecision.model_validate(decision)
            except Exception:
                decision = InvestigationDecision(action="finalize", reason="No se requiere más investigación.")

            if decision.action == "continue":
                next_round = state.plan_round + 1
                next_steps = _normalize_steps(
                    decision.steps, round_number=next_round, completed=state.completed_steps
                )
                if next_steps:
                    return {
                        "replan_count": state.replan_count + 1,
                        "plan_round": next_round,
                        "pending_steps": next_steps,
                    }

        metadata = state_metadata(state.artifacts)
        candidates = state_candidates(state.artifacts)

        if candidates:
            selection_messages = [
                SystemMessage(content=ORCHESTRATOR_SELECTION_PROMPT),
                *messages,
                HumanMessage(
                    content="[CATALOGO_DE_EVIDENCIA]\n"
                    + _candidate_evidence(candidates, metadata)
                ),
            ]
            try:
                selection = llm.with_structured_output(
                    ResponseSelection, method="json_schema"
                ).invoke(
                    selection_messages,
                    config={"configurable": config.get("configurable", {})},
                )
                selection = ResponseSelection.model_validate(selection)
            except Exception:
                selection = ResponseSelection(
                    summary="Resultados verificados disponibles.", candidate_ids=[]
                )

            blocks, selected_metadata = _selected_presentation(
                candidates, selection, metadata
            )
            summary = safe_template(selection.summary, selected_metadata)
            narrative = safe_template(selection.narrative, selected_metadata)
            final_blocks: list[UIBlock] = []
            if narrative.strip():
                final_blocks.append(MarkdownBlock(content=narrative))
            elif not any(block.type == "markdown" for block in blocks):
                final_blocks.append(MarkdownBlock(content=summary))
            final_blocks.extend(blocks)
            validated = AgentResponse.model_validate(
                {
                    "summary": summary,
                    "blocks": final_blocks,
                    "metadata": selected_metadata,
                }
            )
            return {
                "response": validated.model_dump(),
                "messages": [AIMessage(content=validated.summary)],
            }

        formatter_messages = [
            SystemMessage(content=ORCHESTRATOR_FORMATTER_PROMPT),
            *messages,
            HumanMessage(content="[EVIDENCIA_Y_PIEZAS]\n" + _evidence(state)),
        ]
        try:
            response = llm.with_structured_output(AgentResponse, method="json_schema").invoke(
                formatter_messages,
                config={"configurable": config.get("configurable", {})},
            )
        except Exception:
            try:
                response = llm.with_structured_output(AgentResponse, method="json_mode").invoke(
                    formatter_messages,
                    config={"configurable": config.get("configurable", {})},
                )
            except Exception as exc:
                raise LLMGenerationError("No se pudo preparar una respuesta para el usuario.") from exc

        response = AgentResponse.model_validate(response)
        response.metadata = metadata
        response.summary = safe_template(response.summary, metadata)
        blocks = _contribution_blocks(state)
        if blocks:
            if not any(block.get("type") == "markdown" for block in blocks):
                blocks.insert(0, MarkdownBlock(content=response.summary).model_dump())
            response = AgentResponse.model_validate(
                {"summary": response.summary, "blocks": blocks, "metadata": metadata}
            )
        elif not response.blocks:
            response.blocks = [MarkdownBlock(content=response.summary)]
        else:
            response.blocks = [sanitize_generated_block(block, metadata) for block in response.blocks]
        validated = AgentResponse.model_validate(response)
        return {
            "response": validated.model_dump(),
            "messages": [AIMessage(content=validated.summary)],
        }
