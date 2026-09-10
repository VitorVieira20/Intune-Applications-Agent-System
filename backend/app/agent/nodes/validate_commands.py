import logging
import re

from app.agent.state import AgentState

logger = logging.getLogger("intune_agent.node.validate_commands")

SILENT_FLAGS = [
    r"/qn\b", r"/quiet\b", r"/s\b", r"-s\b", r"/silent\b", r"/verysilent\b",
    r"/q\b", r"--silent\b", r"--quiet\b", r"/norestart\b",
]

SYSTEM_CONTEXT_FLAGS = [
    r"allusers\s*=\s*1", r"/allusers\b", r"machine", r"/m\b",
]

MSI_UNINSTALL_PATTERN = re.compile(r"msiexec.*?/x", re.IGNORECASE)


def _matches_any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def validate_commands_node(state: AgentState) -> AgentState:
    install_cmd = (state.get("install_cmd") or "").strip()
    uninstall_cmd = (state.get("uninstall_cmd") or "").strip()
    detection_rule = state.get("detection_rule") or {}

    errors: list[str] = []

    if not install_cmd:
        errors.append("install_cmd está vazio.")
    else:
        if not _matches_any(SILENT_FLAGS, install_cmd):
            errors.append(
                f"install_cmd não contém nenhuma flag silenciosa reconhecida "
                f"(/qn, /quiet, /S, /VERYSILENT, etc.): '{install_cmd}'"
            )
        is_msi = install_cmd.lower().startswith("msiexec") or ".msi" in install_cmd.lower()
        if is_msi and "allusers" not in install_cmd.lower():
            errors.append("Instalador MSI detetado mas falta ALLUSERS=1 para contexto de Sistema.")
        if not is_msi and not _matches_any(SYSTEM_CONTEXT_FLAGS, install_cmd):
            errors.append(
                "install_cmd não indica claramente instalação para todo o sistema "
                "(machine-wide / ALLUSERS). Verificar flag específica do instalador."
            )

    if not uninstall_cmd:
        errors.append("uninstall_cmd está vazio.")
    elif not _matches_any(SILENT_FLAGS, uninstall_cmd) and not MSI_UNINSTALL_PATTERN.search(uninstall_cmd):
        errors.append(f"uninstall_cmd não parece ser silencioso: '{uninstall_cmd}'")

    if not detection_rule or not detection_rule.get("type"):
        errors.append("detection_rule ausente ou sem 'type' definido (msi/file/registry).")
    elif detection_rule.get("type") == "msi" and not detection_rule.get("product_code"):
        errors.append("detection_rule do tipo 'msi' sem 'product_code'.")
    elif detection_rule.get("type") in ("file", "registry") and not detection_rule.get("path_or_key"):
        errors.append(f"detection_rule do tipo '{detection_rule.get('type')}' sem 'path_or_key'.")

    is_valid = len(errors) == 0
    logger.info("validate_commands: is_valid=%s erros=%s", is_valid, errors)

    updated = dict(state)
    updated["is_valid"] = is_valid
    updated["errors"] = errors
    return updated


def route_after_validate(state: AgentState) -> str:
    from app.config import settings

    if state.get("is_valid"):
        return "package_app"
    if state.get("correction_loops", 0) >= settings.max_correction_loops:
        return "end"
    return "extract_parameters"
