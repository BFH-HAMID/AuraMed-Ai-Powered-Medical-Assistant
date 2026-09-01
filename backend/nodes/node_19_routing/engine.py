"""Node 19 — Emergency Proximity Routing.

Nearest-facility ranking by haversine distance over the local facility
directory (offline). Ranks emergency departments for the patient's condition
(e.g. stroke → neuroscience center, chest pain → cardiac center), plus
ambulance dispatch numbers.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from backend.config import REPO_ROOT
from backend.core.audit import log_action
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode

_PATH = Path(REPO_ROOT) / "backend" / "data" / "facilities.json"

# Condition -> preferred specialties
_SPECIALTY_MAP = {
    "chest_pain": ["cardiology", "cardiac_surgery"],
    "stroke": ["stroke", "neurology", "neurosurgery"],
    "child": ["pediatrics", "neonatology"],
    "pregnancy": ["obstetrics"],
    "trauma": ["trauma"],
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class EmergencyRoutingEngine(BaseNode):
    node_id = 19
    node_name = "Emergency Proximity Routing"
    implemented = True

    def __init__(self) -> None:
        self._facilities = json.loads(_PATH.read_text(encoding="utf-8"))["facilities"]

    def route(self, lat: float, lon: float, condition: str = "general", language: str = "en") -> dict:
        wanted = _SPECIALTY_MAP.get(condition, [])
        ranked = []
        for fac in self._facilities:
            dist = haversine_km(lat, lon, fac["lat"], fac["lon"])
            spec_match = len(set(fac.get("specialties", [])) & set(wanted))
            score = dist - (25 if spec_match else 0) - (10 if fac.get("has_emergency") else 0)
            ranked.append((score, dist, spec_match, fac))
        ranked.sort(key=lambda x: x[0])

        bn = language.startswith("bn")
        hospitals = [
            {
                "name": f["name_bn"] if bn else f["name"],
                "type": f["type"],
                "distance_km": round(dist, 1),
                "specialty_match": bool(spec),
                "phone": f["phone"],
                "open_247": f.get("open_247", False),
                "directions_url": f"https://www.openstreetmap.org/?mlat={f['lat']}&mlon={f['lon']}#map=17/{f['lat']}/{f['lon']}",
            }
            for _, dist, spec, f in ranked
            if f["type"] != "ambulance"
        ][:3]
        ambulances = [
            {"name": f["name_bn"] if bn else f["name"], "phone": f["phone"],
             "distance_km": round(haversine_km(lat, lon, f["lat"], f["lon"]), 1)}
            for f in self._facilities if f["type"] == "ambulance"
        ]

        result = {
            "condition": condition,
            "nearest_emergency_departments": hospitals,
            "ambulance_contacts": ambulances,
            "national_emergency_number": "999",
            "advice_en": "Call 999 now; go to the nearest facility matched for the condition. Do not drive yourself if dizzy, in severe pain or short of breath.",
            "advice_bn": "এখনই ৯৯৯-এ কল করুন; অবস্থার উপযোগী নিকটস্থ কেন্দ্রে যান। মাথা ঘোরালে, প্রচণ্ড ব্যথা বা শ্বাসকষ্ট থাকলে নিজে গাড়ি চালাবেন না।",
        }
        log_action(
            self.node_id, "emergency_routing",
            details={"condition": condition, "results": len(hospitals)},
            risk_level="red",
        )
        return result

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        return self.route(
            float(payload["lat"]),
            float(payload["lon"]),
            payload.get("condition", "general"),
            payload.get("language", "en"),
        )


routing_engine = EmergencyRoutingEngine()
