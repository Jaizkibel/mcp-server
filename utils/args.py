import argparse


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="MCP Server with configurable database credentials."
    )
    parser.add_argument(
        "--project-folder", type=str, required=False, help="Path to current workspace"
    )
    parser.add_argument(
        "--db-name", type=str, required=False, help="Database username"
    )
    args = parser.parse_args()

    return args
