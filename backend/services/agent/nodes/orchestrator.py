from __future__ import annotations

import json
import logging
import re
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
from backend.services.agent.metadata import (
    safe_template,
    sanitize_generated_block,
    state_candidates,
    state_metadata,
)
from backend.services.agent.nodes.base import NodeBase, sanitize_tool_calls_in_messages
from backend.services.agent.state import (
    AgentConfiguration,
    AgentState,
    AgentTask,
    ExecutionPlan,
    InvestigationDecision,
    PlanStep,
    PresentationCandidate,
    ResponseSelection,
    TaskResult,
)

MAX_REPLANS = 2
logger = logging.getLogger(__name__)
VISUALIZATION_KEYWORDS = ("gráfica", "grafica", "chart", "graficar", "visualizar", "visualización", "visualizacion", "dashboard")
STATISTICS_KEYWORDS = (
    "anomal", "atípic", "outlier", "tendencia", "evolución", "crecimiento",
    "caída", "caida", "promedio", "media", "mediana", "percentil", "desviación",
    "distribución", "variabilidad", "nulo", "faltante", "calidad de datos",
    "ranking", "participación", "participacion", "segmento", "compar", "kpi",
)


def _messages(state: AgentState, config: RunnableConfig) -> list[Any]:
    try:
        configured = config.get("configurable", {})
        input_messages = configured.get("input_messages", [])
        if input_messages:
            return sanitize_tool_calls_in_messages(list(input_messages))
    except Exception:
        pass
    return sanitize_tool_calls_in_messages(list(getattr(state, "messages", [])))


def _normalize_tasks(
    tasks: list[AgentTask], *, round_number: int, completed: list[AgentTask]
) -> list[AgentTask]:
    completed_keys = {
        (task.specialist, task.objective.strip().casefold()) for task in completed
    }
    normalized: list[AgentTask] = []
    for index, raw_task in enumerate(tasks, start=1):
        task = raw_task if isinstance(raw_task, AgentTask) else AgentTask.model_validate(raw_task)
        objective = task.objective.strip()
        key = (task.specialist, objective.casefold())
        if not objective or key in completed_keys:
            continue
        policy = task.policy.model_copy()
        if task.specialist == "statistics" and task.requires_grant is False:
            task = task.model_copy(update={"requires_grant": True})
        normalized.append(
            task.model_copy(
                update={
                    "id": task.id or f"round-{round_number}-{index}-{task.specialist}",
                    "objective": objective,
                    "policy": policy,
                    "status": "pending",
                }
            )
        )
        completed_keys.add(key)
    return normalized


def validate_task_plan(tasks: list[AgentTask]) -> list[AgentTask]:
    """Apply deterministic graph and resource constraints to an LLM plan."""

    unique: dict[str, AgentTask] = {}
    for task in tasks[:8]:
        if task.id and task.id not in unique:
            policy = task.policy.model_copy()
            if policy.resource == "statistics_sandbox":
                policy = policy.model_copy(update={"max_concurrency": 1})
            else:
                policy = policy.model_copy(update={
                    "max_concurrency": min(policy.max_concurrency, 2),
                })
            if not policy.parallelizable:
                policy = policy.model_copy(update={"max_concurrency": 1})
            unique[task.id] = task.model_copy(update={
                "policy": policy,
                "requires_grant": task.requires_grant or task.specialist == "statistics",
            })

    # A visualization is a presentation consumer, never an evidence producer.
    # Repair a plan that tries to render before any SQL/statistics/quality task
    # has produced a verified artifact.
    evidence_tasks = [
        task for task in unique.values()
        if task.specialist in {"sql", "statistics", "quality"}
    ]
    for task in list(unique.values()):
        if task.specialist != "visualization":
            continue
        evidence_dependency = next(
            (dependency for dependency in task.depends_on
             if unique.get(dependency) in evidence_tasks),
            None,
        )
        if evidence_dependency is None:
            if not evidence_tasks:
                evidence_id = f"{task.id}-evidence"
                while evidence_id in unique:
                    evidence_id += "-sql"
                evidence_task = AgentTask(
                    id=evidence_id,
                    specialist="sql",
                    objective="Obtener evidencia de solo lectura para respaldar la visualización.",
                )
                unique[evidence_id] = evidence_task
                evidence_tasks.append(evidence_task)
            evidence_dependency = evidence_tasks[0].id
            unique[task.id] = task.model_copy(
                update={"depends_on": [*task.depends_on, evidence_dependency]}
            )

    valid_ids = set(unique)
    sanitized: list[AgentTask] = []
    for task in unique.values():
        dependencies = [
            dependency
            for dependency in task.depends_on
            if dependency in valid_ids and dependency != task.id
        ]
        sanitized.append(task.model_copy(update={"depends_on": dependencies}))

    by_id = {task.id: task for task in sanitized}
    visiting: set[str] = set()
    visited: set[str] = set()
    cyclic: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            cyclic.add(task_id)
            return
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in by_id[task_id].depends_on:
            if dependency in by_id:
                visit(dependency)
                if dependency in cyclic:
                    cyclic.add(task_id)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in by_id:
        visit(task_id)
    return [task for task in sanitized if task.id not in cyclic]


