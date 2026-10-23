"""Opt-in installed-wheel behavior checks; fake SDK never launches an agent."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from notebook_intelligence import claude


class UnavailableSDK:
    def __init__(self, *, options):
        self.options = options

    async def __aenter__(self):
        raise OSError('controlled unavailable agent')

    async def __aexit__(self, *args):
        return False


class AvailableSDK(UnavailableSDK):
    queries = []

    async def __aenter__(self):
        return self

    async def get_server_info(self):
        return {'controlled': True}

    async def query(self, query):
        self.queries.append(query)

    async def receive_response(self):
        return
        yield


class LazyClaudeClientQualification(unittest.TestCase):
    def client(self):
        return claude.ClaudeCodeClient(SimpleNamespace(websocket_connector=None, nbi_config=SimpleNamespace(claude_settings={})),
                                      claude.ClaudeAgentOptions())

    def test_construction_does_not_start_or_connect_agent(self):
        with patch.object(claude, 'ClaudeSDKClient', UnavailableSDK):
            client = self.client()
            self.assertEqual(client.status, claude.ClaudeAgentClientStatus.NotConnected)
            self.assertIsNone(client._client_thread)
            self.assertIsNone(client._client)
            self.assertFalse(client.is_connected())

    def test_first_query_reports_real_connection_failure(self):
        with patch.object(claude, 'ClaudeSDKClient', UnavailableSDK):
            client = self.client()
            error = client.query(SimpleNamespace(), SimpleNamespace())
            self.assertEqual(error, 'Claude agent is not connected. Check the server log for the underlying startup error.')
            self.assertEqual(client.status, claude.ClaudeAgentClientStatus.FailedToConnect)
            self.assertFalse(client.is_connected())

    def test_first_query_connects_and_reconnect_remains_functional(self):
        AvailableSDK.queries = []
        with patch.object(claude, 'ClaudeSDKClient', AvailableSDK):
            client = self.client()
            request = SimpleNamespace(chat_history=[{'role': 'user', 'content': 'hello'}],
                                      cancel_token=SimpleNamespace(is_cancel_requested=False))
            try:
                self.assertFalse(client.is_connected())
                self.assertIsNone(client.query(request, SimpleNamespace()))
                self.assertTrue(client.is_connected())
                first_worker = client._client_thread
                client.reconnect()
                self.assertTrue(client.is_connected())
                self.assertIsNot(client._client_thread, first_worker)
                self.assertIsNone(client.query(request, SimpleNamespace()))
                self.assertEqual(AvailableSDK.queries, ['hello', 'hello'])
            finally:
                client.disconnect()
            self.assertFalse(client.is_connected())


if __name__ == '__main__':
    unittest.main()
