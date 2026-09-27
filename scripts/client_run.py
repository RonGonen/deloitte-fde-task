"""Replay an investment manager's session against the running server and save the transcript.

Usage:
    python scripts/client_run.py [--url http://127.0.0.1:8000] [--provider claude_cli|anthropic|rules] [--out docs/client_run_transcript.json]

Each turn is sent in one conversation (same session id) so follow-ups exercise the memory. The
script prints a compact log and writes the full JSON transcript plus a markdown rendering.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

SCENARIO = [
    ("INV-01", "Which airports in New England are strong candidates for terminal expansion?", "PDF question 1: ranked screen with method and caveats"),
    ("INV-02", "Why is the first one ranked above the second?", "Follow-up: explain drivers using previous result"),
    ("INV-03", "What if I ignore scale?", "Sensitivity: re-rank with scale weight zero"),
    ("INV-04", "Tell me about the second one, including its forecast to 2035.", "Ordinal follow-up + forecast"),
    ("INV-05", "Compare LA and Santa Ana airport congestion levels.", "PDF question 2: congestion comparison"),
    ("INV-06", "Add SFO to that comparison.", "Follow-up: extend comparison set"),
    ("INV-07", "Which of these are slot constrained?", "Structural constraint question on active set"),
    ("INV-08", "What is the percentage of long haul flights out of Anchorage airport?", "PDF question 3: long-haul share with scoping"),
    ("INV-09", "What about cargo at Anchorage?", "Scope boundary: cargo not measurable"),
    ("INV-10", "What is the unmet flight demand in SFO airport and why?", "PDF question 4: unmet demand indicator + reasons"),
    ("INV-11", "How confident are you in that, and what data would change the answer?", "Uncertainty communication"),
    ("INV-12", "What's the ROI of expanding BOS?", "Data gap: must not invent returns"),
    ("INV-13", "Top 5 expansion candidates in Texas with at least 1 million passengers.", "Generalization to another region with a volume floor"),
    ("INV-14", "Compare Boston and Providence congestion.", "City names instead of codes"),
    ("INV-15", "Any delays at SFO right now?", "Live status"),
    ("INV-16", "How is the expansion score calculated?", "Methodology transparency"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--provider", default=None, help="rules | claude_cli | anthropic (default: server setting)")
    parser.add_argument("--out", default="docs/client_run_transcript.json")
    parser.add_argument("--only", nargs="*", default=None, help="scenario ids to run")
    args = parser.parse_args()

    client = httpx.Client(base_url=args.url, timeout=httpx.Timeout(30.0, read=600.0))
    health = client.get("/api/health").json()
    print(f"server ready: provider={health['provider']} model={health['model']} universe={health['universe_size']}")
    session_id = None
    transcript = []
    for sid, question, purpose in SCENARIO:
        if args.only and sid not in args.only:
            continue
        payload = {"message": question, "session_id": session_id}
        if args.provider:
            payload["provider"] = args.provider
        t0 = time.time()
        response = client.post("/api/chat", json=payload)
        elapsed = time.time() - t0
        if response.status_code != 200:
            print(f"{sid}: HTTP {response.status_code} {response.text[:200]}")
            transcript.append({"id": sid, "question": question, "purpose": purpose, "error": response.text, "status": response.status_code})
            continue
        body = response.json()
        session_id = body["session_id"]
        tools = [t["tool"] for t in body["tool_results"]]
        print(f"{sid}: mode={body['mode']} tools={tools} {elapsed:.1f}s warnings={body['warnings']}")
        transcript.append({"id": sid, "question": question, "purpose": purpose, "mode": body["mode"], "model": body.get("model"),
                           "tools": tools, "latency_s": round(elapsed, 1), "warnings": body["warnings"], "text": body["text"],
                           "sources": body["sources"], "caveats": body["caveats"],
                           "confidence": [t.get("confidence", {}).get("level") for t in body["tool_results"]]})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(transcript, indent=2, ensure_ascii=False))
    md = out.with_suffix(".md")
    lines = [f"# Client run transcript ({health['provider']}, {health['model']})", ""]
    for t in transcript:
        lines += [f"## {t['id']}: {t['question']}", f"*Purpose:* {t['purpose']}", ""]
        if "error" in t:
            lines += [f"**ERROR** HTTP {t['status']}: {t['error']}", ""]
            continue
        lines += [f"*mode={t['mode']} tools={t['tools']} latency={t['latency_s']}s confidence={t['confidence']} warnings={t['warnings']}*", "", t["text"], ""]
    md.write_text("\n".join(lines))
    print(f"wrote {out} and {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
