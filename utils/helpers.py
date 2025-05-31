import logging
import os
from subprocess import CompletedProcess
import subprocess

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

def get_maven_jars(build_tool: str, workspace_path: str):
    command = [build_tool, "dependency:build-classpath"]
    logger.info(f"Executing '{' '.join(command)}'")
    result = subprocess.run(
        command,
        cwd=workspace_path,
        text=True,
        capture_output=True,
    )
    # result: full jar paths separated by ':', with gradle logging output
    if result.returncode != 0:
        logger.error(f"Maven command failed: {result.stderr}")
        return f"Error: Maven command failed: {result.stderr}"

    classpath_output = result.stdout
    classpath_start_index = classpath_output.find("Dependencies classpath:")
    if classpath_start_index == -1:
        logger.error("Could not find 'Dependencies classpath:' in Maven output.")
        return "Error: Could not find classpath in Maven output."

    lines = classpath_output.split("\n")
    # find line containing ".jar"
    classpath_lines = [l for l in lines if ".jar" in l]
    if len(classpath_lines) != 1:
        logger.error(f"There should only be 1 line containing jar in list {classpath_lines}")
        return "Error: Unable to find libraries"
    # Split by ':' to get individual JAR paths
    jar_paths = classpath_lines[0].split(":")
    return jar_paths

def get_gradle_jars(build_tool: str, workspace_path: str):
    command = [build_tool, "listAllJars"]
    logger.info(f"Executing '{' '.join(command)}'")
    result = subprocess.run(
        command,
        cwd=workspace_path,
        text=True,
        capture_output=True,
    )
    # result: full jar paths, each in different line, with gradle logging output
    if result.returncode != 0:
        logger.error(f"Gradle command failed: {result.stderr}")
        return f"Error: Gradle command failed: {result.stderr}"

    classpath_output = result.stdout
    lines = classpath_output.split('\n')
    # find line containing ".jar"
    classpath_lines = [l for l in lines if ".jar" in l]
    return classpath_lines
