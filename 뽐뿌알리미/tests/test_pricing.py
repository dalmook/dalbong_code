import unittest

from pricing import build_price_analysis, parse_price_observation


class PricingTests(unittest.TestCase):
    def test_parse_price_per_piece(self):
        obs = parse_price_observation(
            item_id="x1",
            title="[11번가] 햇반 180g 32개 19,840원 무배",
            link="https://example.com",
            board_rss_url="https://www.ppomppu.co.kr/rss.php?id=ppomppu",
        )
        self.assertIsNotNone(obs)
        assert obs is not None
        self.assertEqual(obs.total_price_krw, 19840)
        self.assertEqual(obs.quantity_count, 32)
        self.assertEqual(obs.metric_basis, "ea")
        self.assertAlmostEqual(obs.metric_value_krw or 0, 620.0, places=2)
        self.assertTrue(obs.product_key and "햇반" in obs.product_key)

    def test_parse_price_total_only(self):
        obs = parse_price_observation(
            item_id="x2",
            title="커피 원두 특가 12,900원",
            link="https://example.com",
            board_rss_url="https://www.ppomppu.co.kr/rss.php?id=ppomppu",
        )
        self.assertIsNotNone(obs)
        assert obs is not None
        self.assertEqual(obs.metric_basis, "total")
        self.assertEqual(obs.metric_value_krw, 12900.0)

    def test_build_analysis(self):
        analysis = build_price_analysis(620.0, "ea", [580.0, 560.0, 570.0])
        self.assertIsNotNone(analysis)
        assert analysis is not None
        line = analysis.to_alert_line()
        self.assertIn("620", line)
        self.assertIn("직전", line)


if __name__ == "__main__":
    unittest.main()
