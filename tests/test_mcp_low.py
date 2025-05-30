import json
import unittest
import yaml
import os
from unittest.mock import patch, AsyncMock, MagicMock
from mcp_server_low import (
    execute_sql_query,
    http_get_request,
    config,
    list_tools,
    web_search,
    open_in_browser
)    
import datetime
import requests
from httpx import Response
from pathlib import Path

class TestMcpServerFunctions(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        """Load config file before any tests run."""
        configPath = os.path.abspath(f"{Path.home()}/.mcp-server/config.yml")
        try:
            with open(configPath, "r") as file:
                config.update(yaml.safe_load(file))
            print("Successfully loaded config for testing")
            if config.get("projectFolder") == None:
                # set to location of this file
                config["projectFolder"] = os.path.dirname(os.path.abspath(__file__))
        except Exception as e:
            print(f"Failed to load config: {e}")

    async def test_list_tools(self):
        config["buildTool"] = "Maven"

        tools = await list_tools()
        self.assertEqual(len(tools), 7)

    async def test_postgres_sql_query(self):
        db_name = 'musiciandb'
        result = await execute_sql_query(db_name, 'SELECT 2 + 2 as result')
        self.assertEqual(result, "[{\"result\": 4}]")

        result = await execute_sql_query(db_name, "SELECT NOW() as result")
        self.assertTrue(result.startswith("[{\"result\": \""))

        result = await execute_sql_query(db_name, "SELECT 1.23456789 as result")
        self.assertEqual(result, "[{\"result\": 1.23456789}]")

    async def test_open_in_browser(self):
        result = await open_in_browser("test_page.html")
        self.assertTrue(result == "Browser successfully opened")

    async def test_web_query(self):
        findings_text = await web_search("latest gradle version")
        findings = json.loads(findings_text)
        self.assertIsNotNone(findings)
        self.assertEqual(len(findings), 3)
        for finding in findings:
            self.assertIsNotNone(finding["url"])
            self.assertIsNotNone(finding["description"])
            self.assertNotIn("<strong>", finding["description"])
            self.assertIsNotNone(finding["content"])
            self.assertIn("gradle", finding["content"].lower())

    @patch('utils.web.get_http_client')
    async def test_http_get_request_success(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_response.text = '{"key": "value"}'
        mock_client.get.return_value = mock_response

        result = await http_get_request("https://example.com/api")
        result_data = json.loads(result)

        self.assertEqual(result_data["status_code"], 200)
        self.assertEqual(result_data["headers"]["Content-Type"], "application/json")
        self.assertEqual(result_data["body"], '{"key": "value"}')
        mock_client.get.assert_called_once_with("https://example.com/api", headers={})

        # no http:// allowed
        result = await http_get_request("http://example.com/api")
        result_data = json.loads(result)
        self.assertIn("error", result_data)

    @patch('utils.web.get_http_client')
    async def test_http_get_request_with_headers(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.text = 'OK'
        mock_client.get.return_value = mock_response

        headers = {"Authorization": "Bearer token"}
        result = await http_get_request("https://example.com/api", headers=headers)
        result_data = json.loads(result)

        self.assertEqual(result_data["status_code"], 200)
        mock_client.get.assert_called_once_with(
            "https://example.com/api",
            headers={"Authorization": "Bearer token"}
        )

    @patch('utils.web.get_http_client')
    async def test_http_get_request_error(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_client.get.side_effect = Exception("Connection error")

        result = await http_get_request("https://example.com/api")
        result_data = json.loads(result)

        self.assertIn("error", result_data)
        self.assertIn("Connection error", result_data["error"])

if __name__ == "__main__":
    unittest.main()
