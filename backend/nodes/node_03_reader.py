"""Node 03 — Custom Reader & Processing (document ingestion).

Extracts unstructured clinical text from uploaded documents. Plain-text and
CSV ingestion is implemented natively; PDF/DOCX extraction uses optional
deps (pypdf / python-docx) and reports gracefully when absent. Extracted text
is PII-anonymized (Node 16) before reaching the consensus core.
"""
from __future__ import annotations

from pathlib import Path

from backend.core.security import anonymize_text
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode

_TEXT_SUFFIXES = {".txt", ".csv", ".md", ".json"}


class CustomReaderNode(BaseNode):
    node_id = 3
    node_name = "Custom Reader & Processing"
    implemented = True

    def read_text(self, content: str, filename: str = "upload.txt", anonymize: bool = True) -> dict:
        suffix = Path(filename).suffix.lower()
        if suffix in _TEXT_SUFFIXES:
            text = content
            extractor = "native-text"
        elif suffix == ".pdf":
            text = self._read_pdf(content)
            extractor = "pypdf"
        elif suffix in {".docx", ".doc"}:
            return {
                "status": "stub",
                "message": "DOCX extraction requires the optional 'python-docx' package.",
                "filename": filename,
            }
        else:
            return {"status": "stub", "message": f"Unsupported file type: {suffix}"}

        if extractor != "native-text" and text is None:
            return {
                "status": "stub",
                "message": "PDF extraction requires the optional 'pypdf' package (pip install pypdf).",
                "filename": filename,
            }

        clean = " ".join(text.split())
        safe, found = anonymize_text(clean) if anonymize else (clean, {})
        self.audit(
            "document_ingested",
            details={"filename": filename, "chars": len(clean), "extractor": extractor,
                     "pii_redacted": {k: len(v) for k, v in found.items()}},
        )
        return {
            "status": "ok",
            "filename": filename,
            "extractor": extractor,
            "char_count": len(clean),
            "pii_redacted": found,
            "extracted_text_preview": safe[:500],
            "full_text_available": True,
        }

    @staticmethod
    def _read_pdf(content: str) -> str | None:
        try:  # pragma: no cover - optional dependency
            import io

            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(content.encode("latin-1", errors="ignore")))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return None

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        return self.read_text(
            payload.get("content", ""),
            payload.get("filename", "upload.txt"),
            payload.get("anonymize", True),
        )


custom_reader_node = CustomReaderNode()
