#!/usr/bin/env python3
"""Healthspan Signals demo server.

The ten residents and all incoming signals are sample data. This prototype
is not a medical device, does not diagnose conditions, and must not be used for
emergencies. The rolling data window exists only in memory.
"""

from __future__ import annotations

import json
import math
import random
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

APP_DIR = Path(__file__).parent / "app"
KNOWLEDGE_FILE = Path(__file__).parent / "knowledge" / "wellness_reference.json"
HOST, PORT, REFRESH_SECONDS, MAX_SAMPLES = "127.0.0.1", 8787, 12, 60

with KNOWLEDGE_FILE.open(encoding="utf-8") as knowledge_handle:
    WELLNESS_REFERENCE: dict[str, Any] = json.load(knowledge_handle)

AGES = (75, 77, 79, 82, 84, 86, 88, 90, 93, 96)
DEMO_NAMES = ("Maya", "Eleanor", "Thomas", "Ruth", "Samuel", "Lila", "Arthur", "Nora", "Victor", "Beatrice")
RESIDENTS = [
    {
        "id": f"demo-{index:02d}",
        "label": name,
        "age": age,
        "baseline": {
            "sleep_hours": round(7.7 - index * 0.08, 1), "resting_hr": 61 + index,
            "daily_steps": 6100 - index * 260, "systolic_bp": 116 + index,
            "diastolic_bp": 70 + index // 2, "glucose": 91 + index,
            "hrv_ms": 38 - index,
        },
    }
    for index, (name, age) in enumerate(zip(DEMO_NAMES, AGES), start=1)
]
RESIDENT_BY_ID = {resident["id"]: resident for resident in RESIDENTS}
samples = {resident["id"]: deque(maxlen=MAX_SAMPLES) for resident in RESIDENTS}
lock = threading.Lock()
rng = random.Random(20260915)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def routine_consistency(sample: dict[str, Any], baseline: dict[str, float]) -> int:
    """Transparent demonstration score: consistency with a personal baseline only."""
    sleep_delta = abs(float(sample["sleep_hours"]) - baseline["sleep_hours"])
    hr_delta = abs(float(sample["resting_hr"]) - baseline["resting_hr"])
    movement_ratio = float(sample["movement_minutes"]) / 45
    return round(clamp(100 - sleep_delta * 9 - hr_delta * 1.4 - abs(1 - movement_ratio) * 12, 0, 100))


def new_sample(resident: dict[str, Any]) -> dict[str, Any]:
    profile = resident["baseline"]
    tick = len(samples[resident["id"]])
    resident_number = int(resident["id"].split("-")[-1])
    phase = resident_number / 3
    movement = clamp(24 + 18 * math.sin(tick / 5 + phase) + rng.gauss(0, 3), 4, 70)
    sleep = clamp(profile["sleep_hours"] + 0.35 * math.sin(tick / 9 + phase) + rng.gauss(0, 0.12), 5.5, 9.2)
    resting_hr = clamp(profile["resting_hr"] + 3 * math.sin(tick / 8 + phase) + rng.gauss(0, 1.2), 54, 94)

    # Deliberate sample variety for the color-scale demonstration.
    demo_cycle = (resident_number + tick) % 11
    if demo_cycle == 0:
        sleep = clamp(sleep - 2.5, 4.5, 9.2); resting_hr = clamp(resting_hr + 15, 54, 110); movement = 4
    elif demo_cycle in (4, 5):
        sleep = clamp(sleep - 1.2, 5.0, 9.2); resting_hr = clamp(resting_hr + 6, 54, 105); movement = 14
    systolic = clamp(profile["systolic_bp"] + 4 * math.sin(tick / 7 + phase) + rng.gauss(0, 1.5), 85, 185)
    diastolic = clamp(profile["diastolic_bp"] + 3 * math.sin(tick / 7 + phase) + rng.gauss(0, 1.1), 50, 120)
    glucose = clamp(profile["glucose"] + 7 * math.sin(tick / 10 + phase) + rng.gauss(0, 2.5), 55, 220)
    hrv = clamp(profile["hrv_ms"] + 6 * math.sin(tick / 6 + phase) + rng.gauss(0, 2), 8, 95)
    item: dict[str, Any] = {
        "timestamp": now_iso(), "source": "sample", "sleep_hours": round(sleep, 1),
        "resting_hr": round(resting_hr), "movement_minutes": round(movement),
        "steps_today": round(clamp(profile["daily_steps"] * (0.35 + tick / 50) + rng.gauss(0, 120), 0, 12500)),
        "blood_pressure": f"{round(systolic)}/{round(diastolic)}", "glucose_mg_dl": round(glucose),
        "hrv_ms": round(hrv), "head_motion_balance": round(clamp(88 + rng.gauss(0, 5), 55, 100)),
        "torso_motion_balance": round(clamp(89 + rng.gauss(0, 5), 55, 100)),
        "lower_leg_motion_balance": round(clamp(86 + rng.gauss(0, 6), 50, 100)),
        "gait_pattern_consistency": round(clamp(87 + rng.gauss(0, 6), 50, 100)),
        "gesture_check_in": rng.choice(("acknowledgement", "acknowledgement", "neutral cue")),
    }
    item["routine_consistency"] = routine_consistency(item, profile)
    return item


