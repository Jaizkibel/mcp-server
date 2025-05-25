#!/bin/bash

# assure that workspace-dir and  class-name parameters are passed
if [ $# -ne 2 ]; then
  echo "Usage: $0 <workspace-path> <class-name>"
  exit 1
fi

# Check if java is present
if ! command -v java &> /dev/null
then
    echo "Error: java is not installed or not in your PATH."
    exit 1
fi

WORKSPACE_PATH=$1
CLASS_NAME=$2
DECOMPILER_JAR=./bin/jd-cli.jar

# Check if gradlew exists in the workspace path
if [ ! -f "$WORKSPACE_PATH/gradlew" ]; then
  echo "Error: gradlew not found in $WORKSPACE_PATH."
  exit 1
fi

# using workspace path with gradle call is not sufficient.
# Need to switch
cd $WORKSPACE_PATH
JAR_PATHS=$(./gradlew listClassesInDeps | grep "$CLASS_NAME$" | awk '{print $1}')
cd - > /dev/null

JAR_COUNT=$(echo "$JAR_PATHS" | wc -l)
if [ "$JAR_COUNT" -eq 1 ]; then
  # echo "decompiling $CLASS_NAME in $JAR_PATHS"
  java -jar $DECOMPILER_JAR --outputConsole --logLevel=OFF --pattern "$CLASS_NAME" $JAR_PATHS | grep -v "INFO\\|WARN"
# else
elif [ "$JAR_COUNT" -gt 1 ]; then
  echo "Error: There are multiple jars containing this class"
  echo "Jars: $JAR_PATHS"
  exit 1
else
  echo "No matching classes found."
  exit 1
fi

