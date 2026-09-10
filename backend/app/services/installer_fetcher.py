"""Obtenção do instalador da aplicação: suporta URL remota (http/https) ou
caminho local/partilha de rede já acessível dentro do contentor.
"""

import logging
import shutil
from pathlib import Path
from urllib.parse import urlparse

import requests

logger = logging.getLogger("intune_agent.installer_fetcher")

CHUNK_SIZE = 1024 * 1024
DOWNLOAD_TIMEOUT = 300


class InstallerFetchError(Exception):
    pass


def _is_remote_url(ref: str) -> bool:
    parsed = urlparse(ref)
    return parsed.scheme in ("http", "https")


def _filename_from_ref(ref: str) -> str:
    parsed = urlparse(ref)
    name = Path(parsed.path).name if parsed.path else Path(ref).name
    return name or "installer.bin"


def fetch_installer(installer_url_or_path: str, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    filename = _filename_from_ref(installer_url_or_path)
    destination_path = destination_dir / filename

    if _is_remote_url(installer_url_or_path):
        logger.info("A descarregar instalador de %s", installer_url_or_path)
        try:
            with requests.get(installer_url_or_path, stream=True, timeout=DOWNLOAD_TIMEOUT) as resp:
                resp.raise_for_status()
                with open(destination_path, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            fh.write(chunk)
        except requests.RequestException as exc:
            raise InstallerFetchError(f"Falha ao descarregar '{installer_url_or_path}': {exc}") from exc
    else:
        source_path = Path(installer_url_or_path)
        if not source_path.exists():
            raise InstallerFetchError(
                f"Caminho local do instalador não existe dentro do contentor: '{source_path}'. "
                "Se é uma partilha de rede, confirma que está montada como volume."
            )
        if not source_path.is_file():
            raise InstallerFetchError(f"Caminho '{source_path}' não é um ficheiro.")
        logger.info("A copiar instalador local de %s", source_path)
        shutil.copy2(source_path, destination_path)

    if not destination_path.exists() or destination_path.stat().st_size == 0:
        raise InstallerFetchError(f"Instalador '{destination_path}' não foi obtido corretamente (vazio ou ausente).")

    logger.info("Instalador disponível em %s (%d bytes)", destination_path, destination_path.stat().st_size)
    return destination_path
