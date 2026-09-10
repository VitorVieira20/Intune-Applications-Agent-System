import logging

from langgraph.types import interrupt

from app.agent.state import AgentState

logger = logging.getLogger("intune_agent.node.human_review")


def human_review_store_node(state: AgentState) -> AgentState:
    app_name = state["app_name"]
    candidates = state.get("winget_candidates", [])

    if candidates:
        payload = {
            "type": "winget_multiple_matches",
            "message": (
                f"Foram encontrados {len(candidates)} resultado(s) no Winget para "
                f"'{app_name}'. Escolhe o correto, ou pede para seguir para pesquisa web."
            ),
            "app_name": app_name,
            "candidates": candidates,
        }
    else:
        payload = {
            "type": "winget_not_found",
            "message": (
                f"Não foi encontrado nenhum resultado relevante no Winget para '{app_name}'. "
                "Podes enviar um nome diferente para tentar de novo, ou seguir para pesquisa web."
            ),
            "app_name": app_name,
            "candidates": [],
        }

    human_response = interrupt(payload)

    updated = dict(state)
    action = (human_response or {}).get("action")

    if action == "select_package":
        package_id = human_response.get("package_id")
        matched = next((c for c in candidates if c["package_id"] == package_id), None)
        matched_name = matched["name"] if matched else package_id

        updated["in_store"] = True
        updated["human_review_route"] = "extract_parameters"
        updated["search_context"] = (
            f"O utilizador confirmou manualmente o pacote Winget '{matched_name}' "
            f"(id: {package_id}) para a aplicação '{app_name}'. O Winget suporta instalação "
            f"silenciosa e machine-wide via:\n"
            f"Install: winget install --id {package_id} --silent --accept-package-agreements "
            f"--accept-source-agreements --scope machine\n"
            f"Uninstall: winget uninstall --id {package_id} --silent\n"
        )

    elif action == "provide_new_name":
        new_name = (human_response.get("new_app_name") or "").strip()
        if new_name:
            logger.info("human_review: utilizador forneceu novo nome '%s' -> '%s'", app_name, new_name)
            updated["app_name"] = new_name
            updated["human_review_route"] = "check_store"
        else:
            updated["in_store"] = False
            updated["human_review_route"] = "search_web"

    elif action == "proceed_web_search":
        updated["in_store"] = False
        updated["human_review_route"] = "search_web"

    else:
        logger.warning("human_review: ação desconhecida/omissa (%s); fallback para pesquisa web", action)
        updated["in_store"] = False
        updated["human_review_route"] = "search_web"

    return updated


def route_after_human_review(state: AgentState) -> str:
    return state.get("human_review_route", "search_web")
