from django.contrib import admin
from .models import BusStop, Route


@admin.register(BusStop)
class BusStopAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "latitude", "longitude")
    search_fields = ("name",)


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ("id", "start_stop", "end_stop", "distance")
    list_filter = ("start_stop", "end_stop")
