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


def get_maven_jar(build_tool: str, class_name: str, workspace_path: str) -> str:
    command = [os.path.join(workspace_path, build_tool), "dependency:build-classpath"]
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
        return None

    classpath_output = result.stdout
    classpath_start_index = classpath_output.find("Dependencies classpath:")
    if classpath_start_index == -1:
        logger.error("Could not find 'Dependencies classpath:' in Maven output.")
        return None

    lines = classpath_output.split("\n")
    # find line containing ".jar"
    classpath_lines = [l for l in lines if ".jar" in l]
    if len(classpath_lines) != 1:
        logger.error(
            f"There should only be 1 line containing jar in list {classpath_lines}"
        )
        return None
    # Split by ':' to get individual JAR paths
    jar_paths = classpath_lines[0].split(":")
    return find_jar_for_class(class_name, jar_paths)


def get_gradle_jar(build_tool: str, class_name: str, workspace_path: str) -> str:
    command = [os.path.join(workspace_path, build_tool), "listAllJars"]
    logger.info(f"Executing '{' '.join(command)}' in {workspace_path}")
    result = subprocess.run(
        command,
        cwd=workspace_path,
        text=True,
        capture_output=True,
    )
    # result: full jar paths, each in different line, with gradle logging output
    if result.returncode != 0:
        logger.error(f"Gradle command failed: {result.stderr}")
        return None

    classpath_output = result.stdout
    lines = classpath_output.split("\n")
    # find line containing ".jar"
    classpath_lines = [l for l in lines if ".jar" in l]
    return find_jar_for_class(class_name, classpath_lines)


def find_jar_for_class(class_name: str, jar_paths: list) -> str:
    """Find first JAR containing the specified class"""
    class_file = class_name.replace(".", "/") + ".class"
    matching_jar: str = None
    for jar in jar_paths:
        try:
            with zipfile.ZipFile(jar, "r") as zip_ref:
                if class_file in zip_ref.namelist():
                    matching_jar = jar
                    break
        except Exception as e:
            logger.error(f"Error checking JAR {jar}: {e}")
            return None
    return matching_jar


def decompile_from_jar(
    class_name: str, jar_path: str, root_path: Path, workspace_path: str
) -> str:
    """
    Decompiles a Java class from JAR files.

    Args:
        class_name: The full class name (e.g., 'com.example.MyClass')
        jar_paths: List of JAR file paths to search in
        root_path: Root path where the decompiler JAR is located
        workspace_path: The path to the workspace

    Returns:
        The decompiled source code or an error message
    """
    decompiler_jar = root_path / "bin" / "jd-cli.jar"
    decompile_command = [
        os.path.join(workspace_path, "java"),
        "-jar",
        str(decompiler_jar),
        "--outputConsole",
        "--pattern",
        class_name,
        jar_path,
    ]  # Remove quotes around class_name
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
    source_lines = [
        l for l in lines if not re.match(r"^\d{2}:\d{2}:\d{2}\.\d+ (INFO|WARN)", l)
    ]
    return "\n".join(source_lines)


def get_companion_path(build_tool: str, jar_path: str, suffix: str) -> str:
    if "mvn" in build_tool:
        # Maven: if Javadoc file exists, it is in the same folder as lib jar, but ending with -javadoc.jar
        zip_path = jar_path.replace(".jar", f"-{suffix}.jar")
        if not os.path.exists(zip_path):
            logger.error(f"Error: {suffix} file not found at {zip_path}")
            return None
    else:
        # Gradle: Javadoc file is in different folder with unknown hash as name
        # Regex pattern to capture 3 groups from jar path
        # Group 1: (.*) - Matches everything before the last folder (greedy match)
        # Group 2: ([^\/]+) - Matches the last folder (not needed)
        # Group 3: ([^\/]+) - Matches the file name
        pattern = r"^(.*)\/([^\/]+)\/([^\/]+)$"
        match = re.match(pattern, jar_path)
        if match:
            root_folder = match.group(1)
            file_name = match.group(3)
            zip_path = find_file_in_folder(
                root_folder, file_name.replace(".jar", f"-{suffix}.jar")
            )

    return zip_path


def get_content_from_zip(zip_path: str, file_name: str) -> str:
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            name_list = zip_ref.namelist()
            # first entry of name_list, that ends with class_file
            class_file_path = next(
                (name for name in name_list if name.endswith(file_name)), None
            )
            if class_file_path is None:
                logger.error(f"Error: File {file_name} not found in Javadoc {zip_path}")
                return None

            with zip_ref.open(class_file_path) as f:
                content = f.read().decode("utf-8")
                return content
    except Exception as e:
        logger.error(f"Error extracting file from zip: {str(e)}", exc_info=True)
        return None


def find_file_in_folder(root_dir: str, file_name: str) -> str:
    """
    Searches for files in a given folder
    Args:
        root_dir (str): The starting directory for the search.
        file_name (str): The name of the file to search for

    Returns:
        list: A list of full paths of files that match the regex pattern.
    """
    # Compile the regex for efficiency
    compiled_regex = re.compile(f"^{file_name}$")

    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if compiled_regex.search(filename):
                return os.path.join(dirpath, filename)
    return None


def has_item_in_section(config: dict, section_name: str, item_name: str) -> bool:
    if section_name in config:
        for db_name, sub_config in config[section_name].items():
            # Skip pool configuration items (min_size, max_size, etc.)
            if isinstance(sub_config, dict) and item_name in sub_config:
                return True
    return False
