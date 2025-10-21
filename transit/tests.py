from django.test import TestCase, override_settings, Client

from .models import BusStop, Route
from . import utils


class DijkstraTests(TestCase):
    def setUp(self):
        # Create 4 stops forming a small graph
        self.A = BusStop.objects.create(name="A", latitude=12.0, longitude=75.0)
        self.B = BusStop.objects.create(name="B", latitude=12.001, longitude=75.001)
        self.C = BusStop.objects.create(name="C", latitude=12.002, longitude=75.002)
        self.D = BusStop.objects.create(name="D", latitude=12.003, longitude=75.003)

    def test_shortest_path_basic(self):
        # A -> B (1), B -> C (1), A -> C (5) -> expect A-B-C with distance 2
        Route.objects.create(start_stop=self.A, end_stop=self.B, distance=1.0)
        Route.objects.create(start_stop=self.B, end_stop=self.C, distance=1.0)
        Route.objects.create(start_stop=self.A, end_stop=self.C, distance=5.0)

        res = utils.dijkstra_shortest_path(self.A.id, self.C.id)
        self.assertIsNotNone(res)
        self.assertEqual(res["path"], [self.A.id, self.B.id, self.C.id])
        self.assertAlmostEqual(res["total_distance"], 2.0, places=6)

    def test_edge_weight_correctness(self):
        # Now set A->C to 1, and A->B 2, B->C 2 -> expect direct A->C
        Route.objects.create(start_stop=self.A, end_stop=self.C, distance=1.0)
        Route.objects.create(start_stop=self.A, end_stop=self.B, distance=2.0)
        Route.objects.create(start_stop=self.B, end_stop=self.C, distance=2.0)

        res = utils.dijkstra_shortest_path(self.A.id, self.C.id)
        self.assertIsNotNone(res)
        self.assertEqual(res["path"], [self.A.id, self.C.id])
        self.assertAlmostEqual(res["total_distance"], 1.0, places=6)


class ORSBehaviorTests(TestCase):
    def setUp(self):
        self.A = BusStop.objects.create(name="A", latitude=12.0, longitude=75.0)
        self.B = BusStop.objects.create(name="B", latitude=12.01, longitude=75.01)

    @override_settings(OPENROUTESERVICE_API_KEY="")
    def test_ors_fallback_when_no_key(self):
        # ors_directions_for_stops should return None if API key missing
        stops = [
            {"id": self.A.id, "name": self.A.name, "latitude": self.A.latitude, "longitude": self.A.longitude},
            {"id": self.B.id, "name": self.B.name, "latitude": self.B.latitude, "longitude": self.B.longitude},
        ]
        res = utils.ors_directions_for_stops(stops)
        self.assertIsNone(res)


class APITests(TestCase):
    def setUp(self):
        self.client = Client()
        self.A = BusStop.objects.create(name="A", latitude=12.0, longitude=75.0)
        self.B = BusStop.objects.create(name="B", latitude=12.01, longitude=75.01)
        self.C = BusStop.objects.create(name="C", latitude=12.02, longitude=75.02)
        Route.objects.create(start_stop=self.A, end_stop=self.B, distance=1.2)
        Route.objects.create(start_stop=self.B, end_stop=self.C, distance=1.3)

    def test_list_stops(self):
        r = self.client.get("/api/stops/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertGreaterEqual(len(data), 3)

    def test_list_routes(self):
        r = self.client.get("/api/routes/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertGreaterEqual(len(data), 2)
        self.assertIn("start_stop", data[0])
        self.assertIn("end_stop", data[0])

    def test_shortest_route_endpoint(self):
        r = self.client.get(f"/api/shortest-route/?origin={self.A.id}&destination={self.C.id}")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("path", data)
        self.assertIn("stops", data)
        self.assertIn("total_distance", data)

    def test_stats_endpoint(self):
        r = self.client.get("/api/stats/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        # ors field may be None if stats file not present, but should exist
        self.assertIn("ors", data)
