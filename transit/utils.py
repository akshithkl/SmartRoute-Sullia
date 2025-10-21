# Utilities for shortest path calculation using Dijkstra's algorithm
# This module builds a graph from Route edges and computes the optimal path between two BusStops.
from __future__ import annotations
from typing import Dict, List, Tuple, Optional
import heapq
import os
import json
import time
from urllib import request, error

from django.conf import settings

from .models import Route, BusStop


def build_graph() -> Dict[int, List[Tuple[int, float]]]:
    """
    Build an adjacency list graph from Route entries.
    Each edge is directed from start_stop -> end_stop with a weight equal to distance.
    """
    graph: Dict[int, List[Tuple[int, float]]] = {}
    for edge in Route.objects.select_related("start_stop", "end_stop").all():
        u = edge.start_stop_id
        v = edge.end_stop_id
        w = float(edge.distance)
        graph.setdefault(u, []).append((v, w))
        # If your network is undirected, you can also add reverse edges here.
        # graph.setdefault(v, []).append((u, w))
    return graph


def dijkstra_shortest_path(origin_id: int, destination_id: int) -> Optional[Dict[str, object]]:
    """
    Compute the shortest path between two BusStops using Dijkstra.
    Returns a dict with path (list of stop IDs), total_distance, and stops (detailed list) if reachable.
    """
    if origin_id == destination_id:
        stop = BusStop.objects.get(pk=origin_id)
        return {
            "path": [origin_id],
            "total_distance": 0.0,
            "stops": [
                {
                    "id": stop.id,
                    "name": stop.name,
                    "latitude": stop.latitude,
                    "longitude": stop.longitude,
                }
            ],
        }

    graph = build_graph()

    # Distances map and predecessor map for path reconstruction
    dist: Dict[int, float] = {origin_id: 0.0}
    prev: Dict[int, Optional[int]] = {origin_id: None}

    # Min-heap priority queue of (distance, node)
    heap: List[Tuple[float, int]] = [(0.0, origin_id)]

    visited: set[int] = set()

    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)

        if u == destination_id:
            break

        for v, w in graph.get(u, []):
            alt = d + w
            if v not in dist or alt < dist[v]:
                dist[v] = alt
                prev[v] = u
                heapq.heappush(heap, (alt, v))

    if destination_id not in dist:
        return None

    # Reconstruct path from destination back to origin
    path_ids: List[int] = []
    cur: Optional[int] = destination_id
    while cur is not None:
        path_ids.append(cur)
        cur = prev.get(cur)
    path_ids.reverse()

    # Fetch detailed stop info in the found order
    stops_qs = BusStop.objects.filter(id__in=path_ids)
    stops_by_id = {s.id: s for s in stops_qs}
    ordered_stops = [
        {
            "id": sid,
            "name": stops_by_id[sid].name,
            "latitude": stops_by_id[sid].latitude,
            "longitude": stops_by_id[sid].longitude,
        }
        for sid in path_ids
    ]

    # Optionally compute total duration if per-edge durations are available
    total_duration_min: Optional[float] = None
    try:
        edge_pairs = list(zip(path_ids, path_ids[1:]))
        if edge_pairs:
            routes = Route.objects.filter(
                start_stop_id__in=[u for u, _ in edge_pairs],
                end_stop_id__in=[v for _, v in edge_pairs],
            )
            # Build quick lookup for (u,v) -> duration
            dur_map: Dict[tuple, Optional[float]] = {}
            for r in routes:
                dur_map[(r.start_stop_id, r.end_stop_id)] = r.duration
            acc = 0.0
            durations_present = True
            for u, v in edge_pairs:
                dval = dur_map.get((u, v))
                if dval is None:
                    durations_present = False
                    break
                acc += float(dval)
            if durations_present:
                total_duration_min = round(acc, 2)
    except Exception:
        total_duration_min = None

    result = {
        "path": path_ids,
        "total_distance": float(dist[destination_id]),
        "stops": ordered_stops,
    }
    if total_duration_min is not None:
        result["total_duration_min"] = total_duration_min
    return result


# ---------- OpenRouteService helpers ----------

def _ors_request(url: str, payload: dict, api_key: str, timeout: int = 20) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": api_key,
    }, method="POST")
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ors_directions_for_stops(stops: List[Dict[str, object]], profile: str = "driving-car") -> Optional[Dict[str, object]]:
    """
    Call OpenRouteService to compute a route for the given ordered stops.
    Returns dict with fields: geojson (feature collection), distance_km, duration_min.
    """
    api_key = getattr(settings, "OPENROUTESERVICE_API_KEY", "")
    if not api_key or not stops or len(stops) < 2:
        return None

    # ORS expects [lng, lat]
    coordinates = [[float(s["longitude"]), float(s["latitude"])] for s in stops]
    url = f"https://api.openrouteservice.org/v2/directions/{profile}/geojson"
    payload = {
        "coordinates": coordinates,
        "instructions": False,
    }
    try:
        data = _ors_request(url, payload, api_key)
    except error.HTTPError as e:
        return None
    except error.URLError:
        return None

    # Parse summary
    try:
        features = data.get("features", [])
        if not features:
            return None
        props = features[0].get("properties", {})
        summary = props.get("summary", {})
        distance_m = float(summary.get("distance", 0.0))
        duration_s = float(summary.get("duration", 0.0))
        return {
            "geojson": data,
            "distance_km": round(distance_m / 1000.0, 3),
            "duration_min": round(duration_s / 60.0, 1),
        }
    except Exception:
        return None
