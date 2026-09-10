from typing import Optional, TypedDict


class AgentState(TypedDict, total=False):
    app_name: str
    installer_url_or_path: Optional[str]
    in_store: bool
    winget_candidates: list[dict]   # [{"package_id": str, "name": str, "confidence": float}]
    search_context: str
    install_cmd: str
    uninstall_cmd: str
    detection_rule: dict
    installer_download_url: Optional[str]
    installer_is_wrapper_script: bool
    is_valid: bool
    intunewin_path: str
    errors: list[str]
    correction_loops: int
    human_review_route: str
