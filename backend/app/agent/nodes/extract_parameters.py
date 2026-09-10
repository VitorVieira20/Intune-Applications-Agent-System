import json
import logging

from langchain_ollama import ChatOllama

from app.agent.prompts import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_TEMPLATE
from app.agent.state import AgentState
from app.config import settings

logger = logging.getLogger("intune_agent.node.extract_parameters")

_llm = ChatOllama(
    base_url=settings.ollama_base_url,
    model=settings.ollama_model,
    format="json",
    temperature=0.0,
)


def _safe_json_parse(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                pass
        raise


def extract_parameters_node(state: AgentState) -> AgentState:
    previous_errors = "\n".join(state.get("errors", [])) or "None"

    user_prompt = EXTRACTION_USER_TEMPLATE.format(
        app_name=state["app_name"],
        search_context=state.get("search_context", "")[:6000],
        previous_errors=previous_errors,
    )

    messages = [
        ("system", EXTRACTION_SYSTEM_PROMPT),
        ("human", user_prompt),
    ]

    updated = dict(state)

    try:
        response = _llm.invoke(messages)
        parsed = _safe_json_parse(response.content)

        updated["install_cmd"] = parsed.get("install_cmd", "")
        updated["uninstall_cmd"] = parsed.get("uninstall_cmd", "")
        updated["detection_rule"] = parsed.get("detection_rule", {}) or {}
        updated["installer_download_url"] = parsed.get("installer_download_url") or None
        updated["errors"] = []
    except Exception as exc:  # noqa: BLE001
        logger.exception("extract_parameters falhou")
        updated["errors"] = state.get("errors", []) + [f"Falha ao invocar/parsear LLM: {exc}"]
        updated["is_valid"] = False

    updated["correction_loops"] = state.get("correction_loops", 0) + 1
    return updated
