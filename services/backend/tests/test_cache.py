import json
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
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
        self._mutex = threading.Lock()

    def get(self, key):
        with self._mutex:
            return self.values.get(key)

    def ping(self):
        return True

    def mget(self, keys):
        with self._mutex:
            return [self.values.get(key) for key in keys]

    def setex(self, key, ttl, value):
        with self._mutex:
            self.values[key] = value
            self.ttls[key] = ttl
            self.setex_calls.append((key, ttl, value))
        return True

    def set(self, key, value, nx=False, ex=None):
        with self._mutex:
            if nx and key in self.values:
                return False
            self.values[key] = value
            self.ttls[key] = ex
            return True

    def eval(self, _script, _num_keys, key, token):
        with self._mutex:
            if self.values.get(key) == token:
                del self.values[key]
                return 1
            return 0

    def delete(self, key):
        with self._mutex:
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

    def test_get_or_set_json_coalesces_concurrent_cache_misses(self):
        redis = FakeRedis()
        barrier = threading.Barrier(6)
        loader_calls = 0
        loader_mutex = threading.Lock()

        def loader():
            nonlocal loader_calls
            with loader_mutex:
                loader_calls += 1
            time.sleep(0.08)
            return {"value": 42}

        def read_value(_index):
            barrier.wait()
            return cache.get_or_set_json(
                "hot-key",
                loader,
                wait_timeout_seconds=0.5,
                retry_interval_seconds=0.01,
                jitter=False,
            )

        with (
            patch("app.shared.cache.get_redis", return_value=redis),
            ThreadPoolExecutor(max_workers=6) as executor,
        ):
            results = list(executor.map(read_value, range(6)))

        self.assertEqual(results, [{"value": 42}] * 6)
        self.assertEqual(loader_calls, 1)

    def test_get_or_set_json_does_not_wait_when_redis_is_unavailable(self):
        with (
            patch("app.shared.cache._get_json_cached_value", return_value=(False, None)),
            patch("app.shared.cache.try_acquire_lock", return_value=None),
            patch("app.shared.cache.redis_available", return_value=False),
            patch("app.shared.cache.time.sleep", side_effect=AssertionError("must not wait")),
        ):
            result = cache.get_or_set_json(
                "key",
                lambda: {"fallback": True},
                wait_timeout_seconds=60,
            )

        self.assertEqual(result, {"fallback": True})

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
