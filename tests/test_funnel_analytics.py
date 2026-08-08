import importlib
import os
import sys
import types
import unittest


class FunnelAnalyticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("DATABASE_URL", "postgresql://example/test")

        fake_psycopg = types.ModuleType("psycopg")
        fake_rows = types.ModuleType("psycopg.rows")
        fake_rows.dict_row = object()
        fake_psycopg.ProgrammingError = Exception
        fake_psycopg.connect = lambda *args, **kwargs: None
        sys.modules["psycopg"] = fake_psycopg
        sys.modules["psycopg.rows"] = fake_rows

        fake_pool_module = types.ModuleType("psycopg_pool")

        class FakeConnectionPool:
            def __init__(self, *args, **kwargs):
                pass

            def connection(self):
                raise AssertionError("tests should not use the real database pool")

        fake_pool_module.ConnectionPool = FakeConnectionPool
        sys.modules["psycopg_pool"] = fake_pool_module

        cls.server = importlib.import_module("server_deploy")

    def test_funnel_data_converts_raw_event_rows_to_daily_metrics(self):
        rows = [
            {
                "date": "2026-08-09",
                "visitors": 4,
                "return_visitors": 1,
                "first_pops": 3,
                "pop_10s": 2,
                "name_sets": 1,
                "ranking_views": 2,
                "refresh_clicks": 1,
                "session_ends": 3,
                "median_first_pop_ms": 1200,
                "median_name_set_ms": 8000,
                "median_session_seconds": 42,
                "total_session_pops": 90,
            }
        ]
        original = self.server._analytics_query
        self.server._analytics_query = lambda sql, params=None: rows
        try:
            data = self.server._funnel_data()
        finally:
            self.server._analytics_query = original

        self.assertEqual(data, [{
            "date": "2026-08-09",
            "visitors": 4,
            "return_visitors": 1,
            "first_pops": 3,
            "pop_10s": 2,
            "name_sets": 1,
            "ranking_views": 2,
            "refresh_clicks": 1,
            "session_ends": 3,
            "visit_to_first_pop_rate": 0.75,
            "first_pop_to_10_rate": 0.6667,
            "pop_10_to_name_set_rate": 0.5,
            "visit_to_ranking_rate": 0.5,
            "return_visit_rate": 0.25,
            "median_first_pop_ms": 1200,
            "median_name_set_ms": 8000,
            "median_session_seconds": 42,
            "avg_session_pops": 30.0,
        }])


if __name__ == "__main__":
    unittest.main()
