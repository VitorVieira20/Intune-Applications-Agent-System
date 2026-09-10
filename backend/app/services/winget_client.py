"""Cliente para pesquisar apps no catálogo Winget (via api.winget.run).

Em vez de decidir sozinho qual é "a" app certa, devolve todos os candidatos
relevantes (acima de um limiar mínimo de relevância) para que o passo de
Human-in-the-Loop decida. Só faz auto-aceitação quando há uma correspondência
exata (case-insensitive) de nome — nesse caso não há ambiguidade a resolver.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import requests
from rapidfuzz import fuzz, process

logger = logging.getLogger("intune_agent.winget")

WINGET_SEARCH_URL = "https://api.winget.run/v2/packages"
LOW_RELEVANCE_THRESHOLD = 45
MAX_CANDIDATES = 6


@dataclass
class WingetCandidate:
    package_id: str
    name: str
    confidence: float


@dataclass
class WingetSearchResult:
    exact_match: Optional[WingetCandidate] = None
    candidates: list[WingetCandidate] = field(default_factory=list)


def _extract_candidate_name(pkg: dict) -> str:
    latest = pkg.get("Latest", {}) if isinstance(pkg, dict) else {}
    return latest.get("PackageName") or pkg.get("Name") or pkg.get("Id") or ""


def search_winget_candidates(app_name: str, timeout: int = 8) -> WingetSearchResult:
    try:
        resp = requests.get(
            WINGET_SEARCH_URL, params={"query": app_name, "limit": 20}, timeout=timeout
        )
        resp.raise_for_status()
        data = resp.json()
        packages = data.get("Packages", []) if isinstance(data, dict) else []
    except requests.RequestException as exc:
        logger.warning("Falha ao consultar winget.run para '%s': %s", app_name, exc)
        return WingetSearchResult()

    if not packages:
        return WingetSearchResult()

    candidates_by_name = {
        _extract_candidate_name(pkg): pkg for pkg in packages if _extract_candidate_name(pkg)
    }
    if not candidates_by_name:
        return WingetSearchResult()

    normalized_query = app_name.strip().lower()
    for name, pkg in candidates_by_name.items():
        if name.strip().lower() == normalized_query:
            package_id = pkg.get("Id") or pkg.get("PackageIdentifier")
            if package_id:
                return WingetSearchResult(
                    exact_match=WingetCandidate(package_id=package_id, name=name, confidence=100.0)
                )

    ranked = process.extract(
        app_name, candidates_by_name.keys(), scorer=fuzz.WRatio, limit=MAX_CANDIDATES
    )

    candidates = []
    for name, score, _ in ranked:
        if score < LOW_RELEVANCE_THRESHOLD:
            continue
        pkg = candidates_by_name[name]
        package_id = pkg.get("Id") or pkg.get("PackageIdentifier")
        if package_id:
            candidates.append(WingetCandidate(package_id=package_id, name=name, confidence=round(score, 1)))

    return WingetSearchResult(candidates=candidates)
