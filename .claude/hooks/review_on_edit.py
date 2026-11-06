#!/usr/bin/env python3
"""PostToolUse hook: after Claude writes a SystemVerilog, C, C++, html or Python
file, or a <module>_prompt.md requirements file, tell Claude to review the
affected design using the guidelines in CLAUDE.md."""
import json
import os
import sys

REVIEW_EXTS = (
    ".sv", ".svh",                                   # SystemVerilog
    ".c", ".h",                                      # C
    ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx",    # C++
    ".py",                                           # Python
    ".html",                                         # html
)
PROMPT_SUFFIX = "_prompt.md"

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool_input = payload.get("tool_input") or {}
tool_response = payload.get("tool_response") or {}
path = tool_input.get("file_path") or tool_response.get("filePath") or ""

if path.endswith(REVIEW_EXTS):
    msg = (
        f"AUTO-REVIEW: {path} was just updated. Once you have finished "
        "editing this file for the current task, review its new version "
        "following the 'Code Review Guidelines' in CLAUDE.md, including "
        "every lower-level module beneath it ('Lower-level modules') and the "
        "check against its <module name>_prompt.md ('Requirements Checks'). "
        "Focus on the changed regions and anything they affect, and report "
        "findings with line references. Review each file once per task, "
        "not after every individual edit.\n\n"
        "IMPORTANT: After completing the review, write all findings to results.txt in the project root "
        "with a summary of files reviewed, all findings (errors, warnings, suggestions) with file paths "
        "and line numbers, and a final status: PASS (no blocking errors) or FAIL (blocking errors exist). "
        "Then fix all blocking errors and re-run the review until results.txt shows PASS. "
        "Only after results.txt shows PASS, respond with 'updated try again'."
    )
elif path.endswith(PROMPT_SUFFIX):
    module = os.path.basename(path)[: -len(PROMPT_SUFFIX)]
    src_dir = os.path.join(os.path.dirname(os.path.dirname(path)), "src")
    try:
        sources = sorted(
            os.path.join(src_dir, f) for f in os.listdir(src_dir) if f.endswith(REVIEW_EXTS)
        )
    except OSError:
        sources = []
    where = ", ".join(sources) if sources else f"(no sources found in {src_dir}; locate {module} via scripts/build.f)"
    msg = (
        f"AUTO-REVIEW: requirements file {path} for module '{module}' was just "
        "updated. Once you have finished editing it for the current task, "
        f"review the module's sources {where} against the new requirements "
        "following 'Requirements Checks' in CLAUDE.md, together with the rest "
        "of the 'Code Review Guidelines' (lower-level modules included), and "
        "write the results to code_reviews/<file_name.ext>_review.txt. Review "
        "once per task, not after every individual edit.\n\n"
        "IMPORTANT: After completing the review, write all findings to results.txt in the project root "
        "with a summary of files reviewed, all findings (errors, warnings, suggestions) with file paths "
        "and line numbers, and a final status: PASS (no blocking errors) or FAIL (blocking errors exist). "
        "Then fix all blocking errors and re-run the review until results.txt shows PASS. "
        "Only after results.txt shows PASS, respond with 'updated try again'."
    )
else:
    sys.exit(0)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": msg,
    }
}))
