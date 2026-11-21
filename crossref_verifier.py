from __future__ import annotations

import re
import time
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import quote

import requests


API_BASE = "https://api.crossref.org/works"


def _normalise(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _first(values):
    return values[0] if isinstance(values, list) and values else ""


def _crossref_authors(record: dict[str, Any]) -> list[str]:
    result = []
    for author in record.get("author", []) or []:
        given = author.get("given", "")
        family = author.get("family", "")
        name = " ".join(x for x in [given, family] if x).strip()
        if name:
            result.append(name)
    return result


def _year(record: dict[str, Any]) -> str:
    for key in ("published-print", "published-online", "issued", "created"):
        date_parts = (record.get(key) or {}).get("date-parts") or []
        if date_parts and date_parts[0]:
            return str(date_parts[0][0])
    return ""


def _record_summary(record: dict[str, Any]) -> dict[str, Any]:
    page = record.get("page", "") or ""
    page_parts = re.split(r"[-–]", page, maxsplit=1) if page else ["", ""]
    return {
        "article_title": _first(record.get("title")),
        "authors": _crossref_authors(record),
        "abstract": record.get("abstract", "") or "",
        "doi": record.get("DOI", "") or "",
        "journal_name": _first(record.get("container-title")),
        "publisher": record.get("publisher", "") or "",
        "publication_year": _year(record),
        "volume": record.get("volume", "") or "",
        "issue": record.get("issue", "") or "",
        "page_range": page,
        "start_page": page_parts[0],
        "end_page": page_parts[1] if len(page_parts) > 1 else "",
        "references": [
            item.get("unstructured", "") or _format_reference(item)
            for item in (record.get("reference") or [])
        ],
        "crossref_type": record.get("type", "") or "",
        "url": record.get("URL", "") or "",
    }


def _format_reference(item: dict[str, Any]) -> str:
    bits = []
    for key in ("author", "year", "article-title", "journal-title", "volume", "first-page", "DOI"):
        if item.get(key):
            bits.append(str(item[key]))
    return ". ".join(bits)


def _title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalise(left), _normalise(right)).ratio()


def _compare(extracted: dict[str, Any], crossref: dict[str, Any]) -> list[dict[str, Any]]:
    checks = []

    def add(field: str, pdf_value: str, cr_value: str, score: str):
        pdf_value = str(pdf_value or "").strip()
        cr_value = str(cr_value or "").strip()
        if not pdf_value:
            status = "Not extracted from PDF"
        elif not cr_value:
            status = "Not deposited in Crossref"
        elif field == "article_title":
            similarity = _title_similarity(pdf_value, cr_value)
            status = "Match" if similarity >= 0.92 else ("Close match" if similarity >= 0.78 else "Mismatch")
            score = f"{similarity:.0%}"
        else:
            status = "Match" if _normalise(pdf_value) == _normalise(cr_value) else "Mismatch"
        checks.append({
            "field": field,
            "PDF extraction": pdf_value,
            "Crossref": cr_value,
            "verification": status,
            "match score": score,
        })

    add("article_title", extracted.get("article_title", ""), crossref.get("article_title", ""), "")
    add("doi", extracted.get("doi", ""), crossref.get("doi", ""), "")
    add("journal_name", extracted.get("journal_name", ""), crossref.get("journal_name", ""), "")
    add("publication_year", extracted.get("publication_year", ""), crossref.get("publication_year", ""), "")
    add("volume", extracted.get("volume", ""), crossref.get("volume", ""), "")
    add("issue", extracted.get("issue", ""), crossref.get("issue", ""), "")
    add("page_range", extracted.get("page_range", ""), crossref.get("page_range", ""), "")

    pdf_authors = [a.get("name", "") for a in extracted.get("authors", [])]
    cr_authors = crossref.get("authors", [])
    add("authors", "; ".join(pdf_authors), "; ".join(cr_authors), "")
    add("abstract", extracted.get("abstract", ""), crossref.get("abstract", ""), "")
    add("publisher", extracted.get("publisher", ""), crossref.get("publisher", ""), "")

    pdf_refs = extracted.get("references", []) or []
    cr_refs = crossref.get("references", []) or []
    if not pdf_refs:
        ref_status = "Not extracted from PDF"
    elif not cr_refs:
        ref_status = "Not deposited in Crossref"
    else:
        ref_status = f"Count: PDF {len(pdf_refs)} / Crossref {len(cr_refs)} (not a full text comparison)"
    checks.append({
        "field": "references",
        "PDF extraction": f"{len(pdf_refs)} references",
        "Crossref": f"{len(cr_refs)} references",
        "verification": ref_status,
        "match score": "",
    })
    return checks


def verify_with_crossref(
    extracted: dict[str, Any],
    mailto: str = "",
    timeout: int = 20,
) -> dict[str, Any]:
    headers = {
        "User-Agent": f"PDFMetadataVerifier/1.0 (mailto:{mailto or 'not-provided'})"
    }
    params = {"mailto": mailto} if mailto else {}

    doi = (extracted.get("doi") or "").strip()
    record = None
    lookup_method = ""
    candidates = []

    if doi:
        clean_doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.I).strip()
        url = f"{API_BASE}/{quote(clean_doi, safe='')}"
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        if response.status_code == 200:
            record = response.json().get("message")
            lookup_method = "Exact DOI lookup"
        elif response.status_code not in (404,):
            response.raise_for_status()

    # If the PDF has no DOI, or the DOI was not found, search by bibliographic text.
    if record is None:
        title = extracted.get("article_title", "").strip()
        authors = extracted.get("authors", []) or []
        first_author = authors[0].get("name", "") if authors else ""
        query = " ".join(x for x in [title, first_author] if x)
        if not query:
            return {
                "status": "Insufficient PDF metadata to search Crossref",
                "lookup_method": "No DOI and no article title",
                "candidate": None,
                "candidates": [],
                "checks": [],
            }
        search_params = {
            "query.bibliographic": query,
            "rows": 5,
            "select": "DOI,title,author,container-title,publisher,published-print,published-online,issued,created,volume,issue,page,abstract,reference,type,URL",
        }
        search_params.update(params)
        response = requests.get(API_BASE, params=search_params, headers=headers, timeout=timeout)
        response.raise_for_status()
        items = response.json().get("message", {}).get("items", [])
        for item in items:
            summary = _record_summary(item)
            similarity = _title_similarity(title, summary["article_title"])
            candidates.append({"similarity": similarity, "record": summary})
        candidates.sort(key=lambda x: x["similarity"], reverse=True)
        if candidates and candidates[0]["similarity"] >= 0.75:
            record = items[next(
                i for i, item in enumerate(items)
                if _record_summary(item)["doi"] == candidates[0]["record"]["doi"]
            )]
            lookup_method = "Bibliographic title/author search"
        else:
            return {
                "status": "No confident Crossref match found",
                "lookup_method": "Bibliographic title/author search",
                "candidate": None,
                "candidates": candidates,
                "checks": [],
            }

    summary = _record_summary(record)
    checks = _compare(extracted, summary)
    doi_match = bool(doi and summary["doi"] and
                     re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.I).lower()
                     == summary["doi"].lower())
    title_score = _title_similarity(
        extracted.get("article_title", ""), summary.get("article_title", "")
    )
    if doi and doi_match and title_score >= 0.92:
        status = "DOI and title verified"
    elif title_score >= 0.92:
        status = "Likely Crossref match — review field differences"
    else:
        status = "Crossref record found — manual review required"

    return {
        "status": status,
        "lookup_method": lookup_method,
        "candidate": summary,
        "candidates": candidates,
        "checks": checks,
    }
