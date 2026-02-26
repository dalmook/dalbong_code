import os
import tempfile
import unittest

from db import Store, normalize_keyword


class NormalizeKeywordTests(unittest.TestCase):
    def test_normalize_trims_collapses_and_casefolds(self):
        self.assertEqual(normalize_keyword("  RTX   4080 "), "rtx 4080")
        self.assertEqual(normalize_keyword("iPhone"), "iphone")
        self.assertEqual(normalize_keyword(""), "")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "test.sqlite3")
        self.store = Store(self.db_path)
        self.chat_id = "100"

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_keyword_prevents_duplicates_after_normalize(self):
        added, keyword, count = self.store.add_keyword(self.chat_id, " 아이폰 ")
        self.assertTrue(added)
        self.assertEqual(keyword, "아이폰")
        self.assertEqual(count, 1)

        added2, keyword2, count2 = self.store.add_keyword(self.chat_id, "아이폰")
        self.assertFalse(added2)
        self.assertEqual(keyword2, "아이폰")
        self.assertEqual(count2, 1)

    def test_remove_by_index(self):
        self.store.add_keyword(self.chat_id, "rtx")
        self.store.add_keyword(self.chat_id, "아이폰")
        success, removed, count = self.store.remove_keyword(self.chat_id, "1")
        self.assertTrue(success)
        self.assertIsNotNone(removed)
        self.assertEqual(count, 1)

    def test_ui_state_roundtrip(self):
        mode, payload = self.store.get_ui_state(self.chat_id)
        self.assertEqual(mode, "IDLE")
        self.assertIsNone(payload)

        self.store.set_ui_state(self.chat_id, "ADD_WAIT", {"source": "button"})
        mode, payload = self.store.get_ui_state(self.chat_id)
        self.assertEqual(mode, "ADD_WAIT")
        self.assertEqual(payload, {"source": "button"})

    def test_sent_dedup(self):
        self.assertTrue(self.store.mark_sent_if_new(self.chat_id, "item-1"))
        self.assertFalse(self.store.mark_sent_if_new(self.chat_id, "item-1"))


if __name__ == "__main__":
    unittest.main()
