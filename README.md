# MCP Server

A Python implementation of a [Model Context Protocol (MCP)](https://github.com/microsoft/model-context-protocol) server that provides various tools for AI assistants to perform actions in a secure and controlled environment.

## Installation

1. Make sure you have Python 3.12+ installed
2. Clone this repository
3. Install the dependencies:

```bash
pip install -e .
```

Or use a modern Python package manager like `uv`:

```bash
uv pip install -e .
```

## Configuration

The MCP server requires a configuration file at `~/.mcp-server/config.yml` with the following structure:

```yaml
# Brave Search API configuration
braveSearch:
  apiUrl: "https://api.search.brave.com/res/v1/web/search"
  apiKey: "your-brave-api-key"

# Database connection settings
database:
  min_size: 5
  max_size: 10
  max_queries: 50000
  max_inactive_connection_lifetime: 300  # seconds
  
  # Database connection profiles
  database1:  # This is referenced by --db-name parameter
    username: "db_user"
    password: "db_password"
    dbname: "database_name"
    host: "localhost"
    port: 5432
```

## Usage

Run the MCP server with:

```bash
python mcp_server.py --project-folder /path/to/workspace [--db-name database1]
```

Parameters:
- `--project-folder`: Required. Path to the current workspace or project directory
- `--db-name`: Optional. Name of the database configuration to use from the config file

## VS Code Integration for GitHub Copilot

To integrate this MCP server with VS Code for use with GitHub Copilot, follow these steps:

### Prerequisites

1. Make sure you have the latest version of VS Code installed
2. Ensure that GitHub Copilot is installed and properly configured in VS Code
3. The MCP server must be running on your local machine

### Configuration Steps

1. Start the MCP server in a terminal:
   ```bash
   python mcp_server.py --project-folder /path/to/your/workspace [--db-name your-db-name]
   ```

2. Open VS Code settings (File > Preferences > Settings or press `Cmd+,` on macOS) and add the following configuration to your `settings.json`:
   ```json
   "github.copilot.advanced": {
     "mcp": {
       "servers": [
         {
           "name": "Python MCP Server",
           "transport": "stdio",
           "command": "python",
           "args": [
             "/path/to/your/mcp-server/mcp_server.py",
             "--project-folder",
             "${workspaceFolder}",
             "--db-name",
             "your-db-name"
           ],
           "description": "Local Python MCP Server providing database, web, and system tools"
         }
       ]
     }
   }
   ```

3. Replace `/path/to/your/mcp-server/mcp_server.py` with the actual path to your MCP server script and `your-db-name` with your database configuration name.

4. Save the settings and restart VS Code.

### Using MCP Tools in Copilot

Once configured, GitHub Copilot can now access and use the tools provided by your MCP server:

1. Open Copilot Chat in VS Code (press `Ctrl+Shift+I` or click on the Copilot Chat icon)
2. Ask Copilot to perform actions using the tools provided by the MCP server:
   
   ```
   Can you get the current time from the system?
   ```
   
   ```
   Please search for information about Python best practices.
   ```

3. Copilot will automatically use the appropriate MCP tools to fulfill your requests.

### Troubleshooting

If you encounter issues with the MCP server integration:

1. Check that the MCP server is running correctly
2. Verify your VS Code settings are correct
3. Look for error messages in the VS Code Developer Tools (Help > Toggle Developer Tools)
4. Check the `mcp_server.log` file for any server-side errors

### Note for Team Usage

To share the MCP server configuration with your team:

1. Add the MCP server configuration to your workspace settings instead of user settings
2. Store the configuration in a `.vscode/settings.json` file in your repository
3. Ensure all team members have the MCP server installed and properly configured

## Available Tools

The MCP server provides the following tools for AI assistants:

### System Information
- `get_local_time()`: Gets the current local time
- `get_os_info()`: Returns detailed OS information
- `ls_workspace()`: Lists all files in the current project workspace, respecting .gitignore patterns

### Database Operations
- `execute_sql_query(query)`: Executes a read-only SQL query on a configured PostgreSQL database

### Web Interaction
- `query_web(query)`: Executes a search query using the Brave Search API and fetches content from top results
- `http_get_request(url, headers)`: Makes an HTTP GET request to the specified URL
- `http_post_request(url, body, headers)`: Makes an HTTP POST request to the specified URL

### Test Execution
- `run_gradle_tests(test_pattern)`: Runs Gradle tests with the specified pattern
- `run_maven_tests(test_pattern)`: Runs Maven tests with the specified pattern

## API

### MCP Server

The server uses the FastMCP implementation from the MCP Python package, configured to run over stdio transport for secure communication.

#### MCP Server Methods

- `mcp.tool()`: Decorator for registering Python functions as MCP tools
- `mcp.run(transport="stdio")`: Starts the MCP server with the specified transport

### Client Usage

Clients can connect to this MCP server using any MCP client implementation. See the [Model Context Protocol](https://github.com/microsoft/model-context-protocol) repository for client examples.

## Development

### Prerequisites

- Python 3.12+
- PostgreSQL (for database tools)
- Brave Search API key (for web search functionality)

### Project Structure

- `mcp_server.py`: Main server implementation with tool definitions
- `utils/`:
  - `args.py`: Command-line argument parsing
  - `db.py`: Database connection and context management
  - `web.py`: HTTP client utilities and HTML processing

## License

[MIT](LICENSE)