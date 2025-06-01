# MCP Server

A Python implementation of a [Model Context Protocol (MCP)](https://github.com/microsoft/model-context-protocol) server that provides various tools for AI assistants to perform actions in a secure and controlled environment.

Be aware that this README is mostly written by AI.

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
# Operating system
os: Linux

# Brave Search API configuration
braveSearch:
  apiUrl: "https://api.search.brave.com/res/v1/web/search"
  apiKey: "your-brave-api-key"

# Database connection settings
database:
  min_size: 1
  max_size: 3
  max_queries: 5000  # optional: connections are recycled after this many queries
  max_inactive_connection_lifetime: 300  # optional: seconds
  
  # Database connection profiles
  musiciandb:  # This is referenced by --db-name parameter
    username: "readonly"
    password: "readonly"
    dbname: "postgresdb"
    host: "localhost"
    port: 5432

# Browser command for opening URLs
browserCommand: firefox
```

### Gradle Setup

To make use the `get_source`tool in Gradle project, you need to add this task to `build.gradle`

```gradle
tasks.register('listClassesInDeps')  {
    doLast {
        configurations.compileClasspath.resolve().each { file ->
            if (file.name.endsWith('.jar')) {
                println file.absolutePath
            }
        }
        configurations.runtimeClasspath.resolve().each { file ->
            if (file.name.endsWith('.jar')) {
                println file.absolutePath
            }
        }
    }
}
```

## Usage

Run the MCP server with:

```bash
python mcp_server_low.py [--project-folder /path/to/workspace] [--db-name musiciandb] [--build-tool Maven|Gradle]
```

Parameters:
- `--project-folder`: Optional. Path to the current workspace or project directory
- `--db-name`: Optional. Name of the database configuration to use from the config file
- `--build-tool`: Optional. Specify 'Maven' or 'Gradle' for Java project support

## VS Code Integration for GitHub Copilot

To integrate this MCP server with VS Code for use with GitHub Copilot, follow these steps:

### Prerequisites

1. Make sure you have the latest version of VS Code installed
2. Ensure that GitHub Copilot is installed and properly configured in VS Code
3. The MCP server must be running on your local machine

### Configuration Steps

Open VS Code settings (File > Preferences > Settings or press `Cmd+,` on macOS) and add the following configuration to your `settings.json`:
   ```json
   "github.copilot.advanced": {
     "mcp": {
       "servers": [
         {
           "name": "Python MCP Server",
           "transport": "stdio",
           "command": "uv",
           "args": [
             "/path/to/your/mcp-server/mcp_server_low.py",
             "--project-folder",
             "${workspaceFolder}",
             "--db-name",
             "musiciandb",
             "--build-tool",
             "Maven"
           ],
           "description": "Local Python MCP Server providing database, web, and system tools"
         }
       ]
     }
   }
   ```

2. Replace `/path/to/your/mcp-server/mcp_server.py` with the actual path to your MCP server script and `your-db-name` with your database configuration name.

3. Save the settings and restart VS Code.

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

### Database Operations
- `execute_sql_query(query)`: Executes a read-only SQL query on a configured PostgreSQL or SqlServer database

### Web Interaction
- `web_search(query)`: Executes a search query using the Brave Search API and fetches content from top results
- `open_in_browser(url)`: Opens a URL or file in the local browser
- `http_get_request(url, headers)`: Makes an HTTP GET request to the specified URL

### Test Execution
- `run_gradle_tests(test_pattern)`: Runs Gradle tests with the specified pattern
- `run_maven_tests(test_pattern)`: Runs Maven tests with the specified pattern

### Java Source Tools
- `get_source(class_name)`: Returns the source of a Java class
- `get_javadoc(class_name)`: Gets Javadoc for a Java class

## API

### MCP Server

The server uses the low level MCP implementation from the MCP Python package, configured to run over stdio transport for secure communication.
Low level is needed for 2 reasons:
* Entries in tool list depend on start arguments
* `roots/list` is used to determine project workspace path if offered by MCP client (Copilot does)

#### MCP Server Methods

- `@server.list_tools()`: Decorator for registering a function that returns available MCP tools
- `@server.call_tool()`: Decorator for registering a function that handles all tool calls
- `server.run()`: Starts the MCP server with stdio transport and initialization options
- `server_lifespan()`: Async context manager for managing server startup and shutdown lifecycle, including resource cleanup

### Client Usage

Clients can connect to this MCP server using any MCP client implementation. See the [Model Context Protocol](https://github.com/microsoft/model-context-protocol) repository for client examples.

## Development

### Prerequisites

- Python 3.12+
- PostgreSQL (for database tools)
- Brave Search API key (for web search functionality)

### Project Structure

- `mcp_server_low.py`: Main server implementation with tool definitions
- `pyproject.toml`: Project and package management configuration (using `uv`)
- `bin/`: Contains helper scripts and executables
  - `gradle-decompile.sh`: Script for decompiling Gradle projects
  - `jd-cli.jar`: Java Decompiler command-line tool
- `tests/`: Contains unit and integration tests
  - `test_mcp_low.py`: Tests for the low-level MCP server
  - `test_page.html`: Test HTML page
- `utils/`: Utility modules
  - `args.py`: Command-line argument parsing
  - `db.py`: Database connection and context management
  - `helpers.py`: General utility functions
  - `mcp.py`: MCP-related utilities
  - `web.py`: HTTP client utilities and HTML processing

## License

[MIT](LICENSE)