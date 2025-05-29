import logging
import os
from subprocess import CompletedProcess

logger = logging.getLogger(__name__)

def init_logging(log_directory: str, file_name: str):
    # Create the directory if it doesn't exist
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)

    logging.basicConfig(
        filename=os.path.join("log", "mcp_server_low.log"),
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

def handle_cmd_result(result: CompletedProcess) -> str:
    # Check if the command was successful
    if result.returncode == 0:
        logger.debug(f"Command executed successfully: {result.stdout}")
        return result.stdout
    else:
        errmsg = result.stdout + "\n" + result.stderr
        logger.error(f"Command failed: {errmsg}")
        return f"Error: {errmsg}"


