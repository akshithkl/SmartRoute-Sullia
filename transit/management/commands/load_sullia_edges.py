import math
from pathlib import Path
from typing import Dict, List, Tuple

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


# Adjacency list provided by user (stop_id -> list of connected stop_ids)
SULLIA_ADJ: Dict[int, List[int]] = {
    1: [2, 5, 7, 20],
    2: [1, 5, 6, 19],
    3: [4, 17],
    4: [3, 6, 17],
    5: [1, 2, 6, 19],
    6: [2, 4, 5, 22],
    7: [1, 8, 18],
    8: [7, 18, 11, 21],
    9: [16],
    10: [12, 15],
    11: [8, 15, 21],
    12: [10],
    13: [14, 16],
    14: [13, 17],
    15: [10, 11],
    16: [9, 13],
    17: [3, 4, 14],
    18: [7, 8],
    19: [2, 5],
    20: [1, 7],
    21: [8, 11],
    22: [6],
}


class Command(BaseCommand):
    help = "Create Route edges from the provided Sullia adjacency list; computes distances from BusStop coordinates"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--undirected",
            action="store_true",
            help="Also add reverse edges (default: off)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing Route edges before creating new ones",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        undirected = options["undirected"]
        clear = options["clear"]

        # Build a mapping from sequential stop index (1..N) to BusStop by ordering by name used during import
        # Prefer a deterministic mapping by reading the original CSV order if present
        # Here, we match by name against known list imported previously.
        # We assume that BusStops imported from CSV are exactly those and names are unique.
        stops = list(BusStop.objects.all().order_by("name"))
        if len(stops) < 22:
            self.stderr.write(self.style.WARNING("Expected at least 22 stops to map IDs; found %d" % len(stops)))

        # Build a name -> BusStop map for lookups
        name_to_stop: Dict[str, BusStop] = {s.name: s for s in stops}

        # If the import used the provided CSV, we can also map by index using a known ordered list of names.
        ordered_names = [
            "KSRTC Bus Stand Sullia",
            "Sullia Court Bus Stop",
            "Puthila Bus Stop",
            "Gandhinagar Bus Stop",
            "Sullia Town Panchayath",
            "Govt First Grade College",
            "Balemakki Bus Stop",
            "Subramanya Road Junction",
            "Guthigar Bus Stop",
            "Aranthodu Bus Stop",
            "Mandekole Bus Stop",
            "Peraje Bus Stop",
            "Jalsoor Bus Stop",
            "Aletti Bus Stop",
            "Ajjavara Bus Stop",
            "Peral Bus Stop",
            "Ainakal Bus Stop",
            "Kallugundi Bus Stop",
            "Odabai Bus Stop",
            "Srirampete Bus Stop",
            "Duggaldka Bus Stop",
            "Kudpaje Bus Stop",
        ]
        id_to_stop: Dict[int, BusStop] = {}
        for idx, nm in enumerate(ordered_names, start=1):
            bs = name_to_stop.get(nm)
            if not bs:
                self.stderr.write(self.style.ERROR(f"Missing BusStop in DB for name: {nm}. Did you run import_sullia_csv?"))
                return
            id_to_stop[idx] = bs

        if clear:
            deleted, _ = Route.objects.all().delete()
            self.stdout.write(self.style.NOTICE(f"Cleared existing routes: {deleted}"))

        created = 0
        skipped = 0
        for u, nbrs in SULLIA_ADJ.items():
            if u not in id_to_stop:
                self.stderr.write(self.style.WARNING(f"Unknown stop id {u}; skipping"))
                continue
            su = id_to_stop[u]
            for v in nbrs:
                if v not in id_to_stop:
                    self.stderr.write(self.style.WARNING(f"Unknown neighbor id {v}; skipping"))
                    continue
                sv = id_to_stop[v]
                dist = haversine_km(su.latitude, su.longitude, sv.latitude, sv.longitude)
                _, created_flag = Route.objects.get_or_create(
                    start_stop=su,
                    end_stop=sv,
                    defaults={"distance": dist},
                )
                created += int(created_flag)
                if undirected:
                    _, created_flag2 = Route.objects.get_or_create(
                        start_stop=sv,
                        end_stop=su,
                        defaults={"distance": dist},
                    )
                    created += int(created_flag2)
                else:
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(f"Routes created/kept: {created}. Skipped (existing or directed-only counts): {skipped}"))
