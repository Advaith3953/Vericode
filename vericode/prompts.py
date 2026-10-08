"""Prompts and tool documentation shared by the agent and the falsifier."""

FALSIFY_MARKER = "[[VERICODE_ADVERSARIAL_TESTS_REQUEST]]"

TOOL_SPECS = {
    "list_files": ("list_files()", "List all files in the repository."),
    "read_file": ("read_file(path, start=1, end=None)", "Read a file with line numbers."),
    "search_code": ("search_code(pattern, glob='*.py')", "Regex search across files."),
    "edit_file": ("edit_file(path, old, new)", "Replace the single exact occurrence of `old` with `new`."),
    "write_file": ("write_file(path, content)", "Create or overwrite a whole file."),
    "create_test": ("create_test(name, code)", "Create tests/test_adv_<name>.py from a complete pytest file."),
    "run_tests": ("run_tests(path=None)", "Run pytest on the whole suite, or on one path."),
    "diff": ("diff()", "Show the unified diff of all your changes so far."),
    "rollback": ("rollback(path=None)", "Undo your changes to one file, or to everything. Also deletes files you created."),
    "finish": ("finish(summary)", "Declare the task done."),
}


def system_prompt() -> str:
    tools = "\n".join(f"- {sig}: {desc}" for sig, desc in TOOL_SPECS.values())
    return (
        "You are a careful software engineer fixing an issue in a small Python repository.\n"
        "Each turn, reply with exactly ONE JSON object and nothing else:\n"
        '{"thought": "<short reasoning>", "tool": "<tool name>", "args": {...}}\n\n'
        f"Tools:\n{tools}\n\n"
        "Rules:\n"
        "- Read the relevant code and tests before editing.\n"
        "- Existing tests are read-only. Do not try to weaken or delete them.\n"
        "- Implement everything the issue asks for, including the edge cases it mentions.\n"
        "- Run the tests before you call finish."
    )


def user_prompt(issue: str, file_listing: str) -> str:
    return (
        f"ISSUE:\n{issue}\n\nRepository files:\n{file_listing}\n\n"
        "Fix the issue. Reply with one JSON action."
    )


def falsify_prompt(issue: str, diff: str, sources: str, files: str, n: int) -> str:
    return (
        f"{FALSIFY_MARKER}\n"
        "You are a skeptical reviewer. An engineer claims to have fixed the issue below.\n"
        f"Write up to {n} pytest tests that would FAIL if the fix is wrong or incomplete.\n\n"
        "Guidelines:\n"
        "- Derive expected behaviour ONLY from the issue text, never from the implementation.\n"
        "- Target boundaries, edge cases and every requirement the issue lists.\n"
        "- Do not test private details. Import from the repo's top-level modules.\n"
        "- Return ONE complete pytest file inside a single ```python code block.\n\n"
        f"ISSUE:\n{issue}\n\nFILES:\n{files}\n\nPATCH (diff):\n{diff}\n\nCHANGED SOURCE FILES:\n{sources}\n"
    )
