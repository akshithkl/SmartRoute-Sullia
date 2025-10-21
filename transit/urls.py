from django.urls import path
from . import views

urlpatterns = [
    # Frontend map page
    path("", views.map_view, name="map"),

    # API endpoints
    path("api/stops/", views.list_bus_stops, name="list_bus_stops"),
    path("api/shortest-route/", views.shortest_route, name="shortest_route"),
    path("api/routes/", views.list_routes, name="list_routes"),
    path("api/stats/", views.stats, name="stats"),
]
