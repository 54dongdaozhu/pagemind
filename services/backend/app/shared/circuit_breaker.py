import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum


logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    def __init__(self, name: str, retry_after_seconds: float):
        super().__init__(f"{name} circuit is open; retry after {retry_after_seconds:.1f}s")
        self.name = name
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class CircuitSnapshot:
    name: str
    state: CircuitState
    failures: int
    retry_after_seconds: float
    half_open_probe_in_flight: bool


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be greater than 0")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be greater than 0")

        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at: float | None = None
        self._half_open_probe_in_flight = False
        self._lock = threading.Lock()

    def before_call(self) -> None:
        with self._lock:
            now = time.monotonic()
            if self._state == CircuitState.OPEN:
                elapsed = now - (self._opened_at or now)
                if elapsed < self.recovery_timeout:
                    raise CircuitOpenError(self.name, self.recovery_timeout - elapsed)
                self._state = CircuitState.HALF_OPEN
                self._half_open_probe_in_flight = False

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_probe_in_flight:
                    raise CircuitOpenError(self.name, self.recovery_timeout)
                self._half_open_probe_in_flight = True

    def record_success(self) -> None:
        with self._lock:
            previous = self._state
            self._failures = 0
            self._state = CircuitState.CLOSED
            self._opened_at = None
            self._half_open_probe_in_flight = False
            if previous != CircuitState.CLOSED:
                logger.info("[CircuitBreaker] %s circuit closed", self.name)

    def record_failure(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._failures = self.failure_threshold
                self._open_locked()
                return

            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._open_locked()

    def snapshot(self) -> CircuitSnapshot:
        with self._lock:
            retry_after = 0.0
            if self._state == CircuitState.OPEN and self._opened_at is not None:
                retry_after = max(0.0, self.recovery_timeout - (time.monotonic() - self._opened_at))
            return CircuitSnapshot(
                name=self.name,
                state=self._state,
                failures=self._failures,
                retry_after_seconds=retry_after,
                half_open_probe_in_flight=self._half_open_probe_in_flight,
            )

    def _open_locked(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        self._half_open_probe_in_flight = False
        logger.warning(
            "[CircuitBreaker] %s circuit opened after %d failures",
            self.name,
            self._failures,
        )