def _legacy_pending_tasks(state: AgentState) -> list[AgentTask]:
    return [
        AgentTask(
            id=step.id or f"legacy-{index}-{step.specialist}",
            specialist=step.specialist,
            objective=step.objective,
            requires_grant=step.specialist == "statistics",
        )
        for index, step in enumerate(getattr(state, "pending_steps", []), start=1)
    ]


def _apply_task_results(state: AgentState) -> list[AgentTask]:
    tasks = [task.model_copy() for task in state.tasks]
    by_id = {task.id: task for task in tasks}
    latest: dict[str, TaskResult] = {}
    for raw_result in state.task_results:
        result = raw_result if isinstance(raw_result, TaskResult) else TaskResult.model_validate(raw_result)
        latest[result.task_id] = result
    for task_id, result in latest.items():
        task = by_id.get(task_id)
        if task is None:
            continue
        if result.status == "completed":
            by_id[task_id] = task.model_copy(update={"status": "completed"})
        else:
            next_attempts = task.attempts + 1
            if next_attempts < task.max_attempts:
                by_id[task_id] = task.model_copy(
                    update={"status": "ready", "attempts": next_attempts}
                )
            else:
                by_id[task_id] = task.model_copy(
                    update={"status": "failed", "attempts": next_attempts}
                )
    return [by_id[task.id] for task in tasks]


