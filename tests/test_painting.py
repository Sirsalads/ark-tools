"""Painting helpers and config persistence; sends no mouse or keyboard input.

Run with: python tests/test_painting.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from dataclasses import asdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from arkmacro.config import Config, SkinOvercap  # noqa: E402
from arkmacro import painting  # noqa: E402


def sample(colour=(220, 20, 10)) -> list[list[int]]:
    return [list(colour) for _ in range(25)]


class DyeRecognitionTests(unittest.TestCase):
    def test_probe_pixels_have_stable_order_around_the_centre(self):
        points = painting.probe_points([192, 525])
        self.assertEqual(len(points), 25)
        self.assertEqual(points[:5], [(186, 519), (189, 519), (192, 519),
                                    (195, 519), (198, 519)])
        self.assertEqual(points[12], (192, 525))
        self.assertEqual(points[-1], (198, 531))
        self.assertEqual(points, painting.probe_points((192, 525)))
        # Negative coordinates are valid on a secondary monitor.
        self.assertEqual(painting.probe_points([-20, 100])[12], (-20, 100))

    def test_bad_points_cannot_be_probed(self):
        for point in (None, "12", [1], [1, 2, 3], [True, 1], [1.0, 2]):
            with self.subTest(point=point):
                self.assertEqual(painting.probe_points(point), [])

    def test_a_complete_readable_sample_is_required(self):
        self.assertTrue(painting.valid_sample(sample()))
        self.assertTrue(painting.valid_sample(tuple(tuple(c) for c in sample())))
        for invalid in (None, [], sample()[:24], sample() + [[1, 2, 3]],
                        sample((0, 0, 0)), sample((256, 0, 0)),
                        sample((-1, 0, 0)), sample((True, 0, 0)),
                        sample(("220", 20, 10)), sample((220.0, 20, 10)),
                        [[220, 20]] * 25, "red" * 25):
            with self.subTest(invalid=invalid):
                self.assertFalse(painting.valid_sample(invalid))
                self.assertFalse(painting.matches_dye(sample(), invalid))
                self.assertFalse(painting.matches_dye(invalid, sample()))

    def test_lighting_and_streaming_variation_still_matches(self):
        self.assertTrue(painting.matches_dye(sample(), sample()))
        self.assertTrue(painting.matches_dye(sample(), sample((170, 70, 60))))
        self.assertFalse(painting.matches_dye(sample(), sample((169, 20, 10))))
        self.assertFalse(painting.matches_dye(sample(), sample((10, 70, 140))))

    def test_eighteen_pixels_are_required_for_a_match(self):
        observed = sample()
        observed[:7] = [[10, 70, 140] for _ in range(7)]
        self.assertTrue(painting.matches_dye(sample(), observed))
        observed[7] = [10, 70, 140]
        self.assertFalse(painting.matches_dye(sample(), observed))

    def test_a_dye_sequence_ends_when_the_last_icon_disappears(self):
        # A changing stack count is outside this patch. Replacement stacks of
        # the captured colour match; the now-empty blue inventory slot does not.
        reads = [sample(), sample((200, 25, 15)), sample(), sample((10, 70, 140))]
        self.assertEqual([painting.matches_dye(sample(), read) for read in reads],
                         [True, True, True, False])
        self.assertEqual(painting.CLICKS_PER_STACK, 100)

    def test_ready_requires_distinct_targets_and_a_sample(self):
        skin = SkinOvercap()
        self.assertFalse(painting.ready(skin))
        skin.paint_point = [161, 318]
        skin.dye_point = [192, 525]
        self.assertFalse(painting.ready(skin))
        skin.dye_sample = sample()
        self.assertTrue(painting.ready(skin))
        for invalid in ([0, 0], skin.paint_point, None, [192], "192525"):
            with self.subTest(point=invalid):
                skin.dye_point = invalid
                self.assertFalse(painting.ready(skin))
        self.assertFalse(painting.ready(None))


class PaintingConfigTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ark-painting-")
        self.addCleanup(self.directory.cleanup)
        self.path = pathlib.Path(self.directory.name) / "config.json"

    def load_skin(self, values: dict) -> SkinOvercap:
        self.path.write_text(json.dumps({"skin_overcap": values}), encoding="utf-8")
        return Config.load(self.path).skin_overcap

    def test_legacy_sweep_is_disarmed_and_needs_new_captures(self):
        skin = self.load_skin({
            "enabled": True, "activate_key": " F5 ", "mode": "hold",
            "key": "2", "area": [140, 400, 600, 90],
            "area_resolution": [1920, 1080], "stops": 10, "dwell_ms": 25,
        })
        self.assertFalse(skin.enabled)
        self.assertEqual(skin.activate_key, "f5")
        self.assertEqual(skin.mode, "hold")
        self.assertEqual(skin.paint_point, [0, 0])
        self.assertEqual(skin.dye_point, [0, 0])
        self.assertEqual(skin.points_resolution, [0, 0])
        self.assertEqual(skin.dye_sample, [])
        self.assertFalse(painting.ready(skin))
        for obsolete in ("key", "area", "area_resolution", "stops", "dwell_ms"):
            self.assertNotIn(obsolete, asdict(skin))

    def test_captured_paint_settings_survive_a_round_trip(self):
        config = Config()
        config.skin_overcap = SkinOvercap(
            enabled=True, activate_key="f5", mode="hold",
            paint_point=[161, 318], dye_point=[192, 525],
            points_resolution=[1920, 1080], dye_sample=sample(),
            click_interval_ms=120, stack_pause_ms=900)
        config.save(self.path)
        restored = Config.load(self.path)
        self.assertEqual(asdict(restored.skin_overcap), asdict(config.skin_overcap))
        self.assertTrue(painting.ready(restored.skin_overcap))
        self.assertFalse(self.path.with_name("config.json.tmp").exists())

    def test_invalid_settings_are_sanitised(self):
        skin = self.load_skin({
            "paint_point": "nonsense", "dye_point": [192],
            "points_resolution": None, "dye_sample": sample()[:24],
            "click_interval_ms": -1, "stack_pause_ms": 99999,
            "activate_key": " F4 ", "mode": "invalid",
        })
        self.assertEqual(skin.paint_point, [0, 0])
        self.assertEqual(skin.dye_point, [0, 0])
        self.assertEqual(skin.points_resolution, [0, 0])
        self.assertEqual(skin.dye_sample, [])
        self.assertEqual(skin.click_interval_ms, 0)
        self.assertEqual(skin.stack_pause_ms, 5000)
        self.assertEqual(skin.activate_key, "f4")
        self.assertEqual(skin.mode, "toggle")
        self.assertFalse(painting.ready(skin))

    def test_waits_have_bounds_and_fallbacks(self):
        for click, pause, expected in ((99999, -1, (2000, 0)),
                                       (None, "invalid", (0, 0)),
                                       ("125", "750", (125, 750))):
            with self.subTest(click=click, pause=pause):
                skin = self.load_skin({"paint_point": [1, 2],
                                      "click_interval_ms": click,
                                      "stack_pause_ms": pause})
                self.assertEqual((skin.click_interval_ms, skin.stack_pause_ms),
                                 expected)

    def test_old_pacing_moves_to_the_new_floor_once(self):
        # the old default (80) and the old floor (50) both follow the new
        # default; a number that was chosen stays, and so does a pause that was
        for click, wait, expected in ((80, 500, (0, 0)),
                                      (50, 500, (0, 0)),
                                      (120, 900, (120, 900)),
                                      (50, 300, (0, 300))):
            with self.subTest(click=click, wait=wait):
                skin = self.load_skin({"paint_point": [1, 2],
                                      "click_interval_ms": click,
                                      "stack_wait_ms": wait})
                self.assertEqual((skin.click_interval_ms, skin.stack_pause_ms),
                                 expected)
        # a file written after the change is never touched again: 80 is now a
        # choice, not the default it used to be
        skin = self.load_skin({"paint_point": [1, 2], "click_interval_ms": 80,
                               "stack_pause_ms": 0})
        self.assertEqual((skin.click_interval_ms, skin.stack_pause_ms), (80, 0))

    def test_bad_sample_is_discarded_as_a_whole(self):
        for invalid in (None, [], sample((0, 0, 0)), sample((True, 0, 0)),
                        sample()[:24] + [[1000, 0, 0]]):
            with self.subTest(sample=invalid):
                skin = self.load_skin({"paint_point": [1, 2], "dye_sample": invalid})
                self.assertEqual(skin.dye_sample, [])


if __name__ == "__main__":
    unittest.main()
