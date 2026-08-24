"""The only Docker and Git subprocess seams used by the QA025 cell."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from contract import (
    BlockedPrerequisite,
    GuardDenied,
    environment_key_hash,
    redact_text,
    sha256_bytes,
    sha256_file,
    validate_local_directory,
    validate_owned_file,
)

WINDOWS_DOCKER = Path(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe")
WINDOWS_GIT = Path(r"C:\Program Files\Git\cmd\git.exe")
LINUX_DOCKER_CANDIDATES = (Path("/usr/bin/docker"), Path("/usr/local/bin/docker"))
LINUX_GIT_CANDIDATES = (Path("/usr/bin/git"), Path("/usr/local/bin/git"))

WINDOWS_CONTEXT_PAIRS = (
    ("desktop-linux", "npipe:////./pipe/dockerDesktopLinuxEngine"),
    ("default", "npipe:////./pipe/docker_engine"),
)
LINUX_CONTEXT_PAIR = ("default", "unix:///var/run/docker.sock")
CONTEXT_LIST_ARGS = ("context", "ls", "--format", "{{json .}}")
INFO_ARGS = ("info", "--format", "{{json .}}")
DOCKER_COMMANDS = frozenset(
    {
        "compose",
        "create",
        "image",
        "info",
        "inspect",
        "network",
        "pull",
        "rm",
        "start",
        "stop",
        "volume",
    }
)
DOCKER_TARGET_OPTIONS = (
    "--config",
    "--context",
    "--host",
    "--tls",
    "--tlscacert",
    "--tlscert",
    "--tlskey",
    "--tlsverify",
    "-H",
)
COMPOSE_TARGET_OPTIONS = (
    "--env-file",
    "--file",
    "--profile",
    "--project-directory",
    "--project-name",
    "-f",
    "-p",
)
COMPOSE_COMMANDS = frozenset({"build", "config", "create", "ps", "version"})


@dataclass(frozen=True)
class DockerTarget:
    context_name: str
    endpoint: str
    endpoint_kind: str
    endpoint_sha256: str
    daemon_id: str
    daemon_name: str
    server_version: str
    os_type: str
    daemon_identity_sha256: str

    def receipt(self) -> dict[str, str]:
        return {
            "context_name": self.context_name,
            "endpoint_kind": self.endpoint_kind,
            "endpoint_sha256": self.endpoint_sha256,
            "daemon_id_sha256": sha256_bytes(self.daemon_id.encode("utf-8")),
            "daemon_name_sha256": sha256_bytes(self.daemon_name.encode("utf-8")),
            "server_version": self.server_version,
            "os_type": self.os_type,
            "daemon_identity_sha256": self.daemon_identity_sha256,
        }


@dataclass
class CommandReceipt:
    executable_sha256: str
    env_keys_sha256: str
    docker_call_count: int = 0
    compose_call_count: int = 0
    calls: list[dict[str, Any]] = field(default_factory=list)


def _trusted_executable(kind: str) -> Path:
    candidates: tuple[Path, ...]
    if os.name == "nt":
        candidates = (WINDOWS_DOCKER,) if kind == "docker" else (WINDOWS_GIT,)
    else:
        candidates = (
            LINUX_DOCKER_CANDIDATES if kind == "docker" else LINUX_GIT_CANDIDATES
        )
    for candidate in candidates:
        if candidate.is_file() and not candidate.is_symlink():
            resolved = candidate.resolve(strict=True)
            if str(resolved).startswith(("\\\\", "//")):
                continue
            return resolved
    raise BlockedPrerequisite(f"trusted absolute {kind} executable was not found")


def _validated_windows_system_path(raw: str | None, expected_leaf: str) -> Path:
    if not raw:
        raise GuardDenied(f"{expected_leaf} parent path is missing")
    path = Path(raw)
    resolved = validate_local_directory(path, label=expected_leaf)
    if resolved.name.casefold() != expected_leaf.casefold():
        raise GuardDenied(f"{expected_leaf} parent path has an unexpected leaf")
    return resolved


def _validated_home(raw: str | None, *, label: str) -> Path | None:
    if not raw:
        return None
    return validate_local_directory(Path(raw), label=label)


def _current_account_home() -> Path:
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Volatile Environment"
            ) as key:
                raw, _ = winreg.QueryValueEx(key, "USERPROFILE")
        except (OSError, TypeError) as error:
            raise GuardDenied(
                "current Windows account profile could not be attested"
            ) from error
    else:
        try:
            import pwd

            raw = pwd.getpwuid(os.getuid()).pw_dir
        except (KeyError, OSError) as error:
            raise GuardDenied("current account home could not be attested") from error
    return validate_local_directory(Path(str(raw)), label="current account home")


def _windows_environment_value(environment: Mapping[str, str], name: str) -> str | None:
    """Read one Windows environment entry without trusting caller key casing."""

    matches = {
        str(value)
        for key, value in environment.items()
        if str(key).casefold() == name.casefold()
    }
    if len(matches) > 1:
        raise GuardDenied(f"conflicting Windows environment entries for {name}")
    return next(iter(matches), None)


class CommandEnvelope:
    """Own executable resolution, cwd, child env, context and Compose argv."""

    def __init__(
        self,
        repo_root: Path,
        qa_directory: Path,
        parent_env: Mapping[str, str],
        command_temp: Path,
    ) -> None:
        self.repo_root = repo_root.resolve(strict=True)
        self.qa_directory = qa_directory.resolve(strict=True)
        self._parent_env = parent_env
        self.command_temp = command_temp.resolve(strict=True)
        self.docker_executable = _trusted_executable("docker")
        self.git_executable = _trusted_executable("git")
        self._context: DockerTarget | None = None
        self._pending_context_name: str | None = None
        docker_hash = sha256_file(self.docker_executable)
        self.receipt = CommandReceipt(
            executable_sha256=docker_hash,
            env_keys_sha256=environment_key_hash(self._child_environment()),
        )

    @property
    def git_executable_sha256(self) -> str:
        return sha256_file(self.git_executable)

    def _child_environment(self) -> dict[str, str]:
        environment: dict[str, str] = {
            "COMPOSE_DISABLE_ENV_FILE": "1",
            "COMPOSE_ANSI": "never",
        }
        if os.name == "nt":
            windows_root = _validated_windows_system_path(
                _windows_environment_value(self._parent_env, "SystemRoot")
                or _windows_environment_value(self._parent_env, "WINDIR"),
                "Windows",
            )
            comspec = Path(
                _windows_environment_value(self._parent_env, "ComSpec") or ""
            )
            expected_comspec = windows_root / "System32" / "cmd.exe"
            if not comspec.is_absolute() or comspec.resolve(
                strict=True
            ) != expected_comspec.resolve(strict=True):
                raise GuardDenied("ComSpec must be the local System32 cmd.exe")
            docker_dir = self.docker_executable.parent
            git_dir = self.git_executable.parent
            system32 = windows_root / "System32"
            program_files = validate_local_directory(
                self.docker_executable.parents[4], label="trusted Program Files"
            )
            if program_files.name.casefold() != "program files":
                raise GuardDenied("trusted Docker executable is outside Program Files")
            environment.update(
                {
                    "SystemRoot": str(windows_root),
                    "WINDIR": str(windows_root),
                    "ComSpec": str(expected_comspec),
                    # Docker CLI discovers its bundled Compose plugin below this
                    # runner-derived trusted root; no parent ProgramFiles value is read.
                    "ProgramFiles": str(program_files),
                    "PATHEXT": ".COM;.EXE",
                    "PATH": os.pathsep.join(
                        (str(docker_dir), str(git_dir), str(system32))
                    ),
                }
            )
            user_profile = _validated_home(
                _windows_environment_value(self._parent_env, "USERPROFILE"),
                label="USERPROFILE",
            )
            if user_profile is None or user_profile != _current_account_home():
                raise GuardDenied("USERPROFILE does not belong to the current account")
            environment["USERPROFILE"] = str(user_profile)
            environment["HOME"] = str(user_profile)
        else:
            environment["PATH"] = "/usr/local/bin:/usr/bin:/bin"
            home = _validated_home(self._parent_env.get("HOME"), label="HOME")
            if home is None or home != _current_account_home():
                raise GuardDenied("HOME does not belong to the current account")
            environment["HOME"] = str(home)
            runtime = _validated_home(
                self._parent_env.get("XDG_RUNTIME_DIR"), label="XDG_RUNTIME_DIR"
            )
            if runtime is not None:
                if runtime.stat().st_uid != os.getuid():
                    raise GuardDenied(
                        "XDG_RUNTIME_DIR does not belong to the current account"
                    )
                environment["XDG_RUNTIME_DIR"] = str(runtime)
        environment["TEMP"] = str(self.command_temp)
        environment["TMP"] = str(self.command_temp)
        if os.name != "nt":
            environment["TMPDIR"] = str(self.command_temp)
        locale = self._parent_env.get("LC_ALL") or self._parent_env.get("LANG")
        if locale and all(32 <= ord(character) < 127 for character in locale):
            environment["LANG"] = locale
            environment["LC_ALL"] = locale
        return environment

    @staticmethod
    def _assert_argv(args: Sequence[str]) -> list[str]:
        if not isinstance(args, Sequence) or isinstance(args, (str, bytes)):
            raise GuardDenied("command arguments must be an argv sequence")
        normalized = [str(argument) for argument in args]
        if any("\x00" in argument for argument in normalized):
            raise GuardDenied("command argument contains NUL")
        return normalized

    @staticmethod
    def _contains_option(args: Sequence[str], options: Sequence[str]) -> bool:
        for argument in args:
            for option in options:
                if argument == option or argument.startswith(option + "="):
                    return True
                if option == "-H" and argument.startswith("-H"):
                    return True
        return False

    @classmethod
    def _assert_docker_argv(cls, args: Sequence[str]) -> None:
        if cls._contains_option(args, DOCKER_TARGET_OPTIONS):
            raise GuardDenied("Docker target override option is forbidden")
        if not args or args[0] not in DOCKER_COMMANDS | {"context"}:
            raise GuardDenied("Docker command is outside the QA025 allowlist")
        if args[0] == "context" and tuple(args) != CONTEXT_LIST_ARGS:
            raise GuardDenied("Docker context mutation is forbidden")
        allowed_subcommands = {
            "image": {"inspect", "rm"},
            "network": {"create", "inspect", "rm"},
            "volume": {"inspect", "rm"},
        }
        if args[0] in allowed_subcommands and (
            len(args) < 2 or args[1] not in allowed_subcommands[args[0]]
        ):
            raise GuardDenied("Docker subcommand is outside the QA025 allowlist")

    @classmethod
    def _assert_compose_argv(cls, args: Sequence[str]) -> None:
        if cls._contains_option(args, COMPOSE_TARGET_OPTIONS):
            raise GuardDenied("Compose target override option is forbidden")
        if not args or args[0] not in COMPOSE_COMMANDS:
            raise GuardDenied("Compose command is outside the QA025 allowlist")

    def _run(
        self,
        executable: Path,
        args: Sequence[str],
        *,
        timeout: float,
        input_bytes: bytes | None = None,
        replacements: Mapping[str, str] | None = None,
        kind: str,
    ) -> subprocess.CompletedProcess[bytes]:
        normalized = self._assert_argv(args)
        environment = self._child_environment()
        started_argv = [str(executable), *normalized]
        try:
            result = subprocess.run(
                started_argv,
                cwd=self.repo_root,
                env=environment,
                input=input_bytes,
                capture_output=True,
                shell=False,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            if isinstance(error, subprocess.TimeoutExpired):
                raise
            raise BlockedPrerequisite(
                f"{kind} executable could not be started"
            ) from error
        redacted_argv = [
            redact_text(argument, replacements=replacements)
            for argument in started_argv
        ]
        self.receipt.calls.append(
            {
                "kind": kind,
                "argv": redacted_argv,
                "exit_code": result.returncode,
                "env_keys_sha256": environment_key_hash(environment),
                "shell": False,
            }
        )
        return result

    def run_git(
        self, args: Sequence[str], *, timeout: float = 30
    ) -> subprocess.CompletedProcess[bytes]:
        """Run one read-only Git command, always anchored to the expected worktree."""

        allowed = {
            "rev-parse",
            "status",
            "diff",
            "ls-files",
            "check-ignore",
            "show",
            "log",
        }
        normalized = self._assert_argv(args)
        if not normalized or normalized[0] not in allowed:
            raise GuardDenied("run_git accepts read-only Git commands only")
        return self._run(
            self.git_executable,
            ["-C", str(self.repo_root), *normalized],
            timeout=timeout,
            replacements={str(self.repo_root): "<worktree>"},
            kind="git",
        )

    def run_docker(
        self,
        args: Sequence[str],
        *,
        timeout: float = 120,
        input_bytes: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        """Run one Docker command with a fresh sanitized environment."""

        normalized = self._assert_argv(args)
        self._assert_docker_argv(normalized)
        if tuple(normalized) == CONTEXT_LIST_ARGS:
            # Context discovery is metadata-only.  It must not inherit a
            # previously-attested context, otherwise a changed current daemon
            # could influence the evidence used to decide whether cleanup may
            # mutate anything.
            pass
        elif self._pending_context_name is not None and tuple(normalized) == INFO_ARGS:
            normalized = ["--context", self._pending_context_name, *normalized]
        elif self._context is not None:
            normalized = ["--context", self._context.context_name, *normalized]
        else:
            raise GuardDenied("Docker context has not been attested")
        self.receipt.docker_call_count += 1
        return self._run(
            self.docker_executable,
            normalized,
            timeout=timeout,
            input_bytes=input_bytes,
            replacements={
                str(self.repo_root): "<worktree>",
                str(self.qa_directory): "<qa-directory>",
            },
            kind="docker",
        )

    def run_compose(
        self,
        args: Sequence[str],
        *,
        project_name: str,
        base_file: Path,
        override_file: Path,
        run_temp: Path,
        timeout: float = 120,
        input_bytes: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        """Run one Compose call with exact owned files and project arguments."""

        base = validate_owned_file(
            base_file, roots=(self.qa_directory,), label="base Compose file"
        )
        override = validate_owned_file(
            override_file,
            roots=(run_temp,),
            label="generated Compose override",
        )
        normalized = self._assert_argv(args)
        self._assert_compose_argv(normalized)
        self.receipt.compose_call_count += 1
        return self.run_docker(
            [
                "compose",
                "--project-directory",
                str(self.qa_directory),
                "-f",
                str(base),
                "-f",
                str(override),
                "--project-name",
                project_name,
                *normalized,
            ],
            timeout=timeout,
            input_bytes=input_bytes,
        )

    def _attest_context_candidate(self) -> DockerTarget:
        """Read one local context/daemon pair without changing the trusted target."""

        self._pending_context_name = None
        result = self.run_docker(list(CONTEXT_LIST_ARGS), timeout=30)
        if result.returncode != 0:
            raise BlockedPrerequisite("Docker context discovery failed")
        discovered: dict[str, str] = {}
        for raw_line in result.stdout.decode("utf-8", errors="replace").splitlines():
            try:
                item = json.loads(raw_line)
            except json.JSONDecodeError as error:
                raise GuardDenied("Docker context metadata was not JSON") from error
            if not isinstance(item, dict):
                raise GuardDenied("Docker context metadata entry was not an object")
            name = item.get("Name")
            endpoint = item.get("DockerEndpoint")
            if isinstance(name, str) and isinstance(endpoint, str):
                discovered[name] = endpoint

        expected_pairs = (
            WINDOWS_CONTEXT_PAIRS if os.name == "nt" else (LINUX_CONTEXT_PAIR,)
        )
        valid = [
            (name, endpoint)
            for name, endpoint in expected_pairs
            if discovered.get(name) == endpoint
        ]
        if not valid:
            raise GuardDenied(
                "no allowlisted local Docker context/endpoint pair was found"
            )
        selected_name = (
            "desktop-linux"
            if os.name == "nt" and any(name == "desktop-linux" for name, _ in valid)
            else valid[0][0]
        )
        selected_endpoint = next(
            endpoint for name, endpoint in valid if name == selected_name
        )
        endpoint_kind = "npipe" if selected_endpoint.startswith("npipe:") else "unix"

        self._pending_context_name = selected_name
        try:
            info = self.run_docker(list(INFO_ARGS), timeout=30)
        finally:
            # A failed candidate attestation must not affect later commands.
            self._pending_context_name = None
        if info.returncode != 0:
            raise BlockedPrerequisite("allowlisted local Docker daemon is unavailable")
        try:
            payload = json.loads(info.stdout.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise GuardDenied("Docker daemon info was not JSON") from error
        server = payload.get("ServerVersion")
        daemon_id = payload.get("ID")
        daemon_name = payload.get("Name")
        os_type = payload.get("OSType")
        if not all(
            isinstance(value, str) and value
            for value in (server, daemon_id, daemon_name)
        ):
            raise GuardDenied("Docker daemon identity fields are incomplete")
        if os_type != "linux":
            raise GuardDenied("Docker daemon must be a Linux engine")
        identity_object = {
            "context_name": selected_name,
            "endpoint": selected_endpoint,
            "daemon_id": daemon_id,
            "daemon_name": daemon_name,
            "server_version": server,
            "os_type": os_type,
        }
        identity_hash = sha256_bytes(
            json.dumps(identity_object, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        target = DockerTarget(
            context_name=selected_name,
            endpoint=selected_endpoint,
            endpoint_kind=endpoint_kind,
            endpoint_sha256=sha256_bytes(selected_endpoint.encode("utf-8")),
            daemon_id=daemon_id,
            daemon_name=daemon_name,
            server_version=server,
            os_type=os_type,
            daemon_identity_sha256=identity_hash,
        )
        return target

    def discover_and_attest_context(self) -> DockerTarget:
        """Attest the initial local target and make it usable for run commands."""

        target = self._attest_context_candidate()
        self._context = target
        return target

    def reattest_context(self, expected: DockerTarget) -> DockerTarget:
        # Do not assign the candidate to ``_context`` until equality succeeds:
        # any mismatch must leave cleanup with no mutating Docker path.
        current = self._attest_context_candidate()
        if current != expected:
            from contract import CleanupGuardDenied

            raise CleanupGuardDenied(
                "Docker context or daemon identity changed during the run"
            )
        self._context = expected
        return current

    def verify_git_worktree(
        self, *, allowed_untracked_prefixes: Sequence[str] = ()
    ) -> tuple[str, bool]:
        top = self.run_git(["rev-parse", "--show-toplevel"])
        if top.returncode != 0:
            raise GuardDenied("expected worktree is not a Git worktree")
        actual_root = Path(top.stdout.decode("utf-8").strip()).resolve(strict=True)
        if actual_root != self.repo_root:
            raise GuardDenied("Git worktree root does not match the runner root")
        git_dir = self.run_git(["rev-parse", "--absolute-git-dir"])
        common_dir = self.run_git(["rev-parse", "--git-common-dir"])
        if git_dir.returncode != 0 or common_dir.returncode != 0:
            raise GuardDenied("Git metadata indirection could not be attested")
        resolved_git_dir = Path(git_dir.stdout.decode("utf-8").strip()).resolve(
            strict=True
        )
        raw_common = Path(common_dir.stdout.decode("utf-8").strip())
        if not raw_common.is_absolute():
            raw_common = self.repo_root / raw_common
        resolved_common = validate_local_directory(
            raw_common, label="Git common directory"
        )
        if resolved_git_dir == self.repo_root or resolved_common == self.repo_root:
            raise GuardDenied("Git metadata resolves to the worktree root")
        marker = self.repo_root / ".git"
        if not marker.is_file() or marker.is_symlink():
            raise GuardDenied("candidate must be an isolated linked Git worktree")
        try:
            marker_line = marker.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise GuardDenied("linked-worktree Git marker could not be read") from error
        prefix = "gitdir: "
        if not marker_line.casefold().startswith(prefix):
            raise GuardDenied("linked-worktree Git marker is invalid")
        marker_target = Path(marker_line[len(prefix) :])
        if not marker_target.is_absolute():
            marker_target = self.repo_root / marker_target
        try:
            resolved_marker_target = marker_target.resolve(strict=True)
        except OSError as error:
            raise GuardDenied("linked-worktree Git marker target is invalid") from error
        if resolved_marker_target != resolved_git_dir:
            raise GuardDenied("Git marker and Git-reported metadata disagree")
        if (
            resolved_common.name.casefold() != ".git"
            or resolved_git_dir.parent != resolved_common / "worktrees"
        ):
            raise GuardDenied("Git metadata is not the expected shared-worktree layout")
        alternates = resolved_common / "objects" / "info" / "alternates"
        if alternates.exists():
            raise GuardDenied("Git alternate object storage is forbidden")
        sha = self.run_git(["rev-parse", "HEAD"])
        status = self.run_git(["status", "--porcelain=v1", "--untracked-files=all"])
        if sha.returncode != 0 or status.returncode != 0:
            raise GuardDenied("Git candidate identity could not be read")
        candidate = sha.stdout.decode("ascii").strip()
        from contract import assert_sha40

        assert_sha40(candidate)
        dirty_lines = [
            line
            for line in status.stdout.decode("utf-8", errors="replace").splitlines()
            if line[3:].replace("\\", "/").strip()
            and not any(
                line[3:].replace("\\", "/").strip().startswith(prefix)
                for prefix in allowed_untracked_prefixes
            )
        ]
        clean = not dirty_lines
        return candidate, clean
