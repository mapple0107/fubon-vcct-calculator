#!/bin/bash
REPO_DIR="$HOME/Downloads/fubon-vcct-calculator-main"
LOG="$REPO_DIR/update.log"
PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
echo "========================================" >> "$LOG"
echo "執行時間：$(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
cd "$REPO_DIR" || exit 1
export GITHUB_TOKEN="$(cat "$HOME/.fubon_token")"
echo "完成" >> "$LOG"
