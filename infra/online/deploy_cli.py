"""Stable installed CLI. Version and context validation precede every mutation."""

import argparse
import json
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy_acceptance import Acceptance, create_test_key, paths
from deploy_install import installed, operation_lock
from deploy_policy import DeployError
from deploy_protocol import check_protocol
from deploy_runtime import Deployment, validate_args


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise DeployError("INVALID_ARGUMENTS")


def parse(argv):
    parser = SafeParser()
    parser.add_argument(
        "action",
        choices=(
            "version",
            "production",
            "acceptance-prepare",
            "acceptance-update",
            "acceptance-key",
        ),
    )
    parser.add_argument("--protocol", type=int)
    parser.add_argument("--tool-version")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--project")
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--candidate-source", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--test-secret", type=Path)
    parser.add_argument("--target", choices=("web", "app"))
    parser.add_argument("--probe", choices=("container-http",))
    parser.add_argument("--fault", choices=("none", "health", "worker", "rollback"), default="none")
    parser.add_argument("production_args", nargs="*")
    args = parser.parse_intermixed_args(argv)
    if args.action == "production":
        if (
            len(args.production_args) != 6
            or args.fault != "none"
            or any(
                (
                    args.project,
                    args.state_dir,
                    args.evidence_dir,
                    args.candidate_source,
                    args.source,
                    args.test_secret,
                    args.target,
                    args.probe,
                )
            )
        ):
            raise DeployError("INVALID_PRODUCTION_ARGUMENTS")
        validate_args(*args.production_args)
    elif args.action.startswith("acceptance-"):
        if (
            args.production_args
            or not all((args.project, args.state_dir, args.evidence_dir, args.target))
            or args.probe != "container-http"
        ):
            raise DeployError("INVALID_ACCEPTANCE_ARGUMENTS")
        paths(args.project, args.state_dir, args.evidence_dir, args.candidate_source)
        if args.action == "acceptance-key":
            if (
                args.target != "app"
                or args.source
                or args.candidate_source
                or args.test_secret
                or args.fault != "none"
            ):
                raise DeployError("INVALID_ACCEPTANCE_ARGUMENTS")
        elif args.action == "acceptance-prepare":
            if not args.source or args.candidate_source or args.fault != "none":
                raise DeployError("INVALID_ACCEPTANCE_ARGUMENTS")
        elif not args.candidate_source or args.source or args.test_secret:
            raise DeployError("INVALID_ACCEPTANCE_ARGUMENTS")
    return args


def main() -> int:
    try:
        args = parse(sys.argv[1:])
        directory = Path(__file__).resolve().parent
        meta = installed(directory)
        if args.action == "version":
            print(json.dumps(meta))
            return 0
        check_protocol(args.protocol, args.tool_version, directory)
        if os.geteuid() != 0:
            raise DeployError("ROOT_REQUIRED")
        os.umask(0o077)
        if args.action == "acceptance-key":
            print(create_test_key(args.project, args.dry_run))
            return 0

        def interrupted(*_):
            raise DeployError("DEPLOY_INTERRUPTED")

        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        if args.action == "production":
            deployment = Deployment()
            if args.dry_run:
                deployment.stable = deployment.release_target(deployment.current)
                deployment.verify_bundle(*args.production_args[:5])
                print("DRY_RUN_OK")
                return 0
            lock_path = Path("/opt/storylens/shared/lightweight-deploy.lock")
            operation = lambda: deployment.deploy(*args.production_args)
        else:
            acceptance = Acceptance(args.project, args.state_dir, args.evidence_dir, args.target)
            operation = (
                (lambda: acceptance.prepare(args.source, args.test_secret, args.dry_run))
                if args.action == "acceptance-prepare"
                else (lambda: acceptance.update(args.candidate_source, args.fault, args.dry_run))
            )
        if args.dry_run:
            print(operation())  # no lock file writes in dry-run
            return 0
        if args.action != "production":
            with operation_lock(args.project + ".lock"):
                print(operation())
            return 0
        import fcntl

        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            print(operation())
        return 0
    except DeployError as exc:
        print(str(exc))
    except BaseException:  # noqa: BLE001 -- privileged CLI redaction
        print("DEPLOY_FAILED_SAFELY")
    return 1


if __name__ == "__main__":
    sys.exit(main())
