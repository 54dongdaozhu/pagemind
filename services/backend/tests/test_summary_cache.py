import unittest

from app.modules.rag.summarization import _full_summary_cache_key


class SummaryCacheTest(unittest.TestCase):
    def test_cache_key_changes_with_document_version(self):
        first = _full_summary_cache_key("u1", "d1", "v1", "总结")
        second = _full_summary_cache_key("u1", "d1", "v2", "总结")

        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
