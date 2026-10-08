from vericode.agent import parse_action
from vericode.falsify import extract_python_block


def test_plain_json():
    assert parse_action('{"tool": "diff", "args": {}}')["tool"] == "diff"


def test_json_inside_prose_and_fence():
    t = 'Sure!\n```json\n{"thought": "x", "tool": "read_file", "args": {"path": "a.py"}}\n```'
    assert parse_action(t)["args"]["path"] == "a.py"


def test_braces_inside_string_values():
    t = '{"tool": "write_file", "args": {"path": "a.py", "content": "d = {1: 2}\\n"}}'
    assert parse_action(t)["args"]["content"] == "d = {1: 2}\n"


def test_garbage_returns_none():
    assert parse_action("I will now fix it") is None
    assert parse_action('{"no_tool": 1}') is None


def test_extract_python_block():
    assert extract_python_block("x\n```python\ndef test_a():\n    pass\n```\ny").startswith("def test_a")
    assert extract_python_block("no code here") is None
