import logging

from langchain_community.tools import DuckDuckGoSearchRun

from app.agent.state import AgentState

logger = logging.getLogger("intune_agent.node.search_web")

_search_tool = DuckDuckGoSearchRun()


def search_web_node(state: AgentState) -> AgentState:
    app_name = state["app_name"]
    query = f'"{app_name}" silent install switch command line system context registry uninstall'

    try:
        result = _search_tool.invoke(query)
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_web falhou para '%s': %s", app_name, exc)
        result = ""

    context = result or "Nenhum resultado de pesquisa disponível."

    updated = dict(state)
    existing = state.get("search_context", "")
    updated["search_context"] = f"{existing}\n\n{context}".strip()
    return updated
