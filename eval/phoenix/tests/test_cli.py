import argparse

import pytest

from eval.phoenix.run_experiment import server_argv


def test_child_argv_preserves_flags_spaces_and_unicode():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-command", type=server_argv)
    parsed = parser.parse_args(
        [
            "--server-command",
            '["C:/Caller Path/uv.exe", "run", "--no-sync", "--project", "café"]',
        ]
    )
    assert parsed.server_command == [
        "C:/Caller Path/uv.exe",
        "run",
        "--no-sync",
        "--project",
        "café",
    ]


@pytest.mark.parametrize("value", ['"shell string"', "[]", "[1]", '["uv", ""]'])
def test_child_argv_rejects_non_argument_arrays(value):
    with pytest.raises(argparse.ArgumentTypeError):
        server_argv(value)
