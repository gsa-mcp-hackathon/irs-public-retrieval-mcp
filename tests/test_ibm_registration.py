"""Offline registration checks preserve caller-selected ADK environment identity."""

from __future__ import annotations

import io
import json
import os
import runpy
import shutil
import subprocess
import sys
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import yaml

REPO = Path(__file__).resolve().parents[1]
KIT = REPO / "deploy/ibm/local-mcp-toolkit"


class EnvironmentRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        git_bash = Path(os.environ.get("ProgramFiles", "")) / "Git/bin/bash.exe"
        cls.bash = str(git_bash) if git_bash.is_file() else shutil.which("bash")
        if not cls.bash:
            raise unittest.SkipTest("Bash unavailable")

    def setUp(self):
        self.root = REPO / ".pytest_cache" / f"ibm-registration-{uuid.uuid4().hex}"
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root)
        self.kit = self.root / "deploy/ibm/local-mcp-toolkit"
        self.kit.mkdir(parents=True)
        for name in (
            "register-toolkit.sh",
            "read-environment.py",
            "toolkit.yaml",
            "server.py",
            "requirements.txt",
        ):
            if (KIT / name).exists():
                shutil.copy2(KIT / name, self.kit / name)
        source = self.root / "src/example_server"
        source.mkdir(parents=True)
        (source / "__init__.py").write_text("", encoding="utf-8")
        self.config = self.root / "config.yaml"
        self.log = self.root / "adk.jsonl"
        self.modules = self.root / "modules"
        config_module = self.modules / "ibm_watsonx_orchestrate/cli/config.py"
        config_module.parent.mkdir(parents=True)
        config_module.write_text(
            "import os\nfrom pathlib import Path\n"
            "path = Path(os.environ['ADK_FIXTURE_CONFIG'])\n"
            "DEFAULT_CONFIG_FILE_FOLDER = str(path.parent)\n"
            "DEFAULT_CONFIG_FILE = path.name\n"
            "ENVIRONMENTS_SECTION_HEADER = 'environments'\n"
            "ENV_WXO_URL_OPT = 'wxo_url'\n"
            "ENV_AUTH_TYPE = 'auth_type'\n"
            "PROTECTED_ENV_NAME = 'local'\n"
            "import yaml\n"
            "class Config:\n"
            "    def __init__(self):\n"
            "        if os.environ.get('ADK_FIXTURE_NOISY_CONFIG') == 'yes':\n"
            "            print('synthetic SDK initialization')\n"
            "        self.data = yaml.safe_load(path.read_text('utf-8')) "
            "if path.exists() else {}\n"
            "        self.data = self.data or {}\n"
            "    def get(self, section):\n"
            "        return self.data.get(section, {})\n",
            encoding="utf-8",
        )
        type_module = (
            self.modules / "ibm_watsonx_orchestrate/cli/commands/environment/types.py"
        )
        type_module.parent.mkdir(parents=True)
        type_module.write_text(
            "from enum import Enum\n"
            "class EnvironmentAuthType(str, Enum):\n"
            "    IBM_CLOUD_IAM = 'ibm_iam'\n"
            "    MCSP = 'mcsp'\n"
            "    CPD = 'cpd'\n",
            encoding="utf-8",
        )
        utilities = self.modules / "ibm_watsonx_orchestrate/client/utils.py"
        utilities.parent.mkdir(parents=True)
        utilities.write_text(
            "def is_ibm_cloud_platform(url=None):\n"
            "    assert url is not None, 'inference must supply target URL'\n"
            "    return '.cloud.ibm.com' in url\n",
            encoding="utf-8",
        )
        commands = self.root / "bin"
        commands.mkdir()
        orchestrate = commands / "orchestrate"
        orchestrate.write_text(
            '#!/usr/bin/env bash\nexec "$PYTHON" "$ADK_FIXTURE_STUB" "$@"\n',
            encoding="utf-8",
            newline="\n",
        )
        orchestrate.chmod(0o755)
        self.stub = self.root / "stub.py"
        self.stub.write_text(
            "import json, os, pathlib, sys, yaml\n"
            "args = sys.argv[1:]\n"
            "with open(os.environ['ADK_LOG'], 'a', encoding='utf-8') as log:\n"
            "    log.write(json.dumps(args) + '\\n')\n"
            "path = pathlib.Path(os.environ['ADK_FIXTURE_CONFIG'])\n"
            "config = yaml.safe_load(path.read_text('utf-8')) if path.is_file() "
            "else {}\n"
            "envs = config.setdefault('environments', {})\n"
            "if args[:2] == ['env', 'list']:\n"
            "    for name, details in envs.items():\n"
            "        print(name, details.get('wxo_url', 'N/A'))\n"
            "elif args[:2] == ['env', 'add']:\n"
            "    supplied = dict(zip(args[2::2], args[3::2]))\n"
            "    name = supplied['--name']\n"
            "    assert name not in envs, 'existing identities must not change'\n"
            "    envs[name] = {'wxo_url': supplied['--url'], "
            "'auth_type': supplied['--type']}\n"
            "    path.write_text(yaml.safe_dump(config), encoding='utf-8')\n"
            "elif args[:2] == ['env', 'activate']:\n"
            "    assert args[2] in envs, 'activation requires exact name'\n"
            "elif args[:2] == ['toolkits', 'import']:\n"
            "    assert pathlib.Path(args[3]).is_file()\n"
            "elif args[:2] != ['toolkits', 'list']:\n"
            "    raise AssertionError('unexpected ADK command: ' + repr(args))\n",
            encoding="utf-8",
        )

    def write_config(self, environments):
        self.config.write_text(
            yaml.safe_dump({"environments": environments}), encoding="utf-8"
        )

    def run_script(self, *, overrides=None, arguments=()):
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("WXO_", "TOOLKIT_"))
            and key not in ("PACKAGE_NAME", "PYTHON", "PYTHONPATH", "ADK_PYTHON")
        }
        environment.update(
            PATH=str(self.root / "bin") + os.pathsep + environment["PATH"],
            PYTHON=sys.executable.replace("\\", "/"),
            PYTHONPATH=str(self.modules),
            ADK_FIXTURE_CONFIG=str(self.config).replace("\\", "/"),
            ADK_FIXTURE_STUB=str(self.stub).replace("\\", "/"),
            ADK_LOG=str(self.log).replace("\\", "/"),
            TOOLKIT_NAME="offline-toolkit",
            WXO_ENV_NAME="caller-target",
            WXO_INSTANCE_URL="https://target.example.invalid/instance",
            WXO_API_KEY="synthetic-offline-key",
        )
        environment.update(overrides or {})
        try:
            return subprocess.run(
                [self.bash, str(self.kit / "register-toolkit.sh"), *arguments],
                cwd=self.root,
                env=environment,
                input="",
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired as error:
            error.add_note(f"Registration fixture: {self.id()}")
            error.add_note(f"Partial stdout: {error.stdout!r}")
            error.add_note(f"Partial stderr: {error.stderr!r}")
            raise

    def test_timeout_preserves_partial_capture(self):
        error = subprocess.TimeoutExpired(
            ["synthetic-registration"],
            60,
            output="observed fixture stage",
            stderr="observed fixture diagnostic",
        )
        with patch.object(subprocess, "run", side_effect=error):
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                self.run_script()
        self.assertIs(caught.exception, error)
        self.assertEqual(error.timeout, 60)
        self.assertTrue(
            any("observed fixture stage" in note for note in error.__notes__)
        )
        self.assertTrue(
            any("observed fixture diagnostic" in note for note in error.__notes__)
        )

    def run_helper(
        self,
        *,
        auth_type="ibm_iam",
        url="https://target.example.invalid/instance",
        unavailable_sdk=False,
    ):
        modules = {}
        for name in (
            "ibm_watsonx_orchestrate.cli.config",
            "ibm_watsonx_orchestrate.cli.commands.environment.types",
            "ibm_watsonx_orchestrate.client.utils",
        ):
            module = ModuleType(name)
            path = self.modules / (name.replace(".", "/") + ".py")
            with patch.dict(os.environ, ADK_FIXTURE_CONFIG=str(self.config)):
                code = compile(path.read_text("utf-8"), str(path), "exec")
                exec(code, module.__dict__)
            modules[name] = module
        if unavailable_sdk:
            modules["ibm_watsonx_orchestrate.cli.config"] = None
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.dict(sys.modules, modules),
            patch.dict(
                os.environ,
                WXO_ENV_NAME="caller-target",
                WXO_INSTANCE_URL=url,
                WXO_ENV_TYPE=auth_type,
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            returned = runpy.run_path(str(KIT / "read-environment.py"))["main"]()
        return SimpleNamespace(
            returncode=returned, stdout=stdout.getvalue(), stderr=stderr.getvalue()
        )

    def commands(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text("utf-8").splitlines()]

    def assert_local_rejection(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.commands(), [])
        self.assertNotIn("API key (input hidden)", result.stdout + result.stderr)

    def test_matching_identity_reuses_exact_name_without_config_changes(self):
        self.write_config(
            {
                "caller-target": {
                    "wxo_url": "https://target.example.invalid/instance",
                    "auth_type": "ibm_iam",
                },
                "unrelated": {"wxo_url": "https://other.invalid"},
            }
        )
        original = self.config.read_bytes()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.config.read_bytes(), original)
        self.assertFalse(any(cmd[:2] == ["env", "add"] for cmd in self.commands()))
        self.assertIn(
            ["env", "activate", "caller-target", "--api-key", "synthetic-offline-key"],
            self.commands(),
        )
        self.assertEqual(
            sum(cmd[:2] == ["toolkits", "import"] for cmd in self.commands()), 1
        )

    def test_prefix_collision_creates_only_exact_requested_name(self):
        foreign = {"wxo_url": "https://foreign.invalid", "auth_type": "mcsp"}
        self.write_config({"caller-target-extra": foreign})
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            [
                "env",
                "add",
                "--name",
                "caller-target",
                "--url",
                "https://target.example.invalid/instance",
                "--type",
                "ibm_iam",
            ],
            self.commands(),
        )
        configured = yaml.safe_load(self.config.read_text("utf-8"))["environments"]
        self.assertEqual(configured["caller-target-extra"], foreign)

    def test_changed_url_or_auth_type_rejects_before_authentication(self):
        for changes in (
            {"wxo_url": "https://previous.invalid"},
            {"auth_type": "mcsp"},
            {"wxo_url": "https://target.example.invalid/instance/"},
        ):
            with self.subTest(changes=changes):
                details = {
                    "wxo_url": "https://target.example.invalid/instance",
                    "auth_type": "ibm_iam",
                    **changes,
                }
                self.write_config({"caller-target": details})
                original = self.config.read_bytes()
                result = self.run_script(overrides={"WXO_API_KEY": ""})
                self.assert_local_rejection(result)
                self.assertEqual(self.config.read_bytes(), original)

    def test_caller_auth_type_preserves_supported_explicit_type(self):
        self.write_config({})
        result = self.run_script(
            overrides={"WXO_ENV_TYPE": "mcsp", "ADK_FIXTURE_NOISY_CONFIG": "yes"}
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        add = next(cmd for cmd in self.commands() if cmd[:2] == ["env", "add"])
        self.assertEqual(add[-2:], ["--type", "mcsp"])

    def test_adk_interpreter_can_be_selected_independently_from_staging(self):
        self.write_config(
            {
                "caller-target": {
                    "wxo_url": "https://target.example.invalid/instance",
                    "auth_type": "ibm_iam",
                }
            }
        )
        selected = self.root / "bin/adk-python"
        selected.write_text(
            '#!/usr/bin/env bash\nprintf "selected\\n" >> "$ADK_PYTHON_LOG"\n'
            'exec "$PYTHON" "$@"\n',
            encoding="utf-8",
            newline="\n",
        )
        selected.chmod(0o755)
        log = self.root / "adk-python.log"
        result = self.run_script(
            overrides={
                "ADK_PYTHON": str(selected).replace("\\", "/"),
                "ADK_PYTHON_LOG": str(log).replace("\\", "/"),
            }
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(log.read_text("utf-8"), "selected\n")

    def test_malformed_or_unavailable_identity_rejects_locally(self):
        contents = (
            "environments: [broken",
            "- environments\n",
            "environments: []\n",
            "environments:\n  caller-target: null\n",
            "environments:\n  caller-target:\n    wxo_url: https://target.invalid\n",
            "environments:\n  caller-target:\n    wxo_url: 123\n"
            "    auth_type: ibm_iam\n",
        )
        for content in contents:
            with self.subTest(content=content):
                self.config.write_text(content, encoding="utf-8")
                self.assert_local_rejection(self.run_helper())
        self.config.unlink()
        self.config.mkdir()
        self.assert_local_rejection(self.run_helper())

    def test_malformed_identity_stops_registration_before_cli_access(self):
        self.config.write_text("environments: [broken", encoding="utf-8")
        self.assert_local_rejection(self.run_script())

    def test_missing_sdk_or_invalid_caller_type_rejects_locally(self):
        self.write_config({})
        self.assert_local_rejection(self.run_helper(auth_type="unsupported-type"))
        self.assert_local_rejection(self.run_helper(unavailable_sdk=True))

    def test_missing_config_and_sdk_default_mappings_are_absent(self):
        result = self.run_helper()
        self.assertEqual((result.returncode, result.stdout), (3, ""))
        self.assertFalse(self.config.exists())
        for content in ("", "null\n", "{}\n", "cached_user_env: {}\n"):
            with self.subTest(content=content):
                self.config.write_text(content, encoding="utf-8")
                result = self.run_helper()
                self.assertEqual((result.returncode, result.stdout), (3, ""))
                self.assertEqual(self.config.read_text("utf-8"), content)

    def test_sdk_yaml_merges_and_inferred_ibm_type_preserve_config(self):
        url = "https://api.us-south.watson-orchestrate.cloud.ibm.com/instances/test"
        for type_field in ("", "    auth_type: null\n", "    auth_type: ibm_iam\n"):
            with self.subTest(type_field=type_field):
                content = (
                    f"defaults: &defaults\n  wxo_url: {url}\n"
                    "environments:\n  caller-target:\n    <<: *defaults\n" + type_field
                )
                self.config.write_text(content, encoding="utf-8")
                result = self.run_helper(url=url)
                self.assertEqual((result.returncode, result.stdout), (0, ""))
                self.assertEqual(self.config.read_text("utf-8"), content)
                self.assert_local_rejection(self.run_helper(url=url, auth_type="mcsp"))

    def test_config_errors_never_echo_unrelated_cached_values(self):
        sentinel = "SYNTHETIC_UNRELATED_CONFIG_SENTINEL"
        self.config.write_text(
            f"environments: {{}}\ncached_user_env:\n  secret: [{sentinel}\n",
            encoding="utf-8",
        )
        result = self.run_helper()
        self.assert_local_rejection(result)
        self.assertNotIn(sentinel, result.stdout + result.stderr)
        self.assertNotIn("cached_user_env", result.stdout + result.stderr)
        self.assertIn("ParserError", result.stderr)

    def test_prepare_only_avoids_sdk_config_and_adk_access(self):
        self.config.mkdir()
        (self.modules / "ibm_watsonx_orchestrate/cli/config.py").write_text(
            "raise AssertionError('preparation must not import IBM SDK')\n",
            encoding="utf-8",
        )
        result = self.run_script(
            overrides={"WXO_ENV_TYPE": "unsupported-type", "WXO_API_KEY": ""},
            arguments=("--prepare-only",),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.commands(), [])
        self.assertTrue((self.kit / "_toolkit.generated.yaml").is_file())


if __name__ == "__main__":
    unittest.main()
