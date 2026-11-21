
from __future__ import annotations

import json
import re
from typing import Any

import fitz
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field


# -----------------------------
# Metadata structure
# -----------------------------

class Author(BaseModel):
    name: str = ""
    affiliation: str = ""


class ArticleMetadata(BaseModel):
    article_title: str = ""
    authors: list[Author] = Field(default_factory=list)
    abstract: str = ""
    doi: str = ""
    keywords: list[str] = Field(default_factory=list)
    journal_name: str = ""
    publisher: str = ""
    publication_year: str = ""
    volume: str = ""
    issue: str = ""
    start_page: str = ""
    end_page: str = ""
    page_range: str = ""
    references: list[str] = Field(default_factory=list)


# -----------------------------
# Read ALL PDF pages
# -----------------------------

def read_pdf(pdf_bytes: bytes) -> tuple[str, list[dict[str, Any]]]:
    pages = []

    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        for page_no, page in enumerate(pdf, start=1):
            page_text = page.get_text("text", sort=True).strip()

            pages.append({
                "page": page_no,
                "text": page_text
            })

    full_text = "\n\n".join(
        p["text"] for p in pages if p["text"]
    )

    return full_text, pages


# -----------------------------
# Direct extraction using regex
# -----------------------------

def find_doi(text: str) -> str:
    match = re.search(
        r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+",
        text,
        flags=re.IGNORECASE
    )

    return match.group(0).rstrip(".,;:)]}") if match else ""


def extract_header_fields(first_page: str) -> dict:
    result = {}

    # Example:
    # Vol. 38, No. 11 (2026), 2987-2992
    pattern = (
        r"Vol\.?\s*(\d+)\s*,?\s*"
        r"No\.?\s*(\d+)\s*"
        r"\((\d{4})\)\s*,?\s*"
        r"(\d+)\s*[-–—]\s*(\d+)"
    )

    match = re.search(pattern, first_page, re.IGNORECASE)

    if match:
        result["volume"] = match.group(1)
        result["issue"] = match.group(2)
        result["publication_year"] = match.group(3)
        result["start_page"] = match.group(4)
        result["end_page"] = match.group(5)
        result["page_range"] = (
            f"{match.group(4)}-{match.group(5)}"
        )

    # DOI
    result["doi"] = find_doi(first_page)

    # Journal name: text before volume information
    journal_match = re.search(
        r"^\s*([A-Z][A-Za-z &.]+?)\s*;\s*Vol\.?",
        first_page,
        re.MULTILINE
    )

    if journal_match:
        result["journal_name"] = journal_match.group(1).strip()

    return result


# -----------------------------
# Find references section
# -----------------------------

def find_reference_section(text: str) -> str:
    patterns = [
        r"(?im)^\s*REFERENCES\s*$",
        r"(?im)^\s*BIBLIOGRAPHY\s*$",
        r"(?im)^\s*WORKS CITED\s*$",
        r"(?im)^\s*LITERATURE CITED\s*$",
    ]

    positions = []

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            positions.append(match.start())

    if positions:
        return text[min(positions):]

    return ""


# -----------------------------
# Parse Ollama JSON response
# -----------------------------

def parse_json_response(content: Any) -> dict:
    if isinstance(content, dict):
        return content

    raw = str(content).strip()

    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)


# -----------------------------
# Ollama helper
# -----------------------------

def ask_ollama(
    llm: ChatOllama,
    prompt: str
) -> dict:

    response = llm.invoke(prompt)

    return parse_json_response(response.content)


# -----------------------------
# Main metadata extraction
# -----------------------------

def extract_metadata(
    pdf_bytes: bytes,
    model: str = "llama3.2:3b",
    base_url: str = "http://localhost:11434",
) -> tuple[ArticleMetadata, list[dict[str, Any]]]:

    # Step 1: Read complete PDF
    full_text, pages = read_pdf(pdf_bytes)

    if not full_text.strip():
        raise ValueError(
            "No selectable text found in this PDF. OCR is required."
        )

    # Step 2: Separate first page and references
    first_page = pages[0]["text"] if pages else ""

    reference_text = find_reference_section(full_text)

    # Step 3: Initialize Ollama
    llm = ChatOllama(
        model=model,
        base_url=base_url,
        temperature=0,
        format="json",
    )

    metadata = ArticleMetadata()

    # Step 4: Extract title, authors and affiliations
    prompt_metadata = f"""
Extract bibliographic metadata from the FIRST PAGE of this research paper.

Return ONLY valid JSON in this exact structure:

{{
  "article_title": "",
  "authors": [
    {{
      "name": "",
      "affiliation": ""
    }}
  ]
}}

Rules:
- Copy the complete article title.
- Extract every author in the original order.
- Match authors with their numbered affiliations.
- Do not include corresponding-author email as an author.
- Do not invent information.
- Do not return empty values if the information is visible.

PDF FIRST PAGE:
{first_page}
"""

    try:
        data = ask_ollama(llm, prompt_metadata)

        metadata.article_title = data.get("article_title", "")

        metadata.authors = [
            Author.model_validate(author)
            for author in data.get("authors", [])
            if isinstance(author, dict)
        ]

    except Exception as exc:
        print("Title/author extraction error:", exc)

    # Step 5: Extract abstract and keywords separately
    prompt_abstract = f"""
Extract the abstract and keywords from this research paper.

Return ONLY valid JSON:

{{
  "abstract": "",
  "keywords": []
}}

Rules:
- Copy the complete abstract exactly as printed.
- Do not summarize or rewrite it.
- Extract keywords separately.
- Do not use introduction text as the abstract.
- If a field is absent, return an empty value.

PDF TEXT:
{first_page}
"""

    try:
        data = ask_ollama(llm, prompt_abstract)

        metadata.abstract = data.get("abstract", "")
        metadata.keywords = data.get("keywords", [])

    except Exception as exc:
        print("Abstract/keyword extraction error:", exc)

    # Step 6: Extract references separately
    if reference_text:
        prompt_references = f"""
Extract the bibliography references from this research paper.

Return ONLY valid JSON:

{{
  "references": []
}}

Rules:
- Each numbered reference must be a separate list item.
- Preserve DOI and citation details.
- Do not include article body text.
- Do not invent references.

REFERENCE SECTION:
{reference_text[:24000]}
"""

        try:
            data = ask_ollama(llm, prompt_references)

            metadata.references = data.get("references", [])

        except Exception as exc:
            print("Reference extraction error:", exc)

    # Step 7: Extract structured fields directly
    # This avoids depending on the AI for obvious header information.
    direct_fields = extract_header_fields(first_page)

    for field, value in direct_fields.items():
        if value:
            setattr(metadata, field, value)

    # Step 8: DOI fallback using the entire PDF
    if not metadata.doi:
        metadata.doi = find_doi(full_text)

    # Step 9: Return metadata and page text
    return metadata, pages
