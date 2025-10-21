from django.shortcuts import render
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import json
from pathlib import Path

from .models import BusStop, Route
from .serializers import BusStopSerializer, RouteSerializer
from .utils import dijkstra_shortest_path, ors_directions_for_stops


def map_view(request):
    """Render the main map page with the Google Maps API key in context."""
    return render(request, "transit/map.html", {
        "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
    })


@api_view(["GET"])
def list_bus_stops(request):
    """Return all bus stops for marker rendering and selects."""
    # Exclude null or whitespace-only names and any A/B/C demo variants from appearing on the map
    qs = BusStop.objects.all()
    qs = qs.exclude(name__isnull=True).exclude(name__regex=r"^\s*$")
    # Case-insensitive regex to exclude: A, B, C, Stop A/B/C, sto a/stob/stoc, stopa/stopb/stopc, with optional spaces
    qs = qs.exclude(name__regex=r"(?i)^\s*(?:a|b|c|stop\s*a|stop\s*b|stop\s*c|sto\s*a|stob|stoc|stopa|stopb|stopc)\s*$")
    stops = qs.order_by("name")
    data = BusStopSerializer(stops, many=True).data
    return Response(data)


@api_view(["GET"])
def shortest_route(request):
    """Compute shortest route between two stops using Dijkstra's algorithm.

    Query params:
    - origin: BusStop id
    - destination: BusStop id
    """
    try:
        origin = int(request.query_params.get("origin"))
        destination = int(request.query_params.get("destination"))
    except (TypeError, ValueError):
        return Response({"detail": "origin and destination are required integer ids"}, status=status.HTTP_400_BAD_REQUEST)

    result = dijkstra_shortest_path(origin, destination)
    if result is None:
        return Response({"detail": "No path found between the selected stops"}, status=status.HTTP_404_NOT_FOUND)

    # Optionally enrich with OpenRouteService geometry and real-world distance/time
    ors = ors_directions_for_stops(result.get("stops", []))
    if ors:
        result["ors"] = ors

    return Response(result)


@api_view(["GET"])
def list_routes(request):
    """Return all route edges with nested stops for base map rendering."""
    routes = Route.objects.select_related("start_stop", "end_stop").all()
    data = RouteSerializer(routes, many=True).data
    return Response(data)


@api_view(["GET"])
def stats(request):
    """Return counts and latest ORS update stats.

    - nodes: BusStop count
    - edges: Route count
    - ors: {updated, skipped, timestamp} if available from transit/data/ors_stats.json
    """
    nodes = BusStop.objects.count()
    edges = Route.objects.count()
    stats_path = Path("transit") / "data" / "ors_stats.json"
    ors_info = None
    if stats_path.exists():
        try:
            with stats_path.open("r", encoding="utf-8") as f:
                ors_info = json.load(f)
        except Exception:
            ors_info = None
    return Response({
        "nodes": nodes,
        "edges": edges,
        "ors": ors_info,
    })
