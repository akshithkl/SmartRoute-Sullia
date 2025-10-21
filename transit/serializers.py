from rest_framework import serializers
from .models import BusStop, Route


class BusStopSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusStop
        fields = ["id", "name", "latitude", "longitude"]


class RouteSerializer(serializers.ModelSerializer):
    start_stop = BusStopSerializer(read_only=True)
    end_stop = BusStopSerializer(read_only=True)

    class Meta:
        model = Route
        fields = ["id", "start_stop", "end_stop", "distance", "duration"]
