#!/bin/sh
# Builds the chessboard detector harness. Run from anywhere; paths are resolved relative to
# this script, which lives two levels below the repository root.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
clang++ -std=c++14 -O2 -g \
    -I"$ROOT" \
    -F"$ROOT/OpenCV" \
    "$HERE/main.cpp" "$ROOT/VSChessboardDetector.cpp" \
    -framework opencv2 -framework Accelerate -framework OpenCL \
    -o "$HERE/harness"
echo "built $HERE/harness"
echo "run as:  DYLD_FRAMEWORK_PATH=$ROOT/OpenCV $HERE/harness <frame.png> [plumblines.csv]"
