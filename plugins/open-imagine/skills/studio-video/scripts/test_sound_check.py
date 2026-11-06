#!/usr/bin/env python3
"""Tests for the delivery measurements in sound_check.py, on synthetic tones with known answers."""

import math
import pathlib
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sound_check

RATE = 16000


def write_tone(path, segments):
    """segments: (seconds, start_hz, end_hz); a 0 Hz segment is silence."""
    samples, phase = [], 0.0
    for seconds, start, end in segments:
        count = int(seconds * RATE)
        for i in range(count):
            hz = start + (end - start) * i / count
            phase += 2 * math.pi * hz / RATE
            samples.append(int(12000 * math.sin(phase)) if hz else 0)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(b"".join(s.to_bytes(2, "little", signed=True) for s in samples))


class MeasureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def measure(self, segments):
        path = self.root / "tone.wav"
        write_tone(path, segments)
        return sound_check.measure(path)

    def test_flat_tone_has_almost_no_pitch_range(self):
        result = self.measure([(1.0, 120, 120)])
        self.assertAlmostEqual(result["median_hz"], 120, delta=4)
        self.assertLess(result["pitch_range_semitones"], 1)

    def test_rising_glide_has_a_wide_pitch_range(self):
        result = self.measure([(1.0, 100, 200)])
        self.assertGreater(result["pitch_range_semitones"], 8)

    def test_gap_inside_speech_counts_as_one_pause(self):
        result = self.measure([(0.4, 150, 150), (0.3, 0, 0), (0.4, 150, 150)])
        self.assertEqual(result["pauses"], 1)
        self.assertAlmostEqual(result["longest_pause_seconds"], 0.3, delta=0.06)

    def test_leading_and_trailing_silence_are_not_pauses(self):
        result = self.measure([(0.3, 0, 0), (0.5, 150, 150), (0.3, 0, 0)])
        self.assertEqual(result["pauses"], 0)
        self.assertAlmostEqual(result["seconds"], 1.1, delta=0.02)


if __name__ == "__main__":
    unittest.main()
