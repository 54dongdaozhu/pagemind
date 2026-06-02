import json
import unittest
from unittest.mock import patch

from app.shared import cache


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.calls = []

    def setex(self, key, ttl, value):
        self.calls.append((key, ttl, value))
        return self

    def execute(self):
        for key, ttl, value in self.calls:
            self.redis.setex(key, ttl, value)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}
        self.setex_calls = []

    def get(self, key):
        return self.values.get(key)

    def mget(self, keys):
        return [self.values.get(key) for key in keys]

    def setex(self, key, ttl, value):
        self.values[key] = value
        self.ttls[key] = ttl
        self.setex_calls.append((key, ttl, value))
        return True

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.ttls[key] = ex
        return True

    def eval(self, _script, _num_keys, key, token):
        if self.values.get(key) == token:
            del self.values[key]
            return 1
        return 0

    def delete(self, key):
        existed = key in self.values
        self.values.pop(key, None)
        return int(existed)

    def pipeline(self, transaction=False):
        return FakePipeline(self)


class CacheTest(unittest.TestCase):
    def test_jitter_ttl_uses_configured_spread(self):
        with patch("app.shared.cache.random.randint", return_value=7):
            self.assertEqual(cache.jitter_ttl(100, jitter_ratio=0.1), 107)

    def test_set_json_applies_jitter_by_default(self):
        redis = FakeRedis()
        with (
            patch("app.shared.cache.get_redis", return_value=redis),
            patch("app.shared.cache.random.randint", return_value=-5),
        ):
            self.assertTrue(cache.set_json("k", {"a": 1}, 100))

        self.assertEqual(redis.ttls["k"], 95)
        self.assertEqual(json.loads(redis.values["k"]), {"a": 1})

    def test_set_text_can_disable_jitter_for_exact_ttl(self):
        redis = FakeRedis()
        with (
            patch("app.shared.cache.get_redis", return_value=redis),
            patch("app.shared.cache.random.randint", return_value=-5),
        ):
            self.assertTrue(cache.set_text("token", "1", 100, jitter=False))

        self.assertEqual(redis.ttls["token"], 100)

    def test_get_or_set_json_does_not_call_loader_for_cached_null(self):
        redis = FakeRedis()
        with patch("app.shared.cache.get_redis", return_value=redis):
            cache.set_json_null("missing", 30, jitter=False)

            def loader():
                raise AssertionError("loader should not run")

            self.assertIsNone(cache.get_or_set_json("missing", loader))

    def test_get_or_set_json_loads_and_caches_null_value(self):
        redis = FakeRedis()
        calls = []

        def loader():
            calls.append("called")
            return None

        with patch("app.shared.cache.get_redis", return_value=redis):
            self.assertIsNone(cache.get_or_set_json("missing", loader, null_ttl_seconds=30, jitter=False))
            self.assertIsNone(cache.get_or_set_json("missing", loader, null_ttl_seconds=30, jitter=False))

        self.assertEqual(calls, ["called"])
        self.assertEqual(json.loads(redis.values["missing"]), cache.NULL_JSON_CACHE_VALUE)
        self.assertEqual(redis.ttls["missing"], 30)

    def test_get_or_set_json_returns_cached_hit_without_loader(self):
        redis = FakeRedis()
        with patch("app.shared.cache.get_redis", return_value=redis):
            cache.set_json("profile", {"name": "Ada"}, 300, jitter=False)

            def loader():
                raise AssertionError("loader should not run")

            self.assertEqual(cache.get_or_set_json("profile", loader), {"name": "Ada"})

    def test_get_or_set_text_loads_and_caches_value(self):
        redis = FakeRedis()
        with patch("app.shared.cache.get_redis", return_value=redis):
            value = cache.get_or_set_text("summary", lambda: "hello", 60, jitter=False)

        self.assertEqual(value, "hello")
        self.assertEqual(redis.values["summary"], "hello")
        self.assertEqual(redis.ttls["summary"], 60)

    def test_release_lock_only_deletes_matching_token(self):
        redis = FakeRedis()
        with patch("app.shared.cache.get_redis", return_value=redis):
            token = cache.try_acquire_lock("lock:k", ttl_seconds=5)
            self.assertIsNotNone(token)
            self.assertFalse(cache.release_lock("lock:k", "other-token"))
            self.assertIn("lock:k", redis.values)
            self.assertTrue(cache.release_lock("lock:k", token))
            self.assertNotIn("lock:k", redis.values)


if __name__ == "__main__":
    unittest.main()
