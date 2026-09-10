from typing import Literal, Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    app_name: str = Field(..., min_length=1, examples=["7-Zip"])
    installer_url_or_path: Optional[str] = Field(
        default=None, description="URL ou caminho local do instalador (opcional)"
    )


class HumanDecision(BaseModel):
    action: Literal[
        "select_package", "provide_new_name", "proceed_web_search", "provide_installer"
    ]
    package_id: Optional[str] = None
    new_app_name: Optional[str] = None
    installer_url_or_path: Optional[str] = None


class AnalyzeResponse(BaseModel):
    status: Literal["success", "failed"]
    thread_id: str
    id: Optional[int] = None
    app_name: str
    in_store: bool
    install_cmd: Optional[str] = None
    uninstall_cmd: Optional[str] = None
    detection_rule: Optional[dict] = None
    is_valid: bool = False
    intunewin_path: Optional[str] = None
    errors: list[str] = []
    correction_loops: int = 0


class InterruptResponse(BaseModel):
    status: Literal["awaiting_human_input"] = "awaiting_human_input"
    thread_id: str
    interrupt_type: str
    message: str
    app_name: str
    candidates: list[dict] = []
