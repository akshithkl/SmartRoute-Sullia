import json
import time
import socket
import ssl
from urllib import request, error
from typing import Optional, Tuple
from pathlib import Path
from datetime import datetime, timezone

from django.core.management.base import BaseCommand
from django.conf import settings

from transit.models import Route


def _ors_distance_duration(lon1: float, lat1: float, lon2: float, lat2: float, api_key: str, timeout: int = 10) -> Optional[Tuple[float, float]]:
    """Return (distance_km, duration_min) using ORS directions API for a pair."""
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
    help = "Use OpenRouteService to recompute and store real road distances for each Route edge."

    def add_arguments(self, parser):
        parser.add_argument("--sleep", type=float, default=0.2, help="Seconds to sleep between ORS calls (default 0.2)")
        parser.add_argument("--limit", type=int, default=0, help="Limit number of edges to update (0 = all)")
        parser.add_argument("--dry", action="store_true", help="Dry run: do not write to DB")
        parser.add_argument("--skip-existing", action="store_true", help="Skip routes with distance already set (> 0)")
        parser.add_argument("--timeout", type=float, default=10.0, help="Per-request timeout in seconds (default 10)")
        parser.add_argument("--retries", type=int, default=1, help="Retries per edge on failure (default 1)")

    def handle(self, *args, **opts):
        api_key = getattr(settings, "OPENROUTESERVICE_API_KEY", "")
        if not api_key:
            self.stderr.write(self.style.ERROR("OPENROUTESERVICE_API_KEY is not set"))
            return

        sleep_s: float = opts["sleep"]
        limit: int = opts["limit"]
        dry: bool = opts["dry"]
        timeout_s: float = float(opts.get("timeout", 10.0))
        retries: int = max(0, int(opts.get("retries", 1)))

        qs = Route.objects.select_related("start_stop", "end_stop").all()
        if opts.get("skip_existing"):
            qs = qs.filter(distance__lte=0) | qs.filter(distance__isnull=True)
        if limit > 0:
            qs = qs[:limit]

        total = qs.count() if hasattr(qs, 'count') else 0
        updated = 0
        skipped = 0
        for idx, r in enumerate(qs, start=1):
            pair: Optional[Tuple[float, float]] = None
            attempts = 0
            while attempts <= retries and pair is None:
                pair = _ors_distance_duration(
                    r.start_stop.longitude,
                    r.start_stop.latitude,
                    r.end_stop.longitude,
                    r.end_stop.latitude,
                    api_key,
                    timeout=int(timeout_s),
                )
                if pair is None and attempts < retries and sleep_s > 0:
                    time.sleep(sleep_s)
                attempts += 1

            if not pair:
                skipped += 1
            else:
                d_km, dur_min = pair
                if not dry:
                    r.distance = d_km
                    r.duration = dur_min
                    r.save(update_fields=["distance", "duration"])  # commit per-edge
                updated += 1
            if total:
                if idx % 10 == 0:
                    self.stdout.write(f"Processed {idx}/{total}... updated={updated}, skipped={skipped}")
            if sleep_s > 0:
                time.sleep(sleep_s)

        # Write stats file for admin visibility
        try:
            data_dir = Path("transit") / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            stats_path = data_dir / "ors_stats.json"
            payload = {
                "updated": updated,
                "skipped": skipped,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            with stats_path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        self.stdout.write(self.style.SUCCESS(f"Route edges updated: {updated}, skipped: {skipped}"))
