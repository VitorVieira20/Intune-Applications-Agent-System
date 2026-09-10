import logging

from app.agent.state import AgentState
from app.services.winget_client import search_winget_candidates

logger = logging.getLogger("intune_agent.node.check_store")


def check_store_node(state: AgentState) -> AgentState:
    app_name = state["app_name"]
    result = search_winget_candidates(app_name)

    updated = dict(state)

    if result.exact_match:
        pkg = result.exact_match
        logger.info("check_store: correspondência exata '%s' -> %s", app_name, pkg.package_id)
        updated["in_store"] = True
        updated["winget_candidates"] = []
        updated["search_context"] = (
            f"A aplicação '{app_name}' corresponde exatamente ao pacote Winget '{pkg.name}' "
            f"(id: {pkg.package_id}). O Winget suporta instalação silenciosa e machine-wide via:\n"
            f"Install: winget install --id {pkg.package_id} --silent --accept-package-agreements "
            f"--accept-source-agreements --scope machine\n"
            f"Uninstall: winget uninstall --id {pkg.package_id} --silent\n"
            f"Para detection rule, usar o registry key de Uninstall do Windows "
            f"(HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{pkg.package_id})."
        )
    else:
        logger.info(
            "check_store: sem correspondência exata para '%s' (%d candidatos relevantes)",
            app_name, len(result.candidates),
        )
        updated["in_store"] = False
        updated["winget_candidates"] = [
            {"package_id": c.package_id, "name": c.name, "confidence": c.confidence}
            for c in result.candidates
        ]

    return updated


def route_after_check_store(state: AgentState) -> str:
    return "extract_parameters" if state.get("in_store") else "human_review_store"
