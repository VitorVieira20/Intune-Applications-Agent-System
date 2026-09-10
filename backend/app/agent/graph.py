import logging

from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.graph import END, StateGraph

from app.agent.nodes.check_store import check_store_node, route_after_check_store
from app.agent.nodes.extract_parameters import extract_parameters_node
from app.agent.nodes.human_review import human_review_store_node, route_after_human_review
from app.agent.nodes.package_app import package_app_node, route_after_package
from app.agent.nodes.resolve_installer import resolve_installer_node, route_after_resolve_installer
from app.agent.nodes.search_web import search_web_node
from app.agent.nodes.validate_commands import route_after_validate, validate_commands_node
from app.agent.state import AgentState
from app.config import settings

logger = logging.getLogger("intune_agent.graph")


async def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("check_store", check_store_node)
    graph.add_node("human_review_store", human_review_store_node)
    graph.add_node("search_web", search_web_node)
    graph.add_node("extract_parameters", extract_parameters_node)
    graph.add_node("validate_commands", validate_commands_node)
    graph.add_node("resolve_installer", resolve_installer_node)
    graph.add_node("package_app", package_app_node)

    graph.set_entry_point("check_store")

    graph.add_conditional_edges(
        "check_store",
        route_after_check_store,
        {"extract_parameters": "extract_parameters", "human_review_store": "human_review_store"},
    )

    graph.add_conditional_edges(
        "human_review_store",
        route_after_human_review,
        {
            "extract_parameters": "extract_parameters",
            "check_store": "check_store",
            "search_web": "search_web",
        },
    )

    graph.add_edge("search_web", "extract_parameters")
    graph.add_edge("extract_parameters", "validate_commands")

    graph.add_conditional_edges(
        "validate_commands",
        route_after_validate,
        {
            "package_app": "resolve_installer",
            "extract_parameters": "extract_parameters",
            "end": END,
        },
    )

    graph.add_conditional_edges(
        "resolve_installer", route_after_resolve_installer, {"package_app": "package_app"}
    )

    graph.add_conditional_edges("package_app", route_after_package, {"end": END})

    checkpointer = AsyncRedisSaver(redis_url=settings.redis_url)
    await checkpointer.asetup()

    compiled = graph.compile(checkpointer=checkpointer)
    logger.info("StateGraph compilado com checkpointer Redis assíncrono e nós de human-in-the-loop.")
    return compiled
