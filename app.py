import json
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from pdf_extractor import extract_metadata
from crossref_verifier import verify_with_crossref

load_dotenv()
st.set_page_config(page_title="PDF Metadata Extractor", page_icon="📄", layout="wide")
st.title("📄 Research Article PDF Metadata Extractor")
st.caption("Extract bibliographic data locally with Ollama, then verify it against Crossref.")

with st.sidebar:
    st.header("Local extraction settings")
    model = st.text_input("Ollama model", "llama3.2:3b")
    base_url = st.text_input("Ollama URL", "http://localhost:11434")
    st.divider()
    st.header("Crossref settings")
    mailto = st.text_input("Email for polite Crossref API access (optional)", "")
    st.caption("Crossref verification needs an internet connection. PDF extraction runs locally.")

uploads = st.file_uploader(
    "Upload research article PDFs",
    type=["pdf"],
    accept_multiple_files=True,
)

if st.button("Extract PDF data and verify with Crossref", type="primary", disabled=not uploads):
    all_results = []
    for file in uploads:
        st.divider()
        st.subheader(file.name)
        try:
            with st.spinner("Extracting metadata from PDF using local Ollama..."):
                metadata, pages = extract_metadata(file.getvalue(), model=model, base_url=base_url)
                extracted = metadata.model_dump()
                extracted["pdf_name"] = file.name
            # st.success(f"Extracted text from {len(pages)} page(s).")
            with st.expander("Debug: View extracted PDF text"):
                for page in pages:
                    st.markdown(f"### Page {page['page']}")
                    st.text(page["text"])
            with st.expander("Extracted PDF metadata", expanded=True):
                st.json(extracted)

            with st.spinner("Checking the extracted metadata against Crossref..."):
                verification = verify_with_crossref(extracted, mailto=mailto)

            st.markdown(f"**Crossref result:** {verification['status']}")
            st.caption(f"Lookup method: {verification['lookup_method']}")

            if verification.get("candidate"):
                st.subheader("PDF vs Crossref comparison")
                st.dataframe(pd.DataFrame(verification["checks"]), use_container_width=True, hide_index=True)
                with st.expander("Crossref record"):
                    st.json(verification["candidate"])
            elif verification.get("candidates"):
                st.warning("No candidate passed the automatic title-similarity threshold. Review these possible matches.")
                st.dataframe(pd.DataFrame([
                    {
                        "title similarity": f"{c['similarity']:.0%}",
                        "title": c["record"]["article_title"],
                        "authors": ", ".join(c["record"]["authors"][:4]),
                        "DOI": c["record"]["doi"],
                    } for c in verification["candidates"]
                ]), use_container_width=True, hide_index=True)
            else:
                st.info("Crossref could not verify this record. This does not necessarily mean the PDF metadata is incorrect.")

            result = {
                "pdf_name": file.name,
                "pdf_extracted_metadata": extracted,
                "crossref_verification": verification,
            }
            all_results.append(result)
            st.download_button(
                "Download extraction + verification JSON",
                data=json.dumps(result, ensure_ascii=False, indent=2),
                file_name=f"{file.name.rsplit('.', 1)[0]}_verified_metadata.json",
                mime="application/json",
                key=f"download_{file.name}",
            )
        except Exception as exc:
            st.error(f"Could not process {file.name}: {exc}")

    if all_results:
        st.success(f"Finished processing {len(all_results)} PDF(s).")

st.info(
    "Important: Crossref only verifies metadata deposited in its database. "
    "Some records may have no abstract or reference list. A missing Crossref field "
    "is reported as 'Not deposited in Crossref', not as an extraction error."
)
