import logging
import os
from pathlib import Path
import re
from subprocess import CompletedProcess
import subprocess
import zipfile

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

def decompile_from_jars(class_name: str, jar_paths: list, root_path: Path) -> str:
    """
    Decompiles a Java class from JAR files.
    
    Args:
        class_name: The full class name (e.g., 'com.example.MyClass')
        jar_paths: List of JAR file paths to search in
        root_path: Root path where the decompiler JAR is located
        
    Returns:
        The decompiled source code or an error message
    """
    # Find first JAR containing the specified class
    class_file = class_name.replace('.', '/') + '.class'
    matching_jar: str = None
    for jar in jar_paths:
        try:
            with zipfile.ZipFile(jar, 'r') as zip_ref:
                if class_file in zip_ref.namelist():
                    matching_jar = jar
                    break
        except Exception as e:
            logger.error(f"Error checking JAR {jar}: {e}")
    
    if matching_jar is None:
        return "Error: class not found"

    decompiler_jar = root_path / "bin" / "jd-cli.jar"
    decompile_command = ["java", "-jar", str(decompiler_jar), "--outputConsole",
                            "--pattern", class_name, matching_jar]  # Remove quotes around class_name
    logger.info(f"Executing '{' '.join(decompile_command)}'")
    result = subprocess.run(
        decompile_command,
        cwd=root_path,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        logger.error(f"Java decompile command failed: {result.stderr}")
        return f"Error: Decompile command failed: {result.stderr}"
    
    # Filter out logging output from the result
    # there is logging output in the decompiler output. 
    # remove it
    lines = result.stdout.split("\n")
    source_lines = [l for l in lines if not re.match(r'^\d{2}:\d{2}:\d{2}\.\d+ (INFO|WARN)', l)]
    return '\n'.join(source_lines)
