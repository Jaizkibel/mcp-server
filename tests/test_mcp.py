import json
import unittest
import yaml
import os
from unittest.mock import patch, AsyncMock, MagicMock
from mcp_server import (
    get_local_time,
    execute_sql_query,
    get_os_info,
    query_web,
    strip_text_from_html,
    http_get_request,
    http_post_request,
    ls_workspace,
    run_gradle_tests,
    config
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
        except Exception as e:
            print(f"Failed to load config: {e}")

    async def test_get_local_time(self):
        result = await get_local_time()
        current_time = datetime.datetime.now()
        result_time = datetime.datetime.strptime(result, "%Y-%m-%d %H:%M:%S.%f")
        time_difference = abs((current_time - result_time).total_seconds())
        self.assertLess(time_difference, 1)

    async def test_get_os_info(self):
        result = await get_os_info()
        self.assertIn('"version":', result)

    async def test_ls_workspace(self):
        test_path = os.path.dirname(os.path.abspath(__file__))
        print(test_path)        
        config['projectPath'] = f"../{test_path}"

        result = await ls_workspace()
        print(result)

        # make list of result string by separating by line break
        result_list = result.split("\n")
        # assert result_list size is less then 20
        self.assertLess(len(result_list), 20)
        

    async def test_execute_sql_query(self):
        config["dbName"] = "musiciandb"
        result = await execute_sql_query('SELECT 2 + 2 as result')
        self.assertEqual(result, "[{\"result\": 4}]")

        result = await execute_sql_query("SELECT NOW() as result")
        self.assertTrue(result.startswith("[{\"result\": \""))

        result = await execute_sql_query("SELECT 1.23456789 as result")
        self.assertEqual(result, "[{\"result\": 1.23456789}]")

    async def test_web_query(self):
        findings_text = await query_web("latest gradle version")
        findings = json.loads(findings_text)
        self.assertIsNotNone(findings)
        self.assertEqual(len(findings), 3)
        for finding in findings:
            self.assertIsNotNone(finding["url"])
            self.assertIsNotNone(finding["description"])
            self.assertNotIn("<strong>", finding["description"])
            self.assertIsNotNone(finding["content"])
            self.assertIn("gradle", finding["content"].lower())

    async def test_html_strip(self):
        html = "<html><head><title>Test</title></head><body><p>Hello, world!</p></body></html>"
        result = strip_text_from_html(html)
        self.assertEqual(result, "Hello, world!")

        html = requests.get("https://gradle.org/releases/", verify=False).content
        result = strip_text_from_html(html)
        self.assertIn("v8.13", result)    

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

    @patch('utils.web.get_http_client')
    async def test_http_post_request_success(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 201
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_response.text = '{"id": 123}'
        mock_client.post.return_value = mock_response

        body = {"name": "test"}
        result = await http_post_request("https://example.com/api", body=body)
        result_data = json.loads(result)

        self.assertEqual(result_data["status_code"], 201)
        self.assertEqual(result_data["body"], '{"id": 123}')
        mock_client.post.assert_called_once_with(
            "https://example.com/api",
            json={"name": "test"},
            headers={'Content-Type': 'application/json'}
        )

    @patch('utils.web.get_http_client')
    async def test_http_post_request_with_headers(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.text = 'OK'
        mock_client.post.return_value = mock_response

        headers = {"X-Custom-Header": "value"}
        body = {"data": "test"}
        result = await http_post_request(
            "https://example.com/api",
            body=body,
            headers=headers
        )
        result_data = json.loads(result)

        self.assertEqual(result_data["status_code"], 200)
        mock_client.post.assert_called_once_with(
            "https://example.com/api",
            json={"data": "test"},
            headers={"X-Custom-Header": "value", "Content-Type": "application/json"}
        )

    @patch('utils.web.get_http_client')
    async def test_http_post_request_error(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_client.post.side_effect = Exception("Post failed")
# 
        result = await http_post_request("https://example.com/api", body={"test": "data"})
        result_data = json.loads(result)
# 
        self.assertIn("error", result_data)
        self.assertIn("Post failed", result_data["error"])

    @unittest.skip("Disabled test: test_gradle_test_execution")
    async def test_gradle_test_execution(self):
        config["projectFolder"] = "/Users/ANNO.KRUESEMANN/IdeaProjects/bitbucket/boot-demo"
        result = await run_gradle_tests('*DemoReadySpecification')

        self.assertIn("BUILD SUCCESSFUL", result)
        # print(result)

if __name__ == "__main__":
    unittest.main()
