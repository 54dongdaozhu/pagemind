import time
import unittest

from app.shared.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


class CircuitBreakerTest(unittest.TestCase):
    def test_opens_after_threshold_and_short_circuits(self):
        breaker = CircuitBreaker("test", failure_threshold=2, recovery_timeout=10)

        breaker.before_call()
        breaker.record_failure()
        self.assertEqual(breaker.snapshot().state, CircuitState.CLOSED)

        breaker.before_call()
        breaker.record_failure()
        self.assertEqual(breaker.snapshot().state, CircuitState.OPEN)

        with self.assertRaises(CircuitOpenError):
            breaker.before_call()

    def test_half_open_allows_single_probe_and_success_closes(self):
        breaker = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.01)

        breaker.before_call()
        breaker.record_failure()
        time.sleep(0.02)

        breaker.before_call()
        self.assertEqual(breaker.snapshot().state, CircuitState.HALF_OPEN)

        with self.assertRaises(CircuitOpenError):
            breaker.before_call()

        breaker.record_success()
        snapshot = breaker.snapshot()
        self.assertEqual(snapshot.state, CircuitState.CLOSED)
        self.assertEqual(snapshot.failures, 0)

    def test_half_open_failure_reopens(self):
        breaker = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.01)

        breaker.before_call()
        breaker.record_failure()
        time.sleep(0.02)

        breaker.before_call()
        breaker.record_failure()

        self.assertEqual(breaker.snapshot().state, CircuitState.OPEN)
        with self.assertRaises(CircuitOpenError):
            breaker.before_call()


if __name__ == "__main__":
    unittest.main()
