"""Wrapper de empacotamento .intunewin compatível com Linux/macOS.

Estrategia principal: correr o IntuneWinAppUtil.exe oficial via Wine
(INTUNEWIN_APPUTIL_EXE, tipicamente montado como volume Docker). Se a
ferramenta ou o Wine nao estiverem disponiveis, cai para um wrapper Python
que reimplementa o formato .intunewin publicamente documentado (zip com
Metadata/Detection.xml + Contents/IntunePackage.intunewin cifrado em
AES-256-CBC com HMAC-SHA256 de integridade).
"""

import base64
import hashlib
import hmac
import logging
import os
import subprocess
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

logger = logging.getLogger("intune_agent.packager")


class PackagingError(Exception):
    pass


def _encrypt_content(source_zip_bytes: bytes) -> tuple[bytes, bytes, bytes]:
    key = os.urandom(32)
    iv = os.urandom(16)

    cipher = AES.new(key, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(pad(source_zip_bytes, AES.block_size))

    hmac_digest = hmac.new(key, iv + encrypted, hashlib.sha256).digest()

    payload = hmac_digest + iv + encrypted
    return payload, key, iv


def _build_detection_xml(app_name: str, setup_file: str, unencrypted_size: int, key: bytes, iv: bytes) -> str:
    root = ET.Element("ApplicationInfo", {"xmlns": "http://schemas.microsoft.com/win/2011/12/appx"})
    ET.SubElement(root, "Name").text = app_name
    ET.SubElement(root, "UnencryptedContentSize").text = str(unencrypted_size)
    ET.SubElement(root, "FileName").text = "IntunePackage.intunewin"
    ET.SubElement(root, "SetupFile").text = setup_file
    ET.SubElement(root, "ToolVersion").text = "1.0.0-python-wrapper"

    enc_info = ET.SubElement(root, "EncryptionInfo")
    ET.SubElement(enc_info, "EncryptionKey").text = base64.b64encode(key).decode()
    ET.SubElement(enc_info, "InitializationVector").text = base64.b64encode(iv).decode()
    ET.SubElement(enc_info, "MacKey").text = base64.b64encode(key).decode()
    ET.SubElement(enc_info, "MacHashAlgorithm").text = "HmacSHA256"
    ET.SubElement(enc_info, "ProfileIdentifier").text = "ProfileVersion1"
    ET.SubElement(enc_info, "FileDigest").text = base64.b64encode(
        hashlib.sha256(str(uuid.uuid4()).encode()).digest()
    ).decode()
    ET.SubElement(enc_info, "FileDigestAlgorithm").text = "SHA256"

    return ET.tostring(root, encoding="unicode")


def _package_with_python_wrapper(source_dir: Path, setup_file: str, app_name: str, output_path: Path) -> Path:
    tmp_content_zip = output_path.with_suffix(".contents.tmp.zip")
    with zipfile.ZipFile(tmp_content_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(source_dir))

    content_bytes = tmp_content_zip.read_bytes()
    unencrypted_size = len(content_bytes)
    tmp_content_zip.unlink(missing_ok=True)

    encrypted_payload, key, iv = _encrypt_content(content_bytes)
    detection_xml = _build_detection_xml(app_name, setup_file, unencrypted_size, key, iv)

    if output_path.exists():
        output_path.unlink()

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("IntuneWinPackage/Metadata/Detection.xml", detection_xml)
        zf.writestr("IntuneWinPackage/Contents/IntunePackage.intunewin", encrypted_payload)

    logger.info("Pacote .intunewin gerado (wrapper Python) em %s", output_path)
    return output_path


def _package_with_official_tool(source_dir: Path, setup_file: str, output_dir: Path) -> Path:
    apputil_exe = os.environ.get("INTUNEWIN_APPUTIL_EXE")
    if not apputil_exe or not Path(apputil_exe).exists():
        raise PackagingError(
            f"Ferramenta oficial não encontrada em INTUNEWIN_APPUTIL_EXE='{apputil_exe}'. "
            "Verifica se o volume ./tools está montado e contém o IntuneWinAppUtil.exe."
        )

    cmd = [
        "wine", apputil_exe,
        "-c", str(source_dir),
        "-s", setup_file,
        "-o", str(output_dir),
        "-q",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except FileNotFoundError as exc:
        raise PackagingError(f"Binário 'wine' não encontrado no contentor: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise PackagingError(f"IntuneWinAppUtil excedeu o timeout de 600s: {exc}") from exc

    if result.returncode != 0:
        raise PackagingError(
            f"IntuneWinAppUtil falhou (exit={result.returncode}). "
            f"stdout={result.stdout[-500:]} stderr={result.stderr[-500:]}"
        )

    generated = list(output_dir.glob("*.intunewin"))
    if not generated:
        raise PackagingError(
            "IntuneWinAppUtil correu sem erro (exit 0) mas nenhum .intunewin foi encontrado em "
            f"{output_dir}. Verifica se '-s {setup_file}' corresponde a um ficheiro real em {source_dir}."
        )
    return generated[0]


def package_application(source_dir: Path, setup_file: str, app_name: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in app_name if c.isalnum() or c in ("-", "_")) or "app"
    output_path = output_dir / f"{safe_name}.intunewin"

    try:
        return _package_with_official_tool(source_dir, setup_file, output_dir)
    except PackagingError as exc:
        logger.info("Ferramenta oficial indisponível (%s); a usar wrapper Python.", exc)
        return _package_with_python_wrapper(source_dir, setup_file, app_name, output_path)
