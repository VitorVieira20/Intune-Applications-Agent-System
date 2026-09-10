# Intune Silent Install Agent

Sistema de agentes (LangGraph) que descobre parâmetros de instalação silenciosa
para Microsoft Intune (Win32/Winget), gera o pacote `.intunewin` final, e
pede confirmação ao utilizador (Human-in-the-Loop) sempre que há ambiguidade.

## Pré-requisitos

- Docker e Docker Compose
- Ollama a correr **na máquina host** (não em contentor) com o modelo `qwen2.5:7b`:
  ```bash
  ollama pull qwen2.5:7b
  ollama serve
  ```
- `IntuneWinAppUtil.exe` (ferramenta oficial da Microsoft), descarregada de:
  https://github.com/microsoft/Microsoft-Win32-Content-Prep-Tool
- Python 3.9+ na tua máquina, para correr o CLI

## Setup

1. Colocar o `IntuneWinAppUtil.exe` na pasta `./tools/`:
   ```bash
   cp /caminho/para/IntuneWinAppUtil.exe tools/
   ```

2. Criar o ficheiro de ambiente:
   ```bash
   cp .env.example .env
   ```

3. Confirmar que o Ollama do host está acessível:
   ```bash
   docker compose run --rm backend curl -f http://host.docker.internal:11434/api/tags
   ```

4. Subir os serviços:
   ```bash
   docker compose up -d --build
   ```

5. Verificar saúde:
   ```bash
   curl http://localhost/health
   ```

## Uso via CLI (recomendado)

```bash
cd cli
pip install -r requirements.txt
python intune_agent_cli.py "7-Zip"
```

O CLI:
- Envia o pedido inicial (só precisas do nome da app — o instalador é opcional,
  usa `--installer-url` se quiseres fornecê-lo já).
- Se o Winget devolver vários resultados, mostra-os numa tabela e deixas escolher.
- Se não encontrar nada no Winget, deixa-te escrever um nome diferente ou seguir
  para pesquisa web.
- Se não conseguir descobrir automaticamente o link do instalador, pergunta-te
  o URL/caminho diretamente.
- No final, mostra o resultado completo (comandos, detection rule, caminho do
  `.intunewin`).

Exemplo com URL já fornecida:
```bash
python intune_agent_cli.py "7-Zip" --installer-url https://www.7-zip.org/a/7z2408-x64.msi
```

## Uso via API diretamente

### Swagger UI
`http://localhost/docs` — permite testar tudo, incluindo o fluxo de HITL, no browser.

### curl

```bash
curl -X POST http://localhost/api/v1/analyze-and-package \
  -H "Content-Type: application/json" \
  -d '{"app_name": "7-Zip"}'
```

Se a resposta tiver `"status": "awaiting_human_input"`, respondes em:
```bash
curl -X POST http://localhost/api/v1/resume/<thread_id> \
  -H "Content-Type: application/json" \
  -d '{"action": "select_package", "package_id": "7zip.7zip"}'
```

Ações possíveis no `/resume`:
- `{"action": "select_package", "package_id": "..."}`
- `{"action": "provide_new_name", "new_app_name": "..."}`
- `{"action": "proceed_web_search"}`
- `{"action": "provide_installer", "installer_url_or_path": "..."}`

## Como o instalador é resolvido

1. Se a app foi encontrada no Winget → gera um script wrapper PowerShell que
   chama `winget install/uninstall`; não precisa de instalador físico.
2. Se enviaste `installer_url_or_path` no pedido → usa-o diretamente.
3. Se o LLM descobriu um link de download nos resultados da pesquisa web → usa-o
   automaticamente.
4. Se nenhuma das anteriores se aplicar → pausa e pergunta-te (via CLI ou `/resume`).

`installer_url_or_path` aceita URLs `http(s)://` (streaming download) ou
caminhos locais dentro do contentor (ex: partilha de rede montada como volume
extra no `docker-compose.yml`).

## Estrutura de dados persistida

- **Postgres** (`apps_history`, `system_logs`) — histórico de cada análise.
- **Redis** — checkpointer do LangGraph (permite pausar/retomar via `thread_id`
  em qualquer altura, mesmo depois de reiniciares o backend).

## Limitações conhecidas

- O empacotamento via Wine depende do binário e do Wine estarem corretamente
  configurados no contentor — a imagem já inclui `wine`/`wine32:i386`.
- A pesquisa web usa `DuckDuckGoSearchRun`; resultados fracos podem obrigar a
  mais iterações do loop de correção (`MAX_CORRECTION_LOOPS`, default 4).
- Threads pausados (`awaiting_human_input`) sem resposta ficam indefinidamente
  no Redis — ainda não há expiração automática.
- Apps Winget são empacotadas como wrapper script `winget install/uninstall`,
  não com o instalador nativo embutido.
