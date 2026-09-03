import unittest

from backend.film_stitcher import MASTERING_FILTER, build_music_mix_filter


class AudioMasteringTests(unittest.TestCase):
    def test_mastering_targets_social_video_loudness_without_clipping(self):
        self.assertIn("I=-16", MASTERING_FILTER)
        self.assertIn("TP=-1.5", MASTERING_FILTER)
        self.assertIn("LRA=11", MASTERING_FILTER)

    def test_music_mix_preserves_original_audio_and_ducks_music(self):
        graph = build_music_mix_filter()
        self.assertIn("[music][0:a]sidechaincompress", graph)
        self.assertIn("[0:a][ducked]amix", graph)
        self.assertIn(MASTERING_FILTER, graph)

    def test_music_volume_is_safely_clamped(self):
        self.assertIn("volume=1.00", build_music_mix_filter(9))
        self.assertIn("volume=0.00", build_music_mix_filter(-2))


if __name__ == "__main__":
    unittest.main()
