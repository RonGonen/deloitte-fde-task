"""Build/refresh the committed data snapshots from public sources.

Usage (from the repo root, inside the virtualenv):
    python scripts/refresh_data.py                 # TAF compact + delay cause + on-time months already cached
    python scripts/refresh_data.py --ontime 2026-05 2026-06 2026-07   # also download these on-time months (slow)

Snapshots written to data/snapshots/:
    taf_compact.csv, delay_cause_12m.csv, routes_by_origin.csv, ontime_origin_metrics.csv, manifest.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.sources import bts_delay_cause, bts_ontime, faa_enplanements, taf  # noqa: E402
from app.sources.cache import USER_AGENT  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_manifest() -> dict:
    path = settings.snapshot_dir / "manifest.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save_manifest(manifest: dict) -> None:
    (settings.snapshot_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def refresh_taf(manifest: dict) -> None:
    print("TAF: loading FAA enplanement universe for the airport list ...")
    faa = faa_enplanements.load_faa_enplanements()
    lids = set(faa.frame.loc[faa.frame["service_level"].isin(["P", "CS"]), "lid"])
    print(f"TAF: building compact table for {len(lids)} P/CS airports (this parses ~15 MB of Excel, be patient) ...")
    t0 = time.time()
    result = taf.download_and_build(lids)
    out = settings.snapshot_dir / "taf_compact.csv"
    result.frame.to_csv(out, index=False)
    manifest["taf"] = {"retrieved_at": result.retrieved_at, "edition": result.edition, "rows": int(len(result.frame)),
                       "last_actual_year": result.last_actual_year, "last_forecast_year": result.last_forecast_year,
                       "url": taf.TAF_ZIP_URL}
    manifest["faa_enplanements_fallback"] = {"source_url": faa.source_url, "latest_year": faa.latest_year,
                                             "preliminary": faa.preliminary, "retrieved_at": faa.retrieved_at}
    print(f"TAF: wrote {out} ({len(result.frame)} rows) in {time.time() - t0:.0f}s")


def refresh_delay_cause(manifest: dict) -> None:
    print("BTS delay cause: downloading trailing 12 months ...")
    result = bts_delay_cause.load_delay_cause()
    out = settings.snapshot_dir / "delay_cause_12m.csv"
    result.frame.to_csv(out, index=False)
    manifest["delay_cause"] = {"retrieved_at": result.retrieved_at, "period": result.period_label, "rows": int(len(result.frame)),
                               "airports": int(result.frame["airport"].nunique()), "url": bts_delay_cause.PAGE_URL}
    print(f"BTS delay cause: wrote {out} ({result.period_label}, {result.frame['airport'].nunique()} airports)")


def download_ontime_month(year: int, month: int) -> Path:
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    target = settings.cache_dir / f"ontime_{year}_{month}.zip"
    url = bts_ontime.ontime_url(year, month)
    if target.exists() and target.stat().st_size > 1_000_000:
        print(f"on-time {year}-{month:02d}: using cached {target.name}")
        return target
    print(f"on-time {year}-{month:02d}: downloading {url} (~33 MB, the BTS server is slow) ...")
    t0 = time.time()
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=httpx.Timeout(60.0, read=600.0), follow_redirects=True) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(target, "wb") as handle:
                for chunk in response.iter_bytes(1 << 16):
                    handle.write(chunk)
    print(f"on-time {year}-{month:02d}: downloaded {target.stat().st_size / 1e6:.1f} MB in {time.time() - t0:.0f}s")
    return target


def refresh_ontime(manifest: dict, months: list) -> None:
    routes_frames, metric_frames, done = [], [], []
    for spec in months:
        year, month = (int(x) for x in spec.split("-"))
        try:
            path = download_ontime_month(year, month)
            frame = bts_ontime.read_month(path)
        except Exception as exc:  # noqa: BLE001 - report and continue with other months
            print(f"on-time {spec}: FAILED ({exc})")
            continue
        routes, metrics = bts_ontime.aggregate_month(frame)
        routes_frames.append(routes)
        metric_frames.append(metrics)
        done.append(spec)
        print(f"on-time {spec}: {len(frame)} flights, {routes['origin'].nunique()} origins")
    if not done:
        print("on-time: nothing processed")
        return
    routes_all = pd.concat(routes_frames, ignore_index=True)
    metrics_all = pd.concat(metric_frames, ignore_index=True)
    routes_all.to_csv(settings.snapshot_dir / "routes_by_origin.csv", index=False)
    metrics_all.to_csv(settings.snapshot_dir / "ontime_origin_metrics.csv", index=False)
    manifest["ontime"] = {"retrieved_at": now(), "months": done, "route_rows": int(len(routes_all)),
                          "url_pattern": bts_ontime.PREZIP_URL}
    print(f"on-time: wrote routes_by_origin.csv ({len(routes_all)} rows) and ontime_origin_metrics.csv ({len(metrics_all)} rows)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-taf", action="store_true")
    parser.add_argument("--skip-delay", action="store_true")
    parser.add_argument("--ontime", nargs="*", default=None, metavar="YYYY-MM",
                        help="on-time months to include; default: every ontime_*.zip already in the cache")
    args = parser.parse_args()
    settings.snapshot_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    if not args.skip_taf:
        refresh_taf(manifest)
        save_manifest(manifest)
    if not args.skip_delay:
        refresh_delay_cause(manifest)
        save_manifest(manifest)
    months = args.ontime
    if months is None:
        months = sorted(f"{p.stem.split('_')[1]}-{int(p.stem.split('_')[2]):02d}" for p in settings.cache_dir.glob("ontime_*_*.zip")
                        if p.stat().st_size > 1_000_000)
    if months:
        refresh_ontime(manifest, months)
        save_manifest(manifest)
    print("done. manifest:", json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
