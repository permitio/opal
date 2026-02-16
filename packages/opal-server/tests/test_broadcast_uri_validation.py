"""Tests for broadcast URI validation and error logging (issue #716)."""

import asyncio
import logging
import socket
from unittest.mock import MagicMock, patch

import pytest

from opal_server.pubsub import PubSub


class TestValidateBroadcastUri:
    def test_invalid_hostname_logs_error(self, caplog):
        """Unresolvable hostname should be logged at ERROR level."""
        with caplog.at_level(logging.ERROR, logger="opal.server"):
            with patch(
                "opal_server.pubsub.socket.getaddrinfo",
                side_effect=socket.gaierror("Name or service not known"),
            ):
                PubSub._validate_broadcast_uri("postgres://invalid-host-xyz:5432/db")
        assert any("Cannot resolve broadcast URI hostname" in r.message for r in caplog.records)

    def test_valid_hostname_no_error(self, caplog):
        """Resolvable hostname should not produce ERROR logs."""
        with caplog.at_level(logging.ERROR, logger="opal.server"):
            with patch("opal_server.pubsub.socket.getaddrinfo", return_value=[(None,) * 5]):
                PubSub._validate_broadcast_uri("postgres://localhost:5432/db")
        assert not any("Cannot resolve" in r.message for r in caplog.records)

    def test_uri_without_hostname_logs_error(self, caplog):
        """URI with no hostname should be logged at ERROR level."""
        with caplog.at_level(logging.ERROR, logger="opal.server"):
            PubSub._validate_broadcast_uri("postgres://")
        assert any("has no hostname" in r.message for r in caplog.records)


class TestMaskUriPassword:
    def test_password_masked(self):
        result = PubSub._mask_uri_password("postgres://user:secret@host:5432/db")
        assert "secret" not in result
        assert "***" in result
        assert "user" in result

    def test_no_password(self):
        uri = "postgres://host:5432/db"
        assert PubSub._mask_uri_password(uri) == uri


class TestOnBroadcasterDisconnected:
    def test_callback_logs_exception_on_error(self, caplog):
        """done_callback should log task exceptions at ERROR level."""
        from opal_server.server import OpalServer

        task = MagicMock(spec=asyncio.Task)
        task.exception.return_value = ConnectionError("connection refused")

        server = object.__new__(OpalServer)

        with caplog.at_level(logging.ERROR, logger="opal.server"):
            with patch.object(OpalServer, "_graceful_shutdown"):
                server._on_broadcaster_disconnected(task)

        assert any("Broadcast channel connection failed" in r.message for r in caplog.records)

    def test_callback_calls_graceful_shutdown(self):
        """done_callback should call _graceful_shutdown."""
        from opal_server.server import OpalServer

        task = MagicMock(spec=asyncio.Task)
        task.exception.return_value = None

        server = object.__new__(OpalServer)

        with patch.object(OpalServer, "_graceful_shutdown") as mock_shutdown:
            server._on_broadcaster_disconnected(task)
            mock_shutdown.assert_called_once()
