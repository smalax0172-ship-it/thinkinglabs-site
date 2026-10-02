#!/bin/bash
# Session loader. Runs at every session start and after every context
# compaction. The shell cannot read Google Drive, so it tells Claude to read
# the operating files with the Drive connector. File IDs live in the private
# Claude project instructions, not in this public repo.
set -uo pipefail
input="$(cat || true)"
source="$(printf '%s' "$input" | sed -n 's/.*"source"[[:space:]]*:[[:space:]]*"\([a-z]*\)".*/\1/p')"
if [ "$source" = "compact" ]; then
  msg="CONTEXT WAS JUST COMPACTED. The summary does not carry Syd's system. Before your next reply, silently re-read THE SPINE and THE MAP with the Google Drive connector, read_file_content by the IDs in the project instructions. No verification phrase on a re-read. Before building anything, check the Map, Drive, and past chats for something that already exists. End every reply with the closing line from the Spine."
else
  msg="SYD'S SYSTEM COMES FIRST, EVEN FOR A CODING JOB. Before your first reply, read THE SPINE and THE MAP with the Google Drive connector, read_file_content by the IDs in the project instructions, and say the verification phrase once. If a read fails, say so before working. Never rebuild what already exists. Save what you make to its proper Drive folder the same turn. End every reply with the closing line from the Spine."
fi
python3 - "$msg" <<'PY'
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}))
PY
