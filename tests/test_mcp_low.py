import json
import unittest
import yaml
import os
from unittest.mock import patch, AsyncMock, MagicMock
from mcp_server_low import (
    get_source,
    get_javadoc,
    http_get_request,
    config,
    list_tools,
    web_search,
    open_in_browser,
)
from httpx import Response
from pathlib import Path

local_dir = os.path.dirname(os.path.abspath(__file__))

testConfig = {
}


class TestMcpServerFunctions(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        """Load the config file before any tests run."""
        configPath = os.path.abspath(f"{Path.home()}/.mcp-server/config.yml")
        try:
            with open(configPath, "r") as file:
                config.update(yaml.safe_load(file))
            if config.get("projectFolder") is None:
                # set to location of this file
                config["projectFolder"] = local_dir
        except Exception as e:
            print(f"Failed to load mcp server config: {e}")
            try:

                with open(os.path.join(local_dir, "config.yaml"), "r") as file:
                    testConfig.update(yaml.safe_load(file))
            except Exception as e:
                print(f"Failed to load test config: {e}")

    async def test_list_tools(self):
        config["buildTool"] = "mvn"

        tools = await list_tools()
        self.assertEqual(5, len(tools))

    @unittest.skip("Browser test disabled - requires manual interaction")
    async def test_open_in_browser(self):
        result = await open_in_browser("test_page.html")
        self.assertTrue(result == "Browser successfully opened")

    async def test_web_query(self):
        findings_text = await web_search("latest python version")
        findings = json.loads(findings_text)
        self.assertIsNotNone(findings)
        self.assertEqual(5, len(findings))
        for finding in findings:
            self.assertIsNone(finding.get("error"))
            self.assertIsNotNone(finding["url"])
            self.assertIsNotNone(finding["description"])
            self.assertNotIn("<strong>", finding["description"])
            self.assertIsNotNone(finding["content"])
            self.assertIn("python", finding["content"].lower())

    async def test_source_maven(self):
        config["buildTool"] = "mvn"
        # path to maven project required
        self.assertIsNotNone(config.get("mavenProjectPath"))
        config["projectFolder"] = config.get("mavenProjectPath")
        code = await get_source("com.zaxxer.hikari.HikariDataSource")
        # original source starts with comment
        self.assertTrue(len(code) >= 200)

    async def test_javadoc_maven(self):
        config["buildTool"] = "mvn"
        # path to maven project required
        self.assertIsNotNone(config.get("mavenProjectPath"))
        config["projectFolder"] = config.get("mavenProjectPath")
        html = await get_javadoc("com.zaxxer.hikari.HikariDataSource")
        self.assertTrue(html.startswith("<!DOCTYPE HTML>"))

    # @unittest.skip("Javadoc test disabled: Needs existing Gradle Project")
    async def test_javadoc_gradle(self):
        config["buildTool"] = "gradlew"
        # path to gradle project required
        self.assertIsNotNone(config.get("gradleProjectPath"))
        config["projectFolder"] = config.get("gradleProjectPath")
        html = await get_javadoc("com.zaxxer.hikari.HikariDataSource")
        self.assertTrue(html.startswith("<!DOCTYPE HTML>"))

    # @unittest.skip("Source test disabled: Needs existing Gradle Project")
    async def test_source_gradle(self):
        config["buildTool"] = "gradlew"
        # path to gradle project required
        self.assertIsNotNone(config.get("gradleProjectPath"))
        config["projectFolder"] = config.get("gradleProjectPath")
        code = await get_source(
            "com.zaxxer.hikari.HikariDataSource"
        )
        # original source starts with comment
        self.assertTrue(code.startswith("/*\n"))

    @patch("utils.web.get_http_client")
    async def test_http_get_request_success(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.text = '{"key": "value"}'
        mock_client.get.return_value = mock_response

        result = await http_get_request("https://example.com/api")
        result_data = json.loads(result)

        self.assertEqual(200, result_data["status_code"])
        self.assertEqual("application/json", result_data["headers"]["Content-Type"])
        self.assertEqual('{"key": "value"}', result_data["body"])
        mock_client.get.assert_called_once_with("https://example.com/api", headers={})

        # no http:// allowed
        result = await http_get_request("http://example.com/api")
        result_data = json.loads(result)
        self.assertIn("error", result_data)

    @patch("utils.web.get_http_client")
    async def test_http_get_request_with_headers(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.text = "OK"
        mock_client.get.return_value = mock_response

        headers = {"Authorization": "Bearer token"}
        result = await http_get_request("https://example.com/api", headers=headers)
        result_data = json.loads(result)

        self.assertEqual(200, result_data["status_code"])
        mock_client.get.assert_called_once_with(
            "https://example.com/api", headers={"Authorization": "Bearer token"}
        )

    @patch("utils.web.get_http_client")
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
