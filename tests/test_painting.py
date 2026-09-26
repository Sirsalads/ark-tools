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

    def test_a_patch_of_one_colour_survives_a_minority_moving(self):
        # A uniform capture is recognised while most of it still agrees. It
        # used to need 18 of 25 pixels; a patch that is nearly all one colour
        # is now also recognised by that colour, so a third of it can move —
        # a highlight, a border, a quantity — without losing the dye.
        observed = sample()
        observed[:8] = [[10, 70, 140] for _ in range(8)]
        self.assertTrue(painting.matches_dye(sample(), observed))
        self.assertLess(painting.match_score(sample(), observed),
                        painting.MATCH_PERCENT)

    def test_but_the_majority_moving_is_a_different_slot(self):
        observed = sample()
        observed[:13] = [[10, 70, 140] for _ in range(13)]
        self.assertFalse(painting.matches_dye(sample(), observed))

    def test_a_capture_across_an_edge_gets_neither_path(self):
        # The real one. This patch was taken on the boundary of a dye icon:
        # brown slot background across the top, pure red across the bottom. Its
        # middle belongs to neither half, so recognising it by that middle
        # would match an emptied slot just as happily — and never stop the run.
        edge = ([[85, 61, 47]] * 5 + [[176, 85, 80], [236, 82, 81],
                                      [139, 93, 89], [77, 58, 46], [111, 92, 76]]
                + [[255, 0, 0]] * 3 + [[177, 117, 112], [81, 64, 52]]
                + [[255, 0, 0]] * 4 + [[178, 0, 0]]
                + [[255, 0, 0]] * 3 + [[204, 0, 0], [215, 0, 0]])
        self.assertEqual(len(edge), 25)
        self.assertFalse(painting.dominated(edge))
        self.assertTrue(painting.dominated(sample()))
        # an empty slot must not pass just because the middles happen to agree
        self.assertFalse(painting.matches_dye(edge, sample((204, 0, 0))))

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
        self.assertEqual(skin.click_interval_ms, 5)
        self.assertEqual(skin.stack_pause_ms, 5000)
        self.assertEqual(skin.activate_key, "f4")
        self.assertEqual(skin.mode, "toggle")
        self.assertFalse(painting.ready(skin))

    def test_waits_have_bounds_and_fallbacks(self):
        for click, pause, expected in ((99999, -1, (2000, 0)),
                                       (None, "invalid", (40, 150)),
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
        for click, wait, expected in ((80, 500, (40, 150)),
                                      (50, 500, (40, 150)),
                                      (120, 900, (120, 900)),
                                      (50, 300, (40, 300))):
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

    def test_the_zero_gap_build_is_corrected_not_inherited(self):
        # A gap of 0 painted nothing: 2.5 ms between clicks, held 2.5 ms, which
        # is a fraction of the frame the game reads them on. It was one build's
        # default, so nobody chose it, and it is replaced rather than clamped.
        skin = self.load_skin({"paint_point": [1, 2], "click_interval_ms": 0,
                               "stack_pause_ms": 0})
        self.assertEqual((skin.click_interval_ms, skin.stack_pause_ms),
                         (40, 150))
        # a pause that was chosen survives the correction of the gap
        skin = self.load_skin({"paint_point": [1, 2], "click_interval_ms": 0,
                               "stack_pause_ms": 800})
        self.assertEqual((skin.click_interval_ms, skin.stack_pause_ms),
                         (40, 800))
        # and the floor is a floor: a hand-typed 1 ms is raised to where the
        # numbers still mean something, not accepted
        skin = self.load_skin({"paint_point": [1, 2], "click_interval_ms": 1,
                               "stack_pause_ms": 0})
        self.assertEqual((skin.click_interval_ms, skin.stack_pause_ms), (5, 0))

    def test_bad_sample_is_discarded_as_a_whole(self):
        for invalid in (None, [], sample((0, 0, 0)), sample((True, 0, 0)),
                        sample()[:24] + [[1000, 0, 0]]):
            with self.subTest(sample=invalid):
                skin = self.load_skin({"paint_point": [1, 2], "dye_sample": invalid})
                self.assertEqual(skin.dye_sample, [])


class MedianRecognition(unittest.TestCase):
    """The second way to recognise the dye. See painting.matches_dye."""

    @staticmethod
    def patch(colours, count):
        """A reading of `colours`, `count` of them, padded to a full sample."""
        out = list(colours)[:count]
        return out + [list(colours[-1])] * (painting.SAMPLE_COUNT - len(out))

    def test_a_patch_that_mostly_agrees_is_the_same_dye(self):
        # A dye icon with some of its pixels moved — a highlight, a border, a
        # quantity that changed as the stack went down. Per pixel this scores
        # far under the bar; what the patch mostly is has not moved at all.
        dye = self.patch([[88, 66, 50]], 25)
        disturbed = ([[255, 255, 255]] * 10) + ([[88, 66, 50]] * 15)
        self.assertLess(painting.match_score(dye, disturbed),
                        painting.MATCH_PERCENT)
        self.assertLessEqual(painting.median_apart(dye, disturbed),
                             painting.CHANNEL_TOLERANCE)
        self.assertTrue(painting.matches_dye(dye, disturbed))

    def test_an_empty_slot_is_still_an_empty_slot(self):
        # what the check exists for has to keep working: the panel behind a
        # used-up stack is nothing like the dye that was on it
        dye = self.patch([[220, 25, 20]], 25)
        empty = self.patch([[30, 32, 38]], 25)
        self.assertFalse(painting.matches_dye(dye, empty))
        self.assertGreater(painting.median_apart(dye, empty),
                           painting.CHANNEL_TOLERANCE)

    def test_the_strict_path_still_answers_on_its_own(self):
        dye = self.patch([[220, 25, 20]], 25)
        same = self.patch([[224, 30, 18]], 25)
        self.assertGreaterEqual(painting.match_score(dye, same),
                                painting.MATCH_PERCENT)
        self.assertTrue(painting.matches_dye(dye, same))

    def test_the_middle_is_per_channel_and_not_one_of_the_samples(self):
        sample = [[0, 100, 200], [50, 150, 0], [200, 0, 100]] + [[9, 9, 9]] * 22
        self.assertEqual(painting.median_colour(sample), (9, 9, 9))
        # a reading that cannot be trusted has no middle, and is never a match
        self.assertIsNone(painting.median_colour([]))
        self.assertEqual(painting.median_apart(sample, None), 255)
        self.assertFalse(painting.matches_dye(sample, None))


if __name__ == "__main__":
    unittest.main()
