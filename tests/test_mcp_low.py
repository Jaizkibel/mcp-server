import json
import unittest
import yaml
import os
from unittest.mock import patch, AsyncMock, MagicMock
from mcp_server_low import (
  get_source,
  execute_sql_statement,
  get_javadoc,
  http_get_request,
  config,
  list_tools,
  web_search,
  open_in_browser,
)
import datetime
import requests
from httpx import Response
from pathlib import Path

local_dir = os.path.dirname(os.path.abspath(__file__))

testConfig = {"mavenProjectPath": "/Users/ANNO.KRUESEMANN/IdeaProjects/github/cp-postbox-service"}


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

  @unittest.skip("needs implementation")
  async def test_postgres_selects(self):
    db_name = "musiciandb"
    result = await execute_sql_statement(
        db_name, "SELECT 2 + 2 as result", read_only=True
    )
    self.assertEqual('[{"result": 4}]', result)

    result = await execute_sql_statement(
        db_name, "SELECT NOW() as result", read_only=True
    )
    self.assertTrue(result.startswith('[{"result": "'))

    result = await execute_sql_statement(
        db_name, "SELECT 1.23456789 as result", read_only=True
    )
    self.assertEqual('[{"result": 1.23456789}]', result)

  @unittest.skip("needs implementation")
  async def test_postgres_changes(self):
    db_name = "musiciandb"
    # insert 1 row
    result = await execute_sql_statement(
        db_name,
        "insert into musician.band (founded, genre, name) values ('1962-01-01', 'Britpop', 'Beatles')",
        read_only=False
    )
    self.assertIsNotNone(result)
    self.assertEqual(
        '{"status": "INSERT 0 1", "message": "Statement executed successfully"}',
        result
    )
    # delete it again
    result = await execute_sql_statement(
        db_name, "delete from musician.band where name = 'Beatles'", read_only=False
    )
    self.assertEqual(
        '{"status": "DELETE 1", "message": "Statement executed successfully"}',
        result
    )

  @unittest.skip("needs sql server docker running")
  async def test_sqlserver_selects(self):
    db_name = "portaldb"
    result = await execute_sql_statement(
        db_name, "SELECT 2 + 2 as result", read_only=True
    )
    self.assertEqual('[{"result": 4}]', result)

    result = await execute_sql_statement(
        db_name, "SELECT current_timestamp as result", read_only=True
    )
    self.assertTrue(result.startswith('[{"result": "'))

    result = await execute_sql_statement(
        db_name, "SELECT 1.23456789 as result", read_only=True
    )
    self.assertEqual('[{"result": 1.23456789}]', result)

  @unittest.skip("needs sql server docker running")
  async def test_sqlserver_changes(self):
    db_name = "portaldb"
    # insert 1 row
    result = await execute_sql_statement(
        db_name,
        "insert into postbox.document_name (name, language, ui_display_value) values ('MCP_TEST', 'DE', 'Test')",
        read_only=False
    )
    self.assertIsNotNone(result)
    self.assertEqual(
        '{"affected_rows": 1, "message": "Statement executed successfully"}',
        result
    )
    # delete it again
    result = await execute_sql_statement(
        db_name, "delete from postbox.document_name where name = 'MCP_TEST'", read_only=False
    )
    self.assertEqual(
        '{"affected_rows": 1, "message": "Statement executed successfully"}',
        result
    )

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

  # @unittest.skip("Source test disabled: Needs existing Maven Project")
  async def test_source_maven(self):
    config["buildTool"] = "mvn"
    # path to maven project required
    self.assertIsNotNone(testConfig.get("mavenProjectPath"))
    config["projectFolder"] = testConfig.get("mavenProjectPath")
    code = await get_source("com.zaxxer.hikari.HikariDataSource")
    # original source starts with comment
    self.assertTrue(len(code) >= 200)

  # @unittest.skip("Javadoc test disabled: Needs existing Maven Project")
  async def test_javadoc_maven(self):
    config["buildTool"] = "mvn"
    # path to maven project required
    self.assertIsNotNone(testConfig.get("mavenProjectPath"))
    config["projectFolder"] = testConfig.get("mavenProjectPath")
    html = await get_javadoc("com.zaxxer.hikari.HikariDataSource")
    self.assertTrue(html.startswith("<!DOCTYPE HTML>"))

  @unittest.skip("Javadoc test disabled: Needs existing Gradle Project")
  async def test_javadoc_gradle(self):
    config["buildTool"] = "gradle"
    # path to gradle project required
    self.assertIsNotNone(testConfig.get("mavenProjectPath"))
    config["projectFolder"] = testConfig.get("gradleProjectPath")
    html = await get_javadoc("com.zaxxer.hikari.HikariDataSource")
    self.assertTrue(html.startswith("<!DOCTYPE HTML>"))

  @unittest.skip("Source test disabled: Needs existing Gradle Project")
  async def test_source_gradle(self):
    config[
      "projectFolder"] = "/home/kruese/IdeaProjects/github/spring-cloud-kubernetes-leader-example"
    config["buildTool"] = "gradle"
    # path to gradle project required
    # config["projectFolder"] = testConfig.get("gradleProjectPath")
    code = await get_source(
      "io.fabric8.kubernetes.client.extended.leaderelection.LeaderElector")
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
    mock_client.get.assert_called_once_with("https://example.com/api",
                                            headers={})

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
