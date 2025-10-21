import json
import math
import time
import socket
import ssl
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib import request, error

from django.core.management.base import BaseCommand, CommandParser
from django.conf import settings

from transit.models import BusStop


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def ors_pair(lon1: float, lat1: float, lon2: float, lat2: float, api_key: str, timeout: int = 8) -> Optional[Tuple[float, float]]:
    """Return (distance_km, duration_min) for a pair using ORS directions API."""
    url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
    payload = {
        "coordinates": [
            [float(lon1), float(lat1)],
            [float(lon2), float(lat2)],
        ],
        "instructions": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": api_key,
    }, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            res = json.loads(resp.read().decode("utf-8"))
    except (error.HTTPError, error.URLError, socket.timeout, ssl.SSLError):
        return None

    try:
        features = res.get("features", [])
        if not features:
            return None
        summary = features[0]["properties"].get("summary", {})
        dist_km = float(summary.get("distance", 0.0)) / 1000.0
        dur_min = float(summary.get("duration", 0.0)) / 60.0
        return (dist_km, dur_min)
    except Exception:
        return None


class Command(BaseCommand):
    help = "Build an ORS-based distance/time matrix for all BusStop pairs; caches to transit/data/ors_matrix.json. Falls back to haversine when ORS fails."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--sleep", type=float, default=0.15, help="Seconds to sleep between ORS calls (default 0.15)")
        parser.add_argument("--limit", type=int, default=0, help="Limit pairs processed for testing (0 = all)")
        parser.add_argument("--dry", action="store_true", help="Dry run: compute but do not write file")
        parser.add_argument("--timeout", type=float, default=8.0, help="Per-request timeout in seconds (default 8)")
        parser.add_argument("--retries", type=int, default=1, help="Retries per pair on failure (default 1)")

    def handle(self, *args, **opts):
        api_key = getattr(settings, "OPENROUTESERVICE_API_KEY", "")
        if not api_key:
            self.stderr.write(self.style.WARNING("OPENROUTESERVICE_API_KEY is not set; will compute only haversine matrix"))

        sleep_s: float = opts["sleep"]
        limit: int = opts["limit"]
        dry: bool = opts["dry"]
        timeout_s: float = float(opts["timeout"]) if opts.get("timeout") is not None else 8.0
        retries: int = max(0, int(opts.get("retries", 1)))

        # Ensure the whole process respects a default timeout for socket operations
        try:
            socket.setdefaulttimeout(timeout_s)
        except Exception:
            pass

        stops = list(BusStop.objects.all().order_by("id"))
        n = len(stops)
        id_index = {s.id: i for i, s in enumerate(stops)}

        # Prepare results as list of entries {from, to, distance_km, duration_min, method}
        results: List[Dict[str, object]] = []

        count = 0
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                a = stops[i]
                b = stops[j]
                dist_km = None
                dur_min = None
                method = "ors"
                if api_key:
                    pair = None
                    attempts = 0
                    while attempts <= retries and pair is None:
                        pair = ors_pair(a.longitude, a.latitude, b.longitude, b.latitude, api_key, timeout=int(timeout_s))
                        if pair is None and attempts < retries and sleep_s > 0:
                            time.sleep(sleep_s)
                        attempts += 1
                else:
                    pair = None
                if pair is None:
                    # Fallback to haversine only distance
                    dist_km = haversine_km(a.latitude, a.longitude, b.latitude, b.longitude)
                    dur_min = None
                    method = "haversine"
                else:
                    dist_km, dur_min = pair
                results.append({
                    "from": a.id,
                    "to": b.id,
                    "distance_km": round(float(dist_km), 5) if dist_km is not None else None,
                    "duration_min": round(float(dur_min), 2) if dur_min is not None else None,
                    "method": method,
                })
                count += 1
                if limit and count >= limit:
                    break
                if sleep_s > 0 and api_key:
                    time.sleep(sleep_s)
            if limit and count >= limit:
                break

        if dry:
            self.stdout.write(self.style.NOTICE(f"Computed pairs: {len(results)} (dry run)"))
            return

        data_dir = Path("transit") / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        out_path = data_dir / "ors_matrix.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump({"pairs": results}, f, ensure_ascii=False)
        self.stdout.write(self.style.SUCCESS(f"Matrix written: {out_path} (pairs={len(results)})"))
