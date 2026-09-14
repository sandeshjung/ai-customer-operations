from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core import security


class TestRequireApiKey:
    def test_accepts_correct_key(self):
        with patch.object(security.settings, "ADMIN_API_KEY", "secret123"):
            # Should not raise.
            security.require_api_key(x_api_key="secret123")

    def test_rejects_wrong_key(self):
        with patch.object(security.settings, "ADMIN_API_KEY", "secret123"):
            with pytest.raises(HTTPException) as exc_info:
                security.require_api_key(x_api_key="wrong")
        assert exc_info.value.status_code == 401

    def test_rejects_missing_key(self):
        with patch.object(security.settings, "ADMIN_API_KEY", "secret123"):
            with pytest.raises(HTTPException) as exc_info:
                security.require_api_key(x_api_key=None)
        assert exc_info.value.status_code == 401

    def test_fails_closed_and_loud_when_unconfigured(self):
        """An unset ADMIN_API_KEY means auth was never set up — this
        should refuse every request with a clear 503, not silently let
        everything through."""
        with patch.object(security.settings, "ADMIN_API_KEY", None):
            with pytest.raises(HTTPException) as exc_info:
                security.require_api_key(x_api_key="anything")
        assert exc_info.value.status_code == 503


class TestRateLimit:
    def _make_request(self, client_host="1.2.3.4"):
        request = MagicMock()
        request.client.host = client_host
        return request

    def test_allows_requests_under_the_limit(self):
        fake_redis = MagicMock()
        fake_redis.incr.return_value = 1

        with patch.object(security, "redis_client", fake_redis):
            dependency = security.rate_limit("test", max_requests=5, window_seconds=60)
            # Should not raise.
            dependency(self._make_request())

    def test_blocks_requests_over_the_limit(self):
        fake_redis = MagicMock()
        fake_redis.incr.return_value = 6  # over the max_requests=5 limit

        with patch.object(security, "redis_client", fake_redis):
            dependency = security.rate_limit("test", max_requests=5, window_seconds=60)
            with pytest.raises(HTTPException) as exc_info:
                dependency(self._make_request())

        assert exc_info.value.status_code == 429

    def test_sets_expiry_only_on_first_request_in_window(self):
        fake_redis = MagicMock()
        fake_redis.incr.return_value = 1

        with patch.object(security, "redis_client", fake_redis):
            dependency = security.rate_limit("test", max_requests=5, window_seconds=60)
            dependency(self._make_request())

        fake_redis.expire.assert_called_once()

    def test_does_not_reset_expiry_on_subsequent_requests(self):
        fake_redis = MagicMock()
        fake_redis.incr.return_value = 3  # not the first request in this window

        with patch.object(security, "redis_client", fake_redis):
            dependency = security.rate_limit("test", max_requests=5, window_seconds=60)
            dependency(self._make_request())

        fake_redis.expire.assert_not_called()

    def test_different_clients_tracked_separately(self):
        fake_redis = MagicMock()
        fake_redis.incr.return_value = 1

        with patch.object(security, "redis_client", fake_redis):
            dependency = security.rate_limit("test", max_requests=5, window_seconds=60)
            dependency(self._make_request(client_host="1.1.1.1"))
            dependency(self._make_request(client_host="2.2.2.2"))

        keys_used = [call.args[0] for call in fake_redis.incr.call_args_list]
        assert "1.1.1.1" in keys_used[0]
        assert "2.2.2.2" in keys_used[1]
        assert keys_used[0] != keys_used[1]

    def test_disabled_via_settings_skips_check_entirely(self):
        fake_redis = MagicMock()

        with (
            patch.object(security.settings, "RATE_LIMIT_ENABLED", False),
            patch.object(security, "redis_client", fake_redis),
        ):
            dependency = security.rate_limit("test", max_requests=1, window_seconds=60)
            # Even far over any reasonable limit, should pass through
            # without touching Redis at all.
            dependency(self._make_request())
            dependency(self._make_request())
            dependency(self._make_request())

        fake_redis.incr.assert_not_called()