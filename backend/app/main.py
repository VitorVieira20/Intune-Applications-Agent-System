import logging
import uuid

from fastapi import Depends, FastAPI, HTTPException
from langgraph.types import Command
from sqlalchemy.orm import Session

from app.agent.graph import build_graph
from app.database import get_db, init_db
from app.models import AppHistory, SystemLog
from app.schemas import AnalyzeRequest, AnalyzeResponse, HumanDecision, InterruptResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("intune_agent")

app = FastAPI(title="Intune Silent Install Agent", version="1.1.0")

_graph = None


@app.on_event("startup")
async def on_startup() -> None:
    global _graph
    init_db()
    _graph = await build_graph()
    logger.info("Grafo LangGraph compilado e base de dados inicializada.")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _extract_interrupt_payload(final_state) -> dict | None:
    """Normaliza a forma como o LangGraph expõe interrupts pendentes.

    A chave/atributo exato pode variar por versão do langgraph — este helper
    cobre o formato mais comum ('__interrupt__' no dict de estado devolvido
    por ainvoke). Se a tua versão expuser de outra forma, ajusta aqui.
    """
    if not isinstance(final_state, dict):
        return None
    pending = final_state.get("__interrupt__")
    if not pending:
        return None
    first = pending[0]
    return first.value if hasattr(first, "value") else first


async def _persist_and_build_response(final_state: dict, thread_id: str, db: Session) -> AnalyzeResponse:
    status = "success" if (final_state.get("intunewin_path") or final_state.get("in_store")) else "failed"
    app_name = final_state.get("app_name", "")

    record = AppHistory(
        app_name=app_name,
        installer_url_or_path=final_state.get("installer_url_or_path"),
        in_store=final_state.get("in_store", False),
        install_cmd=final_state.get("install_cmd"),
        uninstall_cmd=final_state.get("uninstall_cmd"),
        detection_rule=final_state.get("detection_rule"),
        is_valid=final_state.get("is_valid", False),
        intunewin_path=final_state.get("intunewin_path") or None,
        status=status,
        errors=final_state.get("errors", []),
        correction_loops=final_state.get("correction_loops", 0),
        thread_id=thread_id,
    )
    db.add(record)
    db.flush()
    db.add(
        SystemLog(
            app_history_id=record.id,
            node_name="graph_run",
            level="INFO" if status == "success" else "ERROR",
            message=f"Execução terminada com status={status}, thread_id={thread_id}",
        )
    )
    db.commit()
    db.refresh(record)

    return AnalyzeResponse(
        status=status,
        thread_id=thread_id,
        id=record.id,
        app_name=record.app_name,
        in_store=record.in_store,
        install_cmd=record.install_cmd,
        uninstall_cmd=record.uninstall_cmd,
        detection_rule=record.detection_rule,
        is_valid=record.is_valid,
        intunewin_path=record.intunewin_path,
        errors=record.errors or [],
        correction_loops=record.correction_loops,
    )


@app.post("/api/v1/analyze-and-package", response_model=None)
async def analyze_and_package(payload: AnalyzeRequest, db: Session = Depends(get_db)):
    if _graph is None:
        raise HTTPException(status_code=503, detail="Agente ainda não inicializado.")

    thread_id = str(uuid.uuid4())
    initial_state = {
        "app_name": payload.app_name,
        "installer_url_or_path": payload.installer_url_or_path,
        "in_store": False,
        "winget_candidates": [],
        "search_context": "",
        "install_cmd": "",
        "uninstall_cmd": "",
        "detection_rule": {},
        "installer_download_url": None,
        "installer_is_wrapper_script": False,
        "is_valid": False,
        "intunewin_path": "",
        "errors": [],
        "correction_loops": 0,
    }
    config = {"configurable": {"thread_id": thread_id}}

    try:
        final_state = await _graph.ainvoke(initial_state, config=config)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha na execução do grafo para '%s'", payload.app_name)
        raise HTTPException(status_code=500, detail=f"Erro no agente: {exc}") from exc

    interrupt_payload = _extract_interrupt_payload(final_state)
    if interrupt_payload:
        return InterruptResponse(
            thread_id=thread_id,
            interrupt_type=interrupt_payload.get("type", "unknown"),
            message=interrupt_payload.get("message", ""),
            app_name=interrupt_payload.get("app_name", payload.app_name),
            candidates=interrupt_payload.get("candidates", []),
        )

    return await _persist_and_build_response(final_state, thread_id, db)


@app.post("/api/v1/resume/{thread_id}", response_model=None)
async def resume_analysis(thread_id: str, decision: HumanDecision, db: Session = Depends(get_db)):
    if _graph is None:
        raise HTTPException(status_code=503, detail="Agente ainda não inicializado.")

    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await _graph.aget_state(config)

    if not snapshot or not snapshot.values:
        raise HTTPException(status_code=404, detail=f"thread_id '{thread_id}' não encontrado ou já terminado.")

    try:
        final_state = await _graph.ainvoke(
            Command(resume=decision.model_dump(exclude_none=True)), config=config
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha ao retomar grafo para thread_id=%s", thread_id)
        raise HTTPException(status_code=500, detail=f"Erro ao retomar o agente: {exc}") from exc

    interrupt_payload = _extract_interrupt_payload(final_state)
    if interrupt_payload:
        return InterruptResponse(
            thread_id=thread_id,
            interrupt_type=interrupt_payload.get("type", "unknown"),
            message=interrupt_payload.get("message", ""),
            app_name=interrupt_payload.get("app_name", ""),
            candidates=interrupt_payload.get("candidates", []),
        )

    return await _persist_and_build_response(final_state, thread_id, db)
