import logging
from pathlib import Path

from app.agent.state import AgentState
from app.config import settings
from app.services.installer_fetcher import InstallerFetchError, fetch_installer
from app.services.intunewin_packager import PackagingError, package_application

logger = logging.getLogger("intune_agent.node.package_app")

WINGET_WRAPPER_TEMPLATE = """# Script gerado automaticamente pelo Intune Silent Install Agent
# Aplicacao: {app_name} (via Winget)
$ErrorActionPreference = "Stop"
{install_cmd}
exit $LASTEXITCODE
"""


def package_app_node(state: AgentState) -> AgentState:
    app_name = state["app_name"]
    updated = dict(state)
    source_dir = Path(settings.storage_downloads_dir) / app_name
    output_dir = Path(settings.storage_packages_dir)

    try:
        if state.get("installer_is_wrapper_script"):
            source_dir.mkdir(parents=True, exist_ok=True)
            setup_filename = "install.ps1"
            script_content = WINGET_WRAPPER_TEMPLATE.format(
                app_name=app_name, install_cmd=state.get("install_cmd", "")
            )
            (source_dir / setup_filename).write_text(script_content, encoding="utf-8")
            logger.info("package_app: wrapper script Winget gerado em %s", source_dir / setup_filename)
        else:
            installer_ref = state.get("installer_url_or_path")
            if not installer_ref:
                updated["errors"] = state.get("errors", []) + [
                    "Nenhum instalador disponível (nem fornecido, nem descoberto, nem respondido pelo utilizador)."
                ]
                updated["intunewin_path"] = ""
                return updated

            local_installer = fetch_installer(installer_ref, source_dir)
            setup_filename = local_installer.name

        result_path = package_application(
            source_dir=source_dir,
            setup_file=setup_filename,
            app_name=app_name,
            output_dir=output_dir,
        )
        updated["intunewin_path"] = str(result_path)
        updated["errors"] = []
        logger.info("package_app: sucesso -> %s", result_path)

    except (InstallerFetchError, PackagingError, Exception) as exc:  # noqa: BLE001
        logger.exception("package_app falhou para '%s'", app_name)
        updated["errors"] = state.get("errors", []) + [f"Falha no empacotamento: {exc}"]
        updated["intunewin_path"] = ""

    return updated


def route_after_package(state: AgentState) -> str:
    return "end"
