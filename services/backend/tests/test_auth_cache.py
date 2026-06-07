import unittest
from unittest.mock import patch

from app.modules.auth.service import _invalidate_user_auth_cache, _user_auth_cache_key


class AuthCacheTest(unittest.TestCase):
    def test_auth_cache_key_is_scoped_to_user_and_token(self):
        key = _user_auth_cache_key("user-1", "token-1")

        self.assertTrue(key.startswith("cache:user_auth:u:user-1:t:"))
        self.assertNotEqual(key, _user_auth_cache_key("user-1", "token-2"))
        self.assertNotEqual(key, _user_auth_cache_key("user-2", "token-1"))

    def test_invalidation_only_targets_one_user(self):
        with patch("app.modules.auth.service.delete_pattern") as delete_pattern:
            _invalidate_user_auth_cache("user-1")

        delete_pattern.assert_called_once_with("cache:user_auth:u:user-1:t:*")


if __name__ == "__main__":
    unittest.main()
