import logging

from langgraph.types import interrupt

from app.agent.state import AgentState

logger = logging.getLogger("intune_agent.node.resolve_installer")


def resolve_installer_node(state: AgentState) -> AgentState:
    updated = dict(state)

    if state.get("in_store"):
        logger.info("resolve_installer: app Winget, será empacotado um wrapper script (sem instalador).")
        updated["installer_url_or_path"] = None
        updated["installer_is_wrapper_script"] = True
        return updated

    if state.get("installer_url_or_path"):
        updated["installer_is_wrapper_script"] = False
        return updated

    discovered_url = state.get("installer_download_url")
    if discovered_url:
        logger.info("resolve_installer: URL descoberta automaticamente: %s", discovered_url)
        updated["installer_url_or_path"] = discovered_url
        updated["installer_is_wrapper_script"] = False
        return updated

    payload = {
        "type": "installer_missing",
        "message": (
            f"Não foi possível localizar automaticamente o instalador de '{state['app_name']}'. "
            "Indica um URL de download direto ou um caminho local acessível dentro do contentor."
        ),
        "app_name": state["app_name"],
    }
    human_response = interrupt(payload)
    provided = (human_response or {}).get("installer_url_or_path", "").strip()

    updated["installer_url_or_path"] = provided or None
    updated["installer_is_wrapper_script"] = False
    return updated


def route_after_resolve_installer(state: AgentState) -> str:
    return "package_app"
