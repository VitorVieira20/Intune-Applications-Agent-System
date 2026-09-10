import os
from langchain_community.tools import DuckDuckGoSearchRun
from app.agent.state import AgentState
from app.services.installer_fetcher import get_installer_metadata

# Caminho para o ficheiro local com as regras de todos os instaladores
CHEATSHEET_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../knowledge/installer_cheatsheet.md"))

def search_web_node(state: AgentState):
    """Nó responsável por recolher inteligência web e metadados do ficheiro."""
    app_name = state.get("app_name", "Aplicação Desconhecida")
    installer_path = state.get("installer_path", "")

    print(f"-> A recolher inteligência para: {app_name}")

    # 1. Extrair Metadados do Ficheiro Físico
    file_metadata = get_installer_metadata(installer_path)
    print(f"-> Metadados extraídos: {file_metadata}")

    # 2. Pesquisar no Silent Install HQ
    search = DuckDuckGoSearchRun()
    query = f"site:silentinstallhq.com {app_name} silent install uninstall registry"

    try:
        search_result = search.invoke(query)
    except Exception as e:
        print(f"-> Erro na pesquisa web: {e}")
        search_result = ""

    # 3. Carregar o Cheatsheet (Fallback)
    cheatsheet_data = ""
    if os.path.exists(CHEATSHEET_PATH):
        with open(CHEATSHEET_PATH, "r", encoding="utf-8") as f:
            cheatsheet_data = f.read()
    else:
        print(f"-> AVISO: Ficheiro cheatsheet não encontrado em {CHEATSHEET_PATH}")

    # 4. Construir o Contexto Combinado
    combined_context = f"""
    === SILENT INSTALL HQ RESULTS ===
    {search_result if search_result.strip() else 'No specific instructions found on Silent Install HQ.'}

    === GENERAL INSTALLER CHEATSHEET (FALLBACK) ===
    {cheatsheet_data}
    """

    # Atualiza o estado com as novas informações
    return {
        "search_context": combined_context,
        "file_metadata": file_metadata
    }