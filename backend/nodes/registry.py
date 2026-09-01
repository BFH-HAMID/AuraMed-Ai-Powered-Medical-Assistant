"""Registry of all 26 AuraMed architecture nodes.

Importing this module (it is imported by ``backend.main``) registers every
node: its number, display name, and whether it is fully implemented in this
deployment or a documented integration stub. The registry powers ``GET /``
and ``GET /health`` capability reporting.
"""
from __future__ import annotations

from backend.nodes import register

# Fully implemented / functional nodes
register(2, "Emergency Triage & Red Flag Detection", implemented=True)
register(5, "Drug Safety & Allergy Check", implemented=True)
register(6, "Text-to-Speech Output", implemented=True)
register(7, "Multi-Source Report Comparison", implemented=True)
register(8, "Second Opinion & Dual-AI Consensus", implemented=True)
register(9, "Patient History & Vitals Integration", implemented=True)
register(10, "Data Synthesis & Preparation", implemented=True)
register(11, "Health Risk Predictor Score", implemented=True)
register(12, "Medicine-Related Documentation", implemented=True)
register(13, "Prescription & Guidelines Engine", implemented=True)
register(14, "First Aid & Emergency Guidebook", implemented=True)
register(15, "Lab Test Recommendations", implemented=True)
register(16, "Advanced Data Privacy & HIPAA Compliance", implemented=True)
register(17, "Simplified Patient Explanation", implemented=True)
register(18, "Diet & Lifestyle Guide Generator", implemented=True)
register(19, "Emergency Proximity Routing", implemented=True)
register(20, "Multi-Language Chatbot Interface", implemented=True)
register(21, "Offline Node & Local Caching", implemented=True)
register(22, "Interactive Symptom Tracker", implemented=True)
register(23, "Verified Home Remedies & Traditional Tips", implemented=True)
register(24, "Doctor Feedback Loop & Logging", implemented=True)
register(25, "Alternative Treatment & Lifestyle Options", implemented=True)
register(26, "Regulatory Audit & Compliance Logging", implemented=True)

# Nodes whose heavy ML runtimes are integration stubs on lightweight deployments
register(1, "Audio Processing & Regional Language STT", implemented=False)
register(3, "Custom Reader & Processing", implemented=True)  # text native; PDF/DOCX optional
register(4, "Handwritten Prescription OCR Engine", implemented=False)
