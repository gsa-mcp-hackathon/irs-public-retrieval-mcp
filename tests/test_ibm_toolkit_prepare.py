"""Offline IBM toolkit preparation and registration compatibility checks."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

import yaml

KIT = Path(__file__).resolve().parents[1] / "deploy/ibm/local-mcp-toolkit"


class ToolkitPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        git_bash = Path(os.environ.get("ProgramFiles", "")) / "Git/bin/bash.exe"
        cls.bash = str(git_bash) if git_bash.is_file() else shutil.which("bash")
        if not cls.bash:
            raise unittest.SkipTest("Bash unavailable")

    def setUp(self):
        # Synthetic fixtures inherit caller-selected temporary-root permissions.
        self.root = Path(tempfile.gettempdir()) / f"ibm-toolkit-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)

    def fixture(self, label, package="example_server"):
        root = self.root / label
        kit = root / "deploy/ibm/local-mcp-toolkit"
        kit.mkdir(parents=True)
        for name in (
            "register-toolkit.sh",
            "read-environment.py",
            "toolkit.yaml",
            "server.py",
            "requirements.txt",
        ):
            shutil.copy2(KIT / name, kit / name)
        source = root / "src" / package
        source.mkdir(parents=True)
        (source / "__init__.py").write_text("", encoding="utf-8")
        (source / "app.py").write_text("mcp = object()\n", encoding="utf-8")
        (source / "__pycache__").mkdir()
        (source / "__pycache__/old.pyc").write_bytes(b"discarded cache")
        (root / "unrelated.txt").write_text("excluded", encoding="utf-8")
        (kit / "server.py").write_text(
            (kit / "server.py")
            .read_text(encoding="utf-8")
            .replace("example_server", package),
            encoding="utf-8",
        )
        commands = root / "bin"
        commands.mkdir()
        orchestrate = commands / "orchestrate"
        orchestrate.write_text(
            "#!/usr/bin/env bash\nset -eu\n"
            'printf "%s\\t" "$@" >> "$ADK_LOG"\n'
            'printf "\\n" >> "$ADK_LOG"\n'
            'if [[ "${ALLOW_ADK:-}" != yes ]]; then exit 97; fi\n'
            'if [[ "$1 $2" == "toolkits import" ]]; then\n'
            '  cp "$4" "$IMPORT_CAPTURE"\n'
            "fi\n",
            encoding="utf-8",
            newline="\n",
        )
        orchestrate.chmod(0o755)
        modules = root / "modules/ibm_watsonx_orchestrate/cli"
        modules.mkdir(parents=True)
        (modules / "config.py").write_text(
            "import os\nfrom pathlib import Path\n"
            "path = Path(os.environ['ADK_FIXTURE_CONFIG'])\n"
            "DEFAULT_CONFIG_FILE_FOLDER = str(path.parent)\n"
            "DEFAULT_CONFIG_FILE = path.name\n"
            "ENVIRONMENTS_SECTION_HEADER = 'environments'\n"
            "ENV_WXO_URL_OPT = 'wxo_url'\nENV_AUTH_TYPE = 'auth_type'\n"
            "PROTECTED_ENV_NAME = 'local'\n"
            "import yaml\n"
            "class Config:\n"
            "    def __init__(self):\n"
            "        self.data = yaml.safe_load(path.read_text('utf-8'))\n"
            "    def get(self, section):\n"
            "        return self.data[section]\n",
            encoding="utf-8",
        )
        environment_types = modules / "commands/environment"
        environment_types.mkdir(parents=True)
        (environment_types / "types.py").write_text(
            "from enum import Enum\nclass EnvironmentAuthType(str, Enum):\n"
            "    IBM_CLOUD_IAM = 'ibm_iam'\n",
            encoding="utf-8",
        )
        (root / "adk-config.yaml").write_text(
            yaml.safe_dump(
                {
                    "environments": {
                        "offline-test-env": {
                            "wxo_url": "https://example.invalid",
                            "auth_type": "ibm_iam",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        return root, kit

    def run_script(self, root, kit, config, *arguments):
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("WXO_", "TOOLKIT_"))
            and key
            not in ("PACKAGE_NAME", "PYTHON", "PYTHONPATH", "ADK_PYTHON", "ALLOW_ADK")
        }
        environment.update(
            PATH=str(root / "bin") + os.pathsep + environment["PATH"],
            PYTHON=sys.executable.replace("\\", "/"),
            PYTHONPATH=str(root / "modules"),
            ADK_FIXTURE_CONFIG=str(root / "adk-config.yaml").replace("\\", "/"),
            ADK_LOG=str(root / "adk.log").replace("\\", "/"),
            IMPORT_CAPTURE=str(root / "imported.yaml").replace("\\", "/"),
        )
        environment.update(config)
        # Fixture checks registration effects; process-startup timing varies by host.
        returned = subprocess.run(
            [self.bash, str(kit / "register-toolkit.sh"), *arguments],
            cwd=root,
            env=environment,
            input="",
            capture_output=True,
            text=True,
        )
        self.assertEqual(returned.returncode, 0, returned.stdout + returned.stderr)
        return returned

    def test_prepare_preserves_metadata_and_layout_without_authentication(self):
        cases = (
            (
                "irs_public_lookup",
                '/lookup: "quoted" # text \\ paths\nget_irm_passage',
                "example_server",
            ),
            (
                "team_beta_2026",
                "Find IRS products, instructions, and publications; "
                "r\u00e9sum\u00e9 \U0001f50e\u0085\u2028",
                "caller_server",
            ),
            ("empty_description", "", "example_server"),
            ("path_description", "/usr/share", "example_server"),
        )
        template = yaml.safe_load((KIT / "toolkit.yaml").read_text("utf-8"))
        for index, (name, description, package) in enumerate(cases):
            with self.subTest(name=name, package=package):
                root, kit = self.fixture(str(index), package)
                self.run_script(
                    root,
                    kit,
                    {
                        "TOOLKIT_NAME": name,
                        "TOOLKIT_DESCRIPTION": description,
                        "PACKAGE_NAME": package,
                    },
                    "--prepare-only",
                )
                self.assertFalse((root / "adk.log").exists())
                spec = yaml.safe_load(
                    (kit / "_toolkit.generated.yaml").read_text("utf-8")
                )
                self.assertEqual(spec["name"], name)
                self.assertEqual(spec["description"], description)
                for key in template.keys() - {"name", "description", "package_root"}:
                    self.assertEqual(spec[key], template[key])
                stage = Path(spec["package_root"])
                self.assertEqual(stage.resolve(), (kit / "_stage").resolve())
                self.assertEqual(
                    {path.name for path in stage.iterdir()},
                    {package, "server.py", "requirements.txt"},
                )
                self.assertEqual(
                    (stage / package / "app.py").read_bytes(),
                    (root / "src" / package / "app.py").read_bytes(),
                )
                self.assertFalse(list(stage.rglob("__pycache__")))
                self.assertEqual(
                    (stage / "requirements.txt").read_bytes(),
                    (kit / "requirements.txt").read_bytes(),
                )
                self.assertEqual(
                    (stage / "server.py").read_bytes(),
                    (kit / "server.py").read_bytes(),
                )

    def test_default_registration_imports_template_metadata_and_cleans_outputs(self):
        root, kit = self.fixture("registration")
        template = yaml.safe_load((kit / "toolkit.yaml").read_text("utf-8"))
        template["description"] = "Caller template description remains configurable."
        (kit / "toolkit.yaml").write_text(yaml.safe_dump(template), encoding="utf-8")
        self.run_script(
            root,
            kit,
            {
                "TOOLKIT_NAME": template["name"],
                "WXO_ENV_NAME": "offline-test-env",
                "WXO_INSTANCE_URL": "https://example.invalid",
                "WXO_API_KEY": "offline-test-placeholder",
                "ALLOW_ADK": "yes",
            },
        )
        imported = yaml.safe_load((root / "imported.yaml").read_text("utf-8"))
        self.assertEqual(imported["name"], template["name"])
        self.assertEqual(imported["description"], template["description"])
        commands = [
            line.rstrip("\t").split("\t")
            for line in (root / "adk.log").read_text("utf-8").splitlines()
        ]
        self.assertIn(
            [
                "env",
                "activate",
                "offline-test-env",
                "--api-key",
                "offline-test-placeholder",
            ],
            commands,
        )
        self.assertEqual(
            sum(command[:2] == ["toolkits", "import"] for command in commands), 1
        )
        self.assertFalse((kit / "_stage").exists())
        self.assertFalse((kit / "_toolkit.generated.yaml").exists())


if __name__ == "__main__":
    unittest.main()
