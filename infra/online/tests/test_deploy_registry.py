import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import deploy_install as installer
from deploy_policy import DeployError
from deploy_protocol import TOOL_FILES, tool_version


def version(lib, commit, legacy=False):
    directory = lib / commit
    directory.mkdir(parents=True)
    digest = hashlib.sha256()
    for name in sorted(installer.LEGACY_TOOL_FILES if legacy else TOOL_FILES):
        value = (Path(installer.__file__).parent / name).read_bytes()
        (directory / name).write_bytes(value)
        digest.update(name.encode() + b"\0" + value + b"\0")
    meta = {"commit": commit, "protocol": 2, "tool_version": digest.hexdigest()}
    (directory / "installed.json").write_text(json.dumps(meta))
    return directory


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "trusted", lambda _: None)
    lib, entry = tmp_path / "lib", tmp_path / "bin/tool"
    entry.parent.mkdir()
    old = version(lib, "a" * 40, legacy=True)
    new = version(lib, "b" * 40)
    os.symlink(old / "deploy-lightweight.sh", entry)
    return lib, entry, old, new


def test_two_layouts_and_legacy_lock_list_without_reading_or_changing(library, monkeypatch):
    lib, entry, old, new = library
    lock = lib / "sl-accept-webd20260904.lock"
    lock.write_bytes(b"audit evidence retained")
    lock.chmod(0o600)
    before = lock.stat()
    # Exact old failure: current tool_version requires the two new modules.
    with pytest.raises(FileNotFoundError):
        tool_version(old)
    assert not lock.is_dir()  # old list filter did not treat this regular file as a version
    original = Path.open

    def no_lock_read(path, *args, **kwargs):
        assert path != lock
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", no_lock_read)
    records = installer.registry(lib)
    assert [r["commit"] for r in records["versions"]] == [old.name, new.name]
    assert records["legacy_locks"] == [lock.name]
    installer.activate(new.name, lib, entry)
    installer.unlink(new.name, lib, entry)
    assert lock.stat() == before


@pytest.mark.parametrize(
    "name", ["unknown", "sl-accept-abc.lock", "sl-accept-ABC123456.lock", "C" * 40, "a" * 39]
)
@pytest.mark.parametrize("action", ["registry", "install", "activate", "unlink"])
def test_shared_registry_rejects_unknown_entries(library, name, action, monkeypatch):
    lib, entry, old, new = library
    (lib / name).write_text("not a version")
    before = entry.resolve()
    if action == "install":
        monkeypatch.setattr(installer, "verify_source", lambda _: {"commit": new.name})
    with pytest.raises(DeployError):
        if action == "registry":
            installer.registry(lib)
        elif action == "install":
            installer.install(Path("unused"), lib, entry)
        else:
            getattr(installer, action)(old.name, lib, entry)
    assert entry.resolve() == before


@pytest.mark.parametrize(
    "kind", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFSOCK, stat.S_IFDIR]
)
def test_legacy_lock_special_types_fail(kind):
    with pytest.raises(DeployError):
        installer.check_lock_info(
            SimpleNamespace(st_mode=kind | 0o600, st_nlink=1, st_uid=0, st_gid=0)
        )


@pytest.mark.parametrize(
    "uid,gid,mode,links",
    [
        (1000, 0, 0o600, 1),
        (0, 1000, 0o600, 1),
        (0, 0, 0o644, 1),
        (0, 0, 0o660, 1),
        (0, 0, 0o400, 1),
        (0, 0, 0o600, 2),
    ],
)
def test_lock_owner_permissions_and_hardlinks(uid, gid, mode, links):
    with pytest.raises(DeployError):
        installer.check_lock_info(
            SimpleNamespace(st_mode=stat.S_IFREG | mode, st_nlink=links, st_uid=uid, st_gid=gid)
        )


def test_legacy_lock_symlink_not_followed(library):
    lib, _, old, _ = library
    os.symlink(old, lib / "sl-accept-webd20260904.lock", target_is_directory=True)
    with pytest.raises(DeployError):
        installer.registry(lib)