def _evidence(state: AgentState) -> str:
    payload = {
        "artifacts": [artifact.model_dump(exclude={"debug_metadata", "data"}) for artifact in state.artifacts],
        "contributions": [contribution.model_dump() for contribution in state.contributions],
        "tasks": [task.model_dump() for task in state.tasks],
        "metadata": {key: value.model_dump() for key, value in state_metadata(state.artifacts).items()},
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _candidate_evidence(
    candidates: list[PresentationCandidate], metadata: dict[str, Any]
) -> str:
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


def _invoke_structured(
    llm: Any,
    schema: Any,
    messages: list[Any],
    config: dict[str, Any],
    label: str,
) -> Any:
    """Invoke structured output with a provider-compatible fallback."""

    try:
        return llm.with_structured_output(schema, method="json_schema").invoke(
            messages, config=config
        )
    except Exception as exc:
        logger.warning(
            "Structured %s output with json_schema failed; retrying json_mode (%s)",
            label,
            type(exc).__name__,
        )
        return llm.with_structured_output(schema, method="json_mode").invoke(
            messages, config=config
        )


def _fallback_selection(
    state: AgentState, candidates: list[PresentationCandidate]
) -> ResponseSelection:
    narrative = next(
        (
            contribution.summary.strip()
            for contribution in reversed(state.contributions)
            if contribution.summary.strip()
        ),
        "",
    )
    if not narrative:
        narrative = next(
            (artifact.summary.strip() for artifact in reversed(state.artifacts) if artifact.summary.strip()),
            "",
        )
    return ResponseSelection(
        summary="Encontré resultados verificados para tu consulta.",
        narrative=narrative,
        candidate_ids=[candidate.id for candidate in candidates],
    )


def _references(text: str) -> set[str]:
    return set(re.findall(r"\{\{meta\.([A-Za-z0-9_.-]+)\}\}", text))


def _selected_presentation(
    candidates: list[PresentationCandidate], selection: ResponseSelection, metadata: dict[str, Any]
) -> tuple[list[UIBlock], dict[str, Any]]:
    by_id = {candidate.id: candidate for candidate in candidates}
    selected: list[PresentationCandidate] = []
    seen: set[str] = set()
    for candidate_id in selection.candidate_ids:
        candidate = by_id.get(candidate_id)
        if candidate and candidate_id not in seen:
            selected.append(candidate)
            seen.add(candidate_id)
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
    for artifact in state.artifacts:
        for candidate in artifact.presentation_candidates:
            append_once(candidate.block.model_dump())
        # Compatibility fallback for old in-memory artifacts created by tests.
        if isinstance(artifact.data, dict) and isinstance(artifact.data.get("chart"), dict):
            try:
                append_once(ChartBlock.model_validate(artifact.data["chart"]).model_dump())
            except ValidationError:
                pass
    return blocks


class OrchestratorNode(NodeBase):
    """Plans a DAG, reviews evidence, and composes one safe response."""

    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        try:
            agent_config = AgentConfiguration.model_validate(config.get("configurable", {}))
        except ValidationError as exc:
            raise ValueError(f"Invalid configuration in config['configurable']: {exc}") from exc

        agent_config.database_service.get_database(
            agent_config.runtime_db_id, user_id=agent_config.user_id
        )
        llm = agent_config.llm_service._build_client()
        messages = _messages(state, config)
        current_tasks = state.tasks or _legacy_pending_tasks(state)

        if not state.planning_started:
            try:
                plan = _invoke_structured(
                    llm,
                    ExecutionPlan,
                    [SystemMessage(content=ORCHESTRATOR_PLANNER_PROMPT)] + messages,
                    {"configurable": config.get("configurable", {})},
                    "planner",
                )
                plan = ExecutionPlan.model_validate(plan)
            except Exception as exc:
                logger.exception("Planner failed; using the safe SQL fallback: %s", exc)
                plan = ExecutionPlan(
                    tasks=[AgentTask(
                        id="round-1-1-sql",
                        specialist="sql",
                        objective="Descubrir los datos necesarios.",
                    )]
                )
            tasks = validate_task_plan(_normalize_tasks(plan.tasks, round_number=1, completed=[]))
            if not tasks:
                tasks = [
                    AgentTask(
                        id="round-1-1-sql",
                        specialist="sql",
                        objective="Descubrir los datos necesarios.",
                    )
                ]
            return {
                "planning_started": True,
                "plan_round": 1,
                "tasks": tasks,
                "pending_steps": [PlanStep(**task.model_dump()) for task in tasks],
            }

        if current_tasks and not state.tasks:
            current_tasks = _apply_task_results(state.model_copy(update={"tasks": current_tasks}))
        elif state.tasks and state.task_results:
            current_tasks = _apply_task_results(state)

        if current_tasks and any(task.status in {"pending", "ready"} for task in current_tasks):
            return {"tasks": current_tasks}

        reviewable = bool(current_tasks) or (not state.tasks and not state.task_results)
        if state.replan_count < MAX_REPLANS and reviewable:
            review_messages = [
                SystemMessage(content=ORCHESTRATOR_REVIEW_PROMPT),
                *messages,
                HumanMessage(content="[EVIDENCIA_ACUMULADA]\n" + _evidence(state)),
            ]
            try:
                decision = _invoke_structured(
                    llm,
                    InvestigationDecision,
                    review_messages,
                    {"configurable": config.get("configurable", {})},
                    "review",
                )
                decision = InvestigationDecision.model_validate(decision)
            except Exception as exc:
                logger.exception("Evidence review failed; finalizing safe evidence: %s", exc)
                decision = InvestigationDecision(action="finalize", reason="La evidencia es suficiente.")
            if decision.action == "continue":
                next_round = state.plan_round + 1
                next_tasks = validate_task_plan(_normalize_tasks(
                    decision.tasks,
                    round_number=next_round,
                    completed=current_tasks,
                ))
                if next_tasks:
                    return {
                        "replan_count": state.replan_count + 1,
                        "plan_round": next_round,
                        "tasks": next_tasks,
                        "pending_steps": [PlanStep(**task.model_dump()) for task in next_tasks],
                    }

        metadata = state_metadata(state.artifacts)
        candidates = state_candidates(state.artifacts)
        if candidates:
            selection_messages = [
                SystemMessage(content=ORCHESTRATOR_SELECTION_PROMPT),
                *messages,
                HumanMessage(
                    content="[CATALOGO_DE_EVIDENCIA]\n" + _candidate_evidence(candidates, metadata)
                ),
            ]
            selection_failed = False
            try:
                selection = _invoke_structured(
                    llm,
                    ResponseSelection,
                    selection_messages,
                    {"configurable": config.get("configurable", {})},
                    "selection",
                )
                selection = ResponseSelection.model_validate(selection)
            except Exception as exc:
                selection_failed = True
                logger.exception("Evidence selection failed; using verified fallback: %s", exc)
                selection = _fallback_selection(state, candidates)
            if not selection.summary.strip() or selection.summary.strip() == "Resultados verificados disponibles.":
                selection.summary = _fallback_selection(state, candidates).summary
            if selection_failed and not selection.narrative.strip():
                selection.narrative = _fallback_selection(state, candidates).narrative
            blocks, selected_metadata = _selected_presentation(candidates, selection, metadata)
            summary = safe_template(selection.summary, selected_metadata)
            narrative = safe_template(selection.narrative, selected_metadata)
            final_blocks: list[UIBlock] = []
            if narrative.strip():
                final_blocks.append(MarkdownBlock(content=narrative))
            elif not any(block.type == "markdown" for block in blocks):
                final_blocks.append(MarkdownBlock(content=summary))
            final_blocks.extend(blocks)
            validated = AgentResponse.model_validate(
                {"summary": summary, "blocks": final_blocks, "metadata": selected_metadata}
            )
            return {"response": validated.model_dump(), "messages": [AIMessage(content=summary)]}

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
        return {"response": validated.model_dump(), "messages": [AIMessage(content=validated.summary)]}


# Deprecated helpers kept for callers that imported the previous keyword guards.
# They are no longer used by the planner or graph routing.
def _enforce_visualization_step(steps: list[PlanStep], messages: list[Any]) -> list[PlanStep]:
    text = ""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            text = str(message.content).casefold()
            break
    if not any(keyword in text for keyword in VISUALIZATION_KEYWORDS):
        return steps
    enriched = list(steps)
    specialists = {step.specialist for step in enriched}
    if "sql" not in specialists:
        enriched.insert(0, PlanStep(specialist="sql", objective="Preparar y validar los datos para la visualización solicitada."))
    if "visualization" not in specialists:
        enriched.append(PlanStep(specialist="visualization", objective="Crear la gráfica solicitada con los datos validados."))
    return enriched


def _enforce_statistics_step(steps: list[PlanStep], messages: list[Any]) -> list[PlanStep]:
    text = ""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            text = str(message.content).casefold()
            break
    if not any(keyword in text for keyword in STATISTICS_KEYWORDS):
        return steps
    enriched = list(steps)
    specialists = {step.specialist for step in enriched}
    if "sql" not in specialists:
        enriched.insert(0, PlanStep(specialist="sql", objective="Identificar y validar los datos necesarios para el análisis estadístico."))
    if "statistics" not in specialists:
        index = next(
            (index for index, step in enumerate(enriched) if step.specialist == "visualization"),
            len(enriched),
        )
        enriched.insert(index, PlanStep(specialist="statistics", objective="Calcular las métricas y hallazgos estadísticos solicitados con evidencia verificable."))
    return enriched
