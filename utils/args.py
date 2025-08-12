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
    parser.add_argument(
        "--build-tool", type=str, required=False, help="'mvn(w)' or 'gradle(w)''"
    )
    args = parser.parse_args()

    return args
