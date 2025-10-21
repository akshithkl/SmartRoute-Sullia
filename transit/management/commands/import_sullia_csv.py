import csv
import math
from pathlib import Path
from typing import List, Tuple

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from transit.models import BusStop, Route


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


class Command(BaseCommand):
    help = "Import Sullia bus stops from a CSV and optionally generate k-nearest neighbor routes"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "csv_path",
            nargs="?",
            default=str(Path("transit") / "data" / "sullia_stops.csv"),
            help="Path to the CSV file (default: transit/data/sullia_stops.csv)",
        )
        parser.add_argument(
            "--make-routes",
            action="store_true",
            help="Also generate k-nearest neighbor edges between stops",
        )
        parser.add_argument(
            "--k",
            type=int,
            default=3,
            help="Number of nearest neighbors per stop to connect (default: 3)",
        )
        parser.add_argument(
            "--undirected",
            action="store_true",
            help="Create reverse edges too (i.e., undirected graph)",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"]).resolve()
        # Django converts hyphenated flags (e.g., --make-routes) to underscore keys in options
        make_routes = options.get("make_routes", False)
        k = options["k"]
        undirected = options["undirected"]

        if not csv_path.exists():
            self.stderr.write(self.style.ERROR(f"CSV not found: {csv_path}"))
            return

        self.stdout.write(self.style.NOTICE(f"Reading: {csv_path}"))

        # Import stops
        created = 0
        updated = 0
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    name = row.get("stop_name") or row.get("name")
                    lat = float(row["latitude"])
                    lng = float(row["longitude"]) 
                except Exception as exc:
                    self.stderr.write(self.style.WARNING(f"Skipping row due to parse error: {row} ({exc})"))
                    continue

                stop, is_created = BusStop.objects.update_or_create(
                    name=name,
                    defaults={"latitude": lat, "longitude": lng},
                )
                if is_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(f"Stops imported. Created: {created}, Updated: {updated}"))

        if not make_routes:
            return

        # Build all pair distances and connect k nearest per stop
        stops = list(BusStop.objects.all())
        id_to_stop = {s.id: s for s in stops}
        coords = [(s.id, s.latitude, s.longitude) for s in stops]

        edges: List[Tuple[int, int, float]] = []
        for sid, slat, slng in coords:
            # compute distances to others
            dists: List[Tuple[float, int]] = []
            for tid, tlat, tlng in coords:
                if sid == tid:
                    continue
                d = haversine_km(slat, slng, tlat, tlng)
                dists.append((d, tid))
            dists.sort(key=lambda x: x[0])
            for d, tid in dists[: max(k, 0)]:
                edges.append((sid, tid, d))
                if undirected:
                    edges.append((tid, sid, d))

        # Create Route objects (ignore duplicates via get_or_create)
        created_routes = 0
        for u, v, dist in edges:
            start = id_to_stop[u]
            end = id_to_stop[v]
            _, r_created = Route.objects.get_or_create(
                start_stop=start,
                end_stop=end,
                defaults={"distance": dist},
            )
            if r_created:
                created_routes += 1
        self.stdout.write(self.style.SUCCESS(f"Routes generated: {created_routes}"))
