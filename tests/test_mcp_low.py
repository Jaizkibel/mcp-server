import json
import unittest
import yaml
import os
from unittest.mock import patch, AsyncMock, MagicMock
from mcp_server_low import (
    decompile_java_class,
    execute_sql_query,
    get_javadoc,
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

local_dir = os.path.dirname(os.path.abspath(__file__))

testConfig = {}

class TestMcpServerFunctions(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        """Load config file before any tests run."""
        configPath = os.path.abspath(f"{Path.home()}/.mcp-server/config.yml")
        try:
            with open(configPath, "r") as file:
                config.update(yaml.safe_load(file))
            if config.get("projectFolder") == None:
                # set to location of this file
                config["projectFolder"] = local_dir
        except Exception as e:
            print(f"Failed to load mcp server config: {e}")
        """Load test config file before any tests run."""
        try:

            with open(os.path.join(local_dir,"config.yaml"), "r") as file:
                testConfig.update(yaml.safe_load(file))
        except Exception as e:
            print(f"Failed to load test config: {e}")

    async def test_list_tools(self):
        config["buildTool"] = "mvn"

        tools = await list_tools()
        self.assertEqual(len(tools), 6)

    async def test_postgres_sql_query(self):
        db_name = 'musiciandb'
        result = await execute_sql_query(db_name, 'SELECT 2 + 2 as result')
        self.assertEqual(result, "[{\"result\": 4}]")

        result = await execute_sql_query(db_name, "SELECT NOW() as result")
        self.assertTrue(result.startswith("[{\"result\": \""))

        result = await execute_sql_query(db_name, "SELECT 1.23456789 as result")
        self.assertEqual(result, "[{\"result\": 1.23456789}]")

    @unittest.skip("Browser test disabled - requires manual interaction")
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

    async def test_decompile_class_maven(self):
        config["buildTool"] = "mvn"
        # path to maven project required
        config["projectFolder"] = testConfig.get("mavenProjectPath")
        code = await decompile_java_class("com.zaxxer.hikari.HikariDataSource")
        self.assertTrue(code.startswith("package"))

    async def test_javadoc_maven(self):
        config["buildTool"] = "mvn"
        # path to maven project required
        config["projectFolder"] = testConfig.get("mavenProjectPath")
        html = await get_javadoc("com.zaxxer.hikari.HikariDataSource")
        self.assertTrue(html.startswith("<!DOCTYPE HTML>"))

    async def test_decompile_class_gradle(self):
        config["buildTool"] = "gradlew"
        # path to maven project required
        config["projectFolder"] = testConfig.get("gradleProjectPath")
        code = await decompile_java_class("com.zaxxer.hikari.HikariDataSource")
        self.assertTrue(code.startswith("package"))

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
