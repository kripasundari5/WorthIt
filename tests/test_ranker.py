import unittest

from core.ranker import compute_floors


class FloorGuardTests(unittest.TestCase):
    def test_guard_skips_saturated_aspect_floor(self):
        candidates = [
            {"aspects": {"build_quality": {"score": 1.0, "mentions": 2}}},
            {"aspects": {"build_quality": {"score": 1.0, "mentions": 2}}},
            {"aspects": {"build_quality": {"score": 1.0, "mentions": 2}}},
        ]
        self.assertEqual(compute_floors(candidates, ["build_quality"], guard=True), {})
        self.assertEqual(compute_floors(candidates, ["build_quality"], guard=False),
                         {"build_quality": 1.0})

    def test_guard_keeps_floor_below_median(self):
        candidates = [
            {"aspects": {"thermals": {"score": score, "mentions": 2}}}
            for score in (0.0, 0.2, 0.4, 0.6, 0.8)
        ]
        floors = compute_floors(candidates, ["thermals"], percentile=35, guard=True)
        self.assertIn("thermals", floors)
        self.assertLess(floors["thermals"], 0.4)

    def test_aspect_without_valid_mentions_is_omitted(self):
        candidates = [{"aspects": {"display": {"score": 0.9, "mentions": 0}}}]
        self.assertEqual(compute_floors(candidates, ["display"], guard=True), {})


if __name__ == "__main__":
    unittest.main()