def add_sample(resident_id: str, sample: dict[str, Any] | None = None) -> dict[str, Any]:
    resident = RESIDENT_BY_ID[resident_id]
    with lock:
        item = sample or new_sample(resident)
        samples[resident_id].append(item)
        return item


def resident_summary(resident: dict[str, Any]) -> dict[str, Any]:
    latest = samples[resident["id"]][-1]
    return {"id": resident["id"], "label": resident["label"], "age": resident["age"], "routine_consistency": latest["routine_consistency"]}


def wellness_check_in(latest: dict[str, Any], baseline: dict[str, float]) -> list[str]:
    """Return local reference-based conversation prompts; never a diagnosis or triage output."""
    guidance = WELLNESS_REFERENCE["guidance"]
    ranges = WELLNESS_REFERENCE["reference_ranges"]
    score = int(latest["routine_consistency"])
    notes = [guidance["higher_consistency"] if score >= 85 else guidance["medium_consistency"] if score >= 70 else guidance["lower_consistency"]]
    sleep = float(latest["sleep_hours"])
    sleep_reference = ranges["sleep_age_65_plus_hours"]
    if sleep < sleep_reference["lower"]:
        notes.append(f"You logged {sleep:g} hours of sleep. That is below the general {sleep_reference['label']} reference for many adults age 65+, but your own care plan and usual routine come first.")
    else:
        notes.append(f"You logged {sleep:g} hours of sleep, which sits within the general {sleep_reference['label']} reference for many adults age 65+.")

    pulse = int(latest["resting_hr"])
    pulse_reference = ranges["resting_pulse_bpm"]
    if pulse_reference["lower"] <= pulse <= pulse_reference["upper"]:
        notes.append(f"Your displayed resting pulse is {pulse} bpm, within the common {pulse_reference['label']} adult reference range when resting calmly.")
    else:
        notes.append(f"Your displayed resting pulse is {pulse} bpm, outside the common {pulse_reference['label']} adult reference range. Medication and personal health needs can change what is expected, so use your care plan and care team for interpretation.")

    systolic, diastolic = (int(value) for value in str(latest["blood_pressure"]).split("/", 1))
    bp = ranges["blood_pressure_mm_hg"]
    if systolic >= bp["severe_systolic_lower"] or diastolic >= bp["severe_diastolic_lower"]:
        bp_note = "is above the American Heart Association severe reference threshold"
    elif systolic >= bp["stage_2_systolic_lower"] or diastolic >= bp["stage_2_diastolic_lower"]:
        bp_note = "is in an AHA Stage 2 reference category"
    elif systolic >= bp["stage_1_systolic_lower"] or diastolic >= bp["stage_1_diastolic_lower"]:
        bp_note = "is in an AHA Stage 1 reference category"
    elif systolic >= bp["elevated_systolic_lower"]:
        bp_note = "is in the AHA elevated reference category"
    else:
        bp_note = "is below the AHA 120/80 mm Hg reference threshold"
    notes.append(f"Your displayed blood pressure is {systolic}/{diastolic} mm Hg, which {bp_note}. One measurement alone does not establish a condition; follow facility protocol and qualified clinical guidance.")

    glucose = int(latest["glucose_mg_dl"])
    glucose_reference = ranges["fasting_glucose_mg_dl"]
    if glucose_reference["lower"] <= glucose <= glucose_reference["upper"]:
        glucose_note = f"within the general fasting reference of {glucose_reference['label']}"
    else:
        glucose_note = f"outside the general fasting reference of {glucose_reference['label']}"
    notes.append(f"Your displayed glucose is {glucose} mg/dL, {glucose_note}. This comparison applies only if the reading was fasting; meal timing and individual care plans matter.")
    return notes[:5]


