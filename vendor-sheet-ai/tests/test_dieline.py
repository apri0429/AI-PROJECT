from __future__ import annotations

import unittest

from core.dieline import calculate_dieline


class DielineTests(unittest.TestCase):
    def test_calculate_dieline_returns_bleed_value(self) -> None:
        result = calculate_dieline(100, 200)
        self.assertEqual(result["width"], 100.0)
        self.assertEqual(result["height"], 200.0)
        self.assertEqual(result["bleed"], 4.0)


if __name__ == "__main__":
    unittest.main()
