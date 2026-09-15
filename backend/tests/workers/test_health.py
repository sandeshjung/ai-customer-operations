import json
import urllib.error
import urllib.request
from unittest.mock import patch

import pytest
from app.workers import health


class TestRecordHeartbeat:
    def test_writes_key_with_configured_ttl(self):
        with patch.object(health, "redis_client") as mock_redis:
            health.record_heartbeat()

        mock_redis.set.assert_called_once()
        args, kwargs = mock_redis.set.call_args
        assert args[0] == health.HEARTBEAT_KEY
        assert kwargs["ex"] == health.settings.WORKER_HEARTBEAT_TTL_SECONDS

    def test_swallows_redis_failures(self):
        """A Redis hiccup on the heartbeat write must never be the thing
        that crashes real event processing — this should not raise."""
        with patch.object(health, "redis_client") as mock_redis:
            mock_redis.set.side_effect = ConnectionError("no redis")
            health.record_heartbeat()  # should not raise


class TestIsHealthy:
    def test_true_when_heartbeat_key_present(self):
        with patch.object(health, "redis_client") as mock_redis:
            mock_redis.exists.return_value = 1
            assert health.is_healthy() is True

    def test_false_when_heartbeat_key_absent(self):
        with patch.object(health, "redis_client") as mock_redis:
            mock_redis.exists.return_value = 0
            assert health.is_healthy() is False

    def test_false_when_redis_unreachable(self):
        """Can't confirm liveness -> not healthy, not a crash."""
        with patch.object(health, "redis_client") as mock_redis:
            mock_redis.exists.side_effect = ConnectionError("no redis")
            assert health.is_healthy() is False


class TestHealthServer:
    """Real server, real HTTP requests — not mocked."""

    @pytest.fixture()
    def server(self):
        srv = health.start_health_server(port=0)  # port=0 -> OS picks a free one
        yield srv
        srv.shutdown()

    def _get(self, server, path="/health"):
        url = f"http://localhost:{server.server_port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_returns_200_when_healthy(self, server):
        with patch.object(health, "is_healthy", return_value=True):
            status, body = self._get(server)

        assert status == 200
        assert body == {"status": "ok"}

    def test_returns_503_when_unhealthy(self, server):
        with patch.object(health, "is_healthy", return_value=False):
            status, body = self._get(server)

        assert status == 503
        assert body == {"status": "unhealthy"}

    def test_unknown_path_returns_404(self, server):
        status, body = self._get(server, path="/nonexistent")
        assert status == 404
        assert body == {"status": "not_found"}