def current_state(resident_id: str) -> dict[str, Any]:
    resident = RESIDENT_BY_ID.get(resident_id, RESIDENTS[0])
    with lock:
        history = list(samples[resident["id"]])
        summaries = [resident_summary(person) for person in RESIDENTS]
    latest = history[-1]
    score = int(latest["routine_consistency"])
    return {
        "resident": {"id": resident["id"], "label": resident["label"], "age": resident["age"]},
        "latest": latest, "history": history, "baseline": resident["baseline"], "residents": summaries,
        "wellness_check_in": wellness_check_in(latest, resident["baseline"]),
        "wellness_reference": {"title": WELLNESS_REFERENCE["title"], "version": WELLNESS_REFERENCE["version"], "safety": WELLNESS_REFERENCE["safety"], "references": WELLNESS_REFERENCE["references"]},
        "status": "within_personal_pattern" if score >= 70 else "review_suggested",
        "metadata": {
            "mode": "assisted-living demonstration", "refresh_seconds": REFRESH_SECONDS,
            "retention": "memory only; rolling window clears when the server restarts",
            "disclaimer": "All profiles use sample information. This routine-consistency score is not a medical assessment, diagnosis, or emergency alert.",
        },
    }


def validate_ingest(resident_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    required = ("sleep_hours", "resting_hr", "movement_minutes", "steps_today")
    if resident_id not in RESIDENT_BY_ID:
        raise ValueError("Unknown resident.")
    if not all(key in payload for key in required):
        raise ValueError("Provide sleep_hours, resting_hr, movement_minutes, and steps_today.")
    item = {"timestamp": now_iso(), "source": "external_demo_feed", "sleep_hours": round(clamp(float(payload["sleep_hours"]), 0, 24), 1), "resting_hr": round(clamp(float(payload["resting_hr"]), 20, 240)), "movement_minutes": round(clamp(float(payload["movement_minutes"]), 0, 1440)), "steps_today": round(clamp(float(payload["steps_today"]), 0, 100000))}
    item["routine_consistency"] = routine_consistency(item, RESIDENT_BY_ID[resident_id]["baseline"])
    return item


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(APP_DIR), **kwargs)

    def end_headers(self) -> None:
        # The interface is updated frequently; always deliver the current page.
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def send_json(self, data: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            resident_id = parse_qs(parsed.query).get("resident", [RESIDENTS[0]["id"]])[0]
            self.send_json(current_state(resident_id)); return
        if parsed.path == "/api/health":
            self.send_json({"ok": True, "mode": "assisted-living demonstration"}); return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/ingest": self.send_error(HTTPStatus.NOT_FOUND); return
        try:
            resident_id = parse_qs(parsed.query).get("resident", [""])[0]
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
            if not isinstance(payload, dict): raise ValueError("JSON object required.")
            item = add_sample(resident_id, validate_ingest(resident_id, payload)); self.send_json({"accepted": True, "sample": item}, HTTPStatus.CREATED)
        except (ValueError, json.JSONDecodeError) as error:
            self.send_json({"accepted": False, "error": str(error)}, HTTPStatus.BAD_REQUEST)


def simulation_loop() -> None:
    while True:
        time.sleep(REFRESH_SECONDS)
        for resident in RESIDENTS: add_sample(resident["id"])


if __name__ == "__main__":
    for resident in RESIDENTS:
        for _ in range(18): add_sample(resident["id"])
    threading.Thread(target=simulation_loop, daemon=True).start()
    print(f"Healthspan Signals demo: http://localhost:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
