import unittest

from src.research_radar.field_seed import demo_research_field
from src.research_radar.models import ResearchField
from src.research_radar.query_builder import build_query_lanes


class ResearchRadarQueryBuilderTest(unittest.TestCase):
    def test_demo_field_builds_multiple_lanes(self):
        lanes = build_query_lanes(demo_research_field())
        lane_ids = {lane.id for lane in lanes}
        self.assertIn("broad_missing", lane_ids)
        self.assertIn("broad_recovery", lane_ids)
        self.assertTrue(any(lane.type == "exact" for lane in lanes))
        self.assertTrue(any(lane.type == "intent" for lane in lanes))
        self.assertTrue(all(lane.query for lane in lanes))
        self.assertTrue(all(lane.weight > 0 for lane in lanes))

    def test_max_lanes(self):
        lanes = build_query_lanes(demo_research_field(), max_lanes=2)
        self.assertEqual(len(lanes), 2)

    def test_generic_field_uses_name_when_no_specialized_lanes(self):
        field = ResearchField(id="field-1", slug="multimodal", name="Multimodal")
        lanes = build_query_lanes(field)
        self.assertEqual(lanes[0].id, "generic_1")
        self.assertEqual(lanes[0].query, "Multimodal")


if __name__ == "__main__":
    unittest.main()