@pytest.mark.parametrize("previous", [True, False])
@pytest.mark.parametrize("action", ["activate", "install"])
def test_post_switch_list_failure_restores_exact_entry(library, previous, action, monkeypatch):
    lib, entry, old, new = library
    if not previous:
        entry.unlink()
    original = installer.registry_selfcheck
    calls = 0

    def fail_second(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("FAKE_PRIVATE_ERROR")
        return original(*args)

    monkeypatch.setattr(installer, "registry_selfcheck", fail_second)
    monkeypatch.setattr(
        installer, "verify_source", lambda _: json.loads((new / "installed.json").read_text())
    )
    with pytest.raises(DeployError, match="^REGISTRY_SELFCHECK_FAILED_ENTRY_RESTORED$"):
        if action == "install":
            installer.install(Path("unused"), lib, entry)
        else:
            installer.activate(new.name, lib, entry)
    assert entry.resolve() == old / "deploy-lightweight.sh" if previous else not entry.is_symlink()
    assert new.is_dir()


def test_install_immediate_list_same_registry(library, monkeypatch):
    lib, entry, _, new = library
    lock = lib / "sl-accept-webd20260904.lock"
    lock.write_bytes(b"retained")
    lock.chmod(0o600)
    monkeypatch.setattr(
        installer, "verify_source", lambda _: json.loads((new / "installed.json").read_text())
    )
    installer.install(Path("unused"), lib, entry)
    assert len(installer.registry(lib)["versions"]) == 2
    assert entry.resolve() == new / "deploy-lightweight.sh"
    assert lock.read_bytes() == b"retained"


def test_dedicated_lock_location_exclusion_and_no_truncation(tmp_path, monkeypatch):
    root = tmp_path / "locks"
    held = set()

    def flock(fd, flags):
        inode = os.fstat(fd).st_ino
        if inode in held:
            raise BlockingIOError
        held.add(inode)

    # Fake only flock on Windows; real POSIX implementation is used in Hong Kong.
    monkeypatch.setitem(sys.modules, "fcntl", SimpleNamespace(flock=flock, LOCK_EX=2, LOCK_NB=4))
    monkeypatch.setattr(os, "O_NOFOLLOW", getattr(os, "O_NOFOLLOW", 0), raising=False)
    monkeypatch.setattr(os, "O_NONBLOCK", getattr(os, "O_NONBLOCK", 0), raising=False)
    name = "sl-accept-webd20260904r3.lock"
    with installer.operation_lock(name, root):  # noqa: SIM117 -- outer lock must remain held
        with pytest.raises(BlockingIOError), installer.operation_lock(name, root):
            pytest.fail("second concurrent operation must not run")
    lock = root / name
    assert lock.exists()
    held.clear()
    lock.write_bytes(b"audit retained")
    with installer.operation_lock(name, root):
        assert lock.read_bytes() == b"audit retained"
    cli = Path(installer.__file__).with_name("deploy_cli.py").read_text()
    assert 'with operation_lock(args.project + ".lock")' in cli
    assert "/opt/storylens/lib/storylens-online-deploy" not in cli
    assert str(installer.LOCK_ROOT).replace("\\", "/") == "/run/lock/storylens-online-deploy"


def test_unlink_selfcheck_failure_restores_previous(library, monkeypatch):
    lib, entry, old, _ = library
    original = installer.registry_selfcheck

    def fail_unlinked(lib, entry, target):
        if target is None:
            raise RuntimeError("fixed test failure")
        original(lib, entry, target)

    monkeypatch.setattr(installer, "registry_selfcheck", fail_unlinked)
    with pytest.raises(DeployError, match="ENTRY_RESTORED"):
        installer.unlink(old.name, lib, entry)
    assert entry.resolve() == old / "deploy-lightweight.sh"


@pytest.mark.skipif(
    os.name != "posix", reason="requires Linux kernel flock; Windows only tests OS boundary Fake"
)
def test_real_linux_flock_exclusion(tmp_path):
    if os.getuid() != 0:
        pytest.skip("root ownership acceptance requires root")
    root = tmp_path / "locks"
    with installer.operation_lock("sl-accept-kernel1234.lock", root):  # noqa: SIM117
        with (
            pytest.raises(BlockingIOError),
            installer.operation_lock("sl-accept-kernel1234.lock", root),
        ):
            pytest.fail("kernel must deny concurrent lock")
    with installer.operation_lock("sl-accept-kernel1234.lock", root):
        pass
