#!/usr/bin/env python3
"""CLI interativo para o Intune Silent Install Agent.

Uso:
    python intune_agent_cli.py "7-Zip"
    python intune_agent_cli.py "7-Zip" --installer-url https://www.7-zip.org/a/7z2408-x64.msi
    python intune_agent_cli.py "Notion" --api-url http://localhost:8080
"""
import argparse
import sys
from typing import Optional

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Intune Silent Install Agent - CLI interativo")
    parser.add_argument("app_name", help="Nome da aplicação a analisar (ex: '7-Zip')")
    parser.add_argument(
        "--installer-url", dest="installer_url", default=None,
        help="URL ou caminho local do instalador (opcional)",
    )
    parser.add_argument(
        "--api-url", dest="api_url", default="http://localhost",
        help="URL base da API (default: http://localhost)",
    )
    return parser.parse_args()


def start_analysis(api_url: str, app_name: str, installer_url: Optional[str]) -> dict:
    payload = {"app_name": app_name}
    if installer_url:
        payload["installer_url_or_path"] = installer_url

    resp = requests.post(f"{api_url}/api/v1/analyze-and-package", json=payload, timeout=600)
    resp.raise_for_status()
    return resp.json()


def resume_analysis(api_url: str, thread_id: str, decision: dict) -> dict:
    resp = requests.post(f"{api_url}/api/v1/resume/{thread_id}", json=decision, timeout=600)
    resp.raise_for_status()
    return resp.json()


def handle_winget_multiple_matches(payload: dict) -> dict:
    candidates = payload.get("candidates", [])
    console.print(Panel(payload.get("message", ""), title="Vários resultados no Winget", style="yellow"))

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", width=3)
    table.add_column("Nome")
    table.add_column("Package ID")
    table.add_column("Confiança")
    for idx, c in enumerate(candidates, start=1):
        table.add_row(str(idx), c.get("name", ""), c.get("package_id", ""), f"{c.get('confidence', 0):.1f}%")
    console.print(table)
    console.print("  [n] Nenhum destes -> seguir para pesquisa web")

    while True:
        choice = console.input("\nEscolhe um número, ou 'n' para pesquisa web: ").strip().lower()
        if choice == "n":
            return {"action": "proceed_web_search"}
        if choice.isdigit() and 1 <= int(choice) <= len(candidates):
            selected = candidates[int(choice) - 1]
            return {"action": "select_package", "package_id": selected["package_id"]}
        console.print("[red]Opção inválida, tenta novamente.[/red]")


def handle_winget_not_found(payload: dict) -> dict:
    console.print(Panel(payload.get("message", ""), title="Não encontrado no Winget", style="yellow"))
    console.print("  [1] Enviar um nome diferente")
    console.print("  [2] Seguir para pesquisa web")

    while True:
        choice = console.input("\nEscolhe uma opção (1/2): ").strip()
        if choice == "1":
            new_name = console.input("Novo nome da aplicação: ").strip()
            if new_name:
                return {"action": "provide_new_name", "new_app_name": new_name}
            console.print("[red]Nome vazio, tenta novamente.[/red]")
        elif choice == "2":
            return {"action": "proceed_web_search"}
        else:
            console.print("[red]Opção inválida, tenta novamente.[/red]")


def handle_installer_missing(payload: dict) -> dict:
    console.print(Panel(payload.get("message", ""), title="Instalador não encontrado", style="yellow"))
    url_or_path = console.input("URL de download ou caminho local do instalador: ").strip()
    return {"action": "provide_installer", "installer_url_or_path": url_or_path}


INTERRUPT_HANDLERS = {
    "winget_multiple_matches": handle_winget_multiple_matches,
    "winget_not_found": handle_winget_not_found,
    "installer_missing": handle_installer_missing,
}


def print_final_result(result: dict) -> None:
    status = result.get("status")
    style = "green" if status == "success" else "red"
    console.print(Panel(f"Status: [bold]{status}[/bold]", style=style))

    table = Table(show_header=False)
    table.add_row("App", result.get("app_name", ""))
    table.add_row("No Winget", str(result.get("in_store", False)))
    table.add_row("Install cmd", result.get("install_cmd") or "-")
    table.add_row("Uninstall cmd", result.get("uninstall_cmd") or "-")
    table.add_row("Detection rule", str(result.get("detection_rule") or "-"))
    table.add_row(".intunewin", result.get("intunewin_path") or "-")
    table.add_row("Ciclos de correção", str(result.get("correction_loops", 0)))
    if result.get("errors"):
        table.add_row("Erros", "\n".join(result["errors"]))
    console.print(table)


def main() -> None:
    args = parse_args()

    console.print(f"[bold cyan]A analisar '{args.app_name}'...[/bold cyan]")
    try:
        result = start_analysis(args.api_url, args.app_name, args.installer_url)
    except requests.RequestException as exc:
        console.print(f"[red]Erro ao contactar a API em {args.api_url}: {exc}[/red]")
        sys.exit(1)

    while result.get("status") == "awaiting_human_input":
        interrupt_type = result.get("interrupt_type", "")
        handler = INTERRUPT_HANDLERS.get(interrupt_type)

        if handler is None:
            console.print(f"[red]Tipo de interrupção desconhecido: '{interrupt_type}'. A abortar.[/red]")
            sys.exit(1)

        decision = handler(result)
        thread_id = result["thread_id"]

        console.print("[cyan]A retomar análise...[/cyan]")
        try:
            result = resume_analysis(args.api_url, thread_id, decision)
        except requests.RequestException as exc:
            console.print(f"[red]Erro ao retomar a análise: {exc}[/red]")
            sys.exit(1)

    print_final_result(result)
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
