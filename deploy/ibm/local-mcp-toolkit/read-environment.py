"""Resolve environment identity through ADK config without reading auth stores."""

from __future__ import annotations

import os
import sys


class IdentityError(ValueError):
    """Authored identity diagnostics contain no stored configuration values."""


def main() -> int:
    try:
        import yaml
        from ibm_watsonx_orchestrate.cli.commands.environment.types import (
            EnvironmentAuthType,
        )
        from ibm_watsonx_orchestrate.cli.config import (
            ENV_AUTH_TYPE,
            ENV_WXO_URL_OPT,
            ENVIRONMENTS_SECTION_HEADER,
            PROTECTED_ENV_NAME,
            Config,
        )
    except (ImportError, AttributeError) as error:
        print(
            "FATAL: ADK environment identity unavailable. Set ADK_PYTHON to "
            "Python from orchestrate's environment; compatible ADK config "
            f"exports required (verified with ADK 2.19.1): {error}",
            file=sys.stderr,
        )
        return 1

    name = os.environ["WXO_ENV_NAME"]
    url = os.environ["WXO_INSTANCE_URL"]
    auth_type = os.environ["WXO_ENV_TYPE"]
    try:
        EnvironmentAuthType(auth_type)
    except ValueError:
        print(
            f"FATAL: WXO_ENV_TYPE {auth_type!r} unsupported by selected ADK.",
            file=sys.stderr,
        )
        return 1
    if name == PROTECTED_ENV_NAME:
        print(
            f"FATAL: {name!r} is reserved by ADK; choose another WXO_ENV_NAME.",
            file=sys.stderr,
        )
        return 1

    try:
        # Default Config initializes normal SDK config defaults. AUTH config is
        # separate and never constructed here. Preserve native loader semantics.
        environments = Config().get(ENVIRONMENTS_SECTION_HEADER)
        if not isinstance(environments, dict):
            raise IdentityError("environments must contain mapping")
        if name not in environments:
            return 3
        environment = environments[name]
        if not isinstance(environment, dict):
            raise IdentityError("selected environment must contain mapping")
        stored_url = environment.get(ENV_WXO_URL_OPT)
        stored_type = environment.get(ENV_AUTH_TYPE)
        if not isinstance(stored_url, str) or not stored_url:
            raise IdentityError("selected environment has no explicit URL")
        if stored_type is None:
            # ADK can omit --type. IBM Cloud inference needs only supplied URL;
            # other inference can depend on keys or active Config state.
            from ibm_watsonx_orchestrate.client.utils import is_ibm_cloud_platform

            if is_ibm_cloud_platform(stored_url):
                stored_type = EnvironmentAuthType.IBM_CLOUD_IAM.value
        if not isinstance(stored_type, str) or not stored_type:
            raise IdentityError(
                "selected environment has unresolved auth type. Resolve explicit "
                "auth type through ADK or choose another WXO_ENV_NAME"
            )
        if stored_url != url or stored_type != auth_type:
            print(
                f"FATAL: ADK environment {name!r} conflicts with supplied "
                "WXO_INSTANCE_URL/WXO_ENV_TYPE. Choose another WXO_ENV_NAME "
                "or resolve existing configuration through ADK before retrying.",
                file=sys.stderr,
            )
            return 1
    except IdentityError as error:
        print(f"FATAL: Invalid ADK environment identity: {error}.", file=sys.stderr)
        return 1
    except (
        yaml.YAMLError,
        ValueError,
        TypeError,
        ImportError,
        OSError,
        UnicodeError,
        AttributeError,
        KeyError,
    ) as error:
        # Parser messages can include unrelated cached configuration values.
        print(
            f"FATAL: Invalid ADK environment identity ({type(error).__name__}).",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
