from django.db import models


class BusStop(models.Model):
    name = models.CharField(max_length=200)
    latitude = models.FloatField()
    longitude = models.FloatField()

    def __str__(self) -> str:
        return self.name


class Route(models.Model):
    start_stop = models.ForeignKey(BusStop, on_delete=models.CASCADE, related_name='routes_from')
    end_stop = models.ForeignKey(BusStop, on_delete=models.CASCADE, related_name='routes_to')
    distance = models.FloatField(help_text="Distance in kilometers")
    duration = models.FloatField(null=True, blank=True, help_text="Estimated travel time in minutes (ORS)")

    class Meta:
        unique_together = ('start_stop', 'end_stop')

    def __str__(self) -> str:
        return f"{self.start_stop} -> {self.end_stop} ({self.distance} km)"
