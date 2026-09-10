import json
import logging

from app.agent.prompts import EXTRACT_PARAMETERS_PROMPT
from langchain_ollama import ChatOllama

from app.agent.prompts import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_TEMPLATE
from app.agent.state import AgentState
from app.config import settings

logger = logging.getLogger("intune_agent.node.extract_parameters")

_llm = ChatOllama(
    base_url=settings.ollama_base_url,
    model=settings.ollama_model,
    format="json",
    temperature=0.0,
)


def _safe_json_parse(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                pass
        raise


def extract_parameters_node(state: AgentState):
    """Usa o Ollama para extrair ou corrigir os comandos de instalação."""
    app_name = state.get("app_name", "Aplicação")
    search_context = state.get("search_context", "")
    file_metadata = state.get("file_metadata", "")
    errors = state.get("errors", [])

    # Construir o bloco de feedback se o Sandbox tiver reprovado uma tentativa anterior
    error_feedback = ""
    if errors:
        error_feedback = "### CRITICAL FEEDBACK FROM PREVIOUS ATTEMPT:\n"
        error_feedback += "Your previous commands failed in the Windows Sandbox test for the following reasons:\n"
        for err in errors:
            error_feedback += f"- {err}\n"
        error_feedback += "WARNING: You MUST change the install_cmd or uninstall_cmd flags to fix these issues. Do not suggest the exact same commands again.\n"
        print(f"-> A pedir correção ao LLM baseada nos erros: {errors[-1]}")

    # Formatar o prompt final
    prompt = EXTRACT_PARAMETERS_PROMPT.format(
        app_name=app_name,
        error_feedback=error_feedback,
        file_metadata=file_metadata,
        search_context=search_context
    )

    # Configurar o modelo local via host.docker.internal (ou IP da rede)
    llm = ChatOllama(model="qwen2.5:7b", format="json", temperature=0.1)

    response = llm.invoke(prompt)

    # Limpeza rigorosa do JSON (Remove blocos de markdown ```json )
    raw_content = response.content.strip()
    if raw_content.startswith("```json"):
        raw_content = raw_content[7:]
    if raw_content.startswith("```"):
        raw_content = raw_content[3:]
    if raw_content.endswith("```"):
        raw_content = raw_content[:-3]

    try:
        data = json.loads(raw_content.strip())
        return {
            "install_cmd": data.get("install_cmd", "Not found"),
            "uninstall_cmd": data.get("uninstall_cmd", "Not found"),
            "detection_rule": data.get("detection_rule", "Not found"),
            # Limpamos a flag de validação para forçar um novo teste na Sandbox
            "is_valid": None
        }
    except json.JSONDecodeError as e:
        print(f"-> Erro no parse do JSON: {e}")
        # Adiciona erro ao estado para o LLM tentar estruturar melhor
        errors.append("Invalid JSON output format.")
        return {"install_cmd": "", "uninstall_cmd": "", "detection_rule": "", "errors": errors}