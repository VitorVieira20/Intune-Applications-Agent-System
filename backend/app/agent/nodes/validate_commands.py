import os
import json
import time
import subprocess

from langgraph.graph import END
from app.agent.state import AgentState

def validate_commands_node(state: AgentState):
    """
    Testa dinamicamente os comandos gerados usando a Windows Sandbox.
    Garante que a instalação é silenciosa (sem UI) e funcional.
    """
    installer_path = state.get("installer_path")
    install_cmd = state.get("install_cmd")
    app_name = state.get("app_name", "Aplicação")

    if not installer_path or not os.path.exists(installer_path):
        errors = state.get("errors", [])
        errors.append("Ficheiro executável não encontrado para teste.")
        return {"is_valid": False, "errors": errors}

    print(f"\n-> A iniciar teste na Sandbox para: {app_name}")
    print(f"-> Comando a testar: {install_cmd}")

    # Configuração de Caminhos Absolutos
    shared_folder_host = os.path.dirname(os.path.abspath(installer_path))

    # Caminhos dentro da Sandbox
    shared_folder_guest = "C:\\TempInstall"
    result_file_host = os.path.join(shared_folder_host, "resultado.json")
    result_file_guest = f"{shared_folder_guest}\\resultado.json"
    monitor_file_host = os.path.join(shared_folder_host, "monitor.ps1")
    wsb_file_host = os.path.join(shared_folder_host, "test.wsb")

    # Limpa resultados anteriores
    if os.path.exists(result_file_host):
        os.remove(result_file_host)

    # 1. O Script Espião em PowerShell
    ps_script = f"""
    $ResultFile = "{result_file_guest}"
    $ErrorActionPreference = "SilentlyContinue"

    $Output = @{{
        InstallSuccess = $false
        HasUI = $false
        ErrorMessage = ""
    }}

    try {{
        $Process = Start-Process -FilePath "cmd.exe" -ArgumentList "/c cd {shared_folder_guest} && {install_cmd}" -PassThru -WindowStyle Hidden
        $TimeoutSeconds = 300
        $Timer = 0

        while (-not $Process.HasExited) {{
            Start-Sleep -Seconds 1
            $Timer++

            $ChildProcesses = Get-CimInstance Win32_Process | Where-Object {{ $_.ParentProcessId -eq $Process.Id }}
            foreach ($child in $ChildProcesses) {{
                $p = Get-Process -Id $child.ProcessId
                if ($p -and $p.MainWindowHandle -ne 0) {{
                    $Output.HasUI = $true
                    $Output.ErrorMessage = "A instalação falhou: Uma janela gráfica (UI) foi detetada."
                    Stop-Process -Id $p.Id -Force
                    break
                }}
            }}

            if ($Timer -ge $TimeoutSeconds) {{
                $Output.ErrorMessage = "A instalação falhou: Excedeu o limite de 5 minutos."
                Stop-Process -Id $Process.Id -Force
                break
            }}
        }}

        if (-not $Output.HasUI -and $Output.ErrorMessage -eq "") {{
            if ($Process.ExitCode -eq 0 -or $Process.ExitCode -eq 3010) {{
                $Output.InstallSuccess = $true
            }} else {{
                $Output.ErrorMessage = "A instalação falhou com o Exit Code: " + $Process.ExitCode
            }}
        }}
    }} catch {{
        $Output.ErrorMessage = $_.Exception.Message
    }}

    $Output | ConvertTo-Json | Out-File -FilePath $ResultFile -Encoding UTF8
    Stop-Computer -Force
    """

    with open(monitor_file_host, "w", encoding="utf-8") as f:
        f.write(ps_script)

    # 2. Configuração da Sandbox (.wsb)
    wsb_content = f"""
    <Configuration>
      <MappedFolders>
        <MappedFolder>
          <HostFolder>{shared_folder_host}</HostFolder>
          <SandboxFolder>{shared_folder_guest}</SandboxFolder>
          <ReadOnly>false</ReadOnly>
        </MappedFolder>
      </MappedFolders>
      <LogonCommand>
        <Command>powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File {shared_folder_guest}\\monitor.ps1</Command>
      </LogonCommand>
    </Configuration>
    """

    with open(wsb_file_host, "w", encoding="utf-8") as f:
        f.write(wsb_content)

    # 3. Lançar a Windows Sandbox
    print("-> A lançar a Windows Sandbox... (isto pode demorar alguns segundos)")
    subprocess.Popen(["cmd.exe", "/c", "start", wsb_file_host], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 4. Aguardar pelo Relatório
    timeout = 320
    start_time = time.time()

    while not os.path.exists(result_file_host):
        if time.time() - start_time > timeout:
            errors = state.get("errors", [])
            errors.append("Teste falhou: A Sandbox não devolveu resposta (Timeout).")
            return {"is_valid": False, "errors": errors}
        time.sleep(2)

    # 5. Ler Resultado
    try:
        with open(result_file_host, "r", encoding="utf-8") as f:
            result = json.load(f)

        if result.get("InstallSuccess") and not result.get("HasUI"):
            print("-> SUCESSO: A Sandbox confirmou a instalação silenciosa!")
            return {"is_valid": True, "errors": []}
        else:
            error_msg = result.get("ErrorMessage", "Erro desconhecido na instalação.")
            print(f"-> FALHA NA SANDBOX: {error_msg}")

            errors = state.get("errors", [])
            errors.append(error_msg)
            return {"is_valid": False, "errors": errors}

    except Exception as e:
        errors = state.get("errors", [])
        errors.append(f"Erro ao ler o ficheiro resultado.json: {e}")
        return {"is_valid": False, "errors": errors}


def route_after_validate(state: AgentState) -> str:
    """
    Decide o próximo passo após a validação da Sandbox.
    Implementa um limite de tentativas para evitar loops infinitos.
    """
    is_valid = state.get("is_valid")
    errors = state.get("errors", [])

    if is_valid:
        # A chave "package_app" no graph.py mapeia para o próximo passo
        return "package_app"

    if len(errors) >= 3:
        print("\n-> [ALERTA] Limite de 3 tentativas falhadas atingido.")
        print("-> O agente não conseguiu encontrar um comando silencioso válido. A abortar...")
        return "end"

    print(f"-> A redirecionar para o LLM para corrigir o erro (Tentativa {len(errors)}/3)...")
    return "extract_parameters"