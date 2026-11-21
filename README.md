# PDF Metadata Extractor + Crossref Verifier

A focused application that extracts journal article metadata from PDFs using a local Ollama model, then checks the result against Crossref's public REST API.

## Scope

This project only does:
1. Extract article metadata from uploaded PDFs.
2. Verify the extracted metadata against Crossref.
3. Show field-by-field differences.
4. Export the extracted data and verification report as JSON.

It does not include RAG chat, vector databases, SQL Server, or XML export in this version.

## Fields extracted from PDF

- Article title
- Authors and affiliations
- Abstract
- DOI
- Keywords
- Journal name and publisher
- Publication year
- Volume and issue
- Start page, end page and page range
- References

## Crossref verification

- If the PDF contains a DOI, the app tries the exact `/works/{doi}` endpoint.
- If no DOI is found (or the DOI is not registered in Crossref), it searches by article title and first author using `query.bibliographic`.
- It compares title, DOI, authors, journal, year, volume, issue, pages, abstract and publisher.
- It also compares the number of references deposited in Crossref. It does not claim that a count-only comparison proves every reference matches.
- Crossref may not contain every field. Missing Crossref data is shown as "Not deposited in Crossref", not as a PDF extraction failure.

Crossref documentation:
- REST API: https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- Access and polite pool: https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/

## Requirements

- Python 3.13 or 3.12 recommended
- Ollama installed
- Internet connection for Crossref verification

## Windows installation

Install Ollama from https://ollama.com/download.

Pull a local chat model:

```powershell
ollama pull llama3.2:3b
```

Create and activate a Python environment:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Start the app:

```powershell
streamlit run app.py
```

Open the local URL shown by Streamlit, usually http://localhost:8501.

## Important accuracy notes

- PDF extraction runs locally. Crossref verification requires internet.
- Scanned PDFs need OCR; this version handles selectable PDF text.
- A small local model can miss or mis-associate authors, affiliations, and references. Always review extracted output.
- Crossref is not a universal registry. A DOI registered with DataCite or another agency will not be found through the Crossref works endpoint.
- Crossref records are deposited by publishers/members and can be incomplete. A mismatch is a review flag, not automatic proof that the PDF is wrong.
- The app does not overwrite PDF-extracted values with Crossref values; it keeps both for comparison.
