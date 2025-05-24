import logging
import os

def init_logging(log_directory: str, file_name: str):
    # Create the directory if it doesn't exist
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)

    logging.basicConfig(
        filename=os.path.join("log", "mcp_server_low.log"),
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
