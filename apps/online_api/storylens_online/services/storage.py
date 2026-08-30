from __future__ import annotations

import hashlib
import os
import re
import secrets
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from storylens_online.errors import PublicApiError

STORAGE_KEY_PATTERN = re.compile(r"^[0-9a-f]{64}\.txt$")


class StoredUpload(BaseModel):
    model_config = ConfigDict(frozen=True)

    original_filename: str = Field(min_length=1, max_length=255)
    storage_key: str = Field(pattern=r"^[0-9a-f]{64}\.txt$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_size_bytes: int = Field(gt=0)


class SecureUploadStorage:
    def __init__(self, root: str | Path, max_bytes: int) -> None:
        self.root = Path(root).resolve()
        self.max_bytes = max_bytes

    def store(self, original_filename: str | None, content: bytes) -> StoredUpload:
        display_name = self._safe_display_name(original_filename)
        if Path(display_name).suffix.lower() != ".txt":
            raise PublicApiError(415, "txt_only", "Phase 2A 只支持 TXT 文件。")
        if not content:
            raise PublicApiError(400, "empty_file", "不能上传空文件。")
        if len(content) > self.max_bytes:
            raise PublicApiError(413, "file_too_large", "文件超过当前上传大小限制。")
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise PublicApiError(
                400,
                "invalid_text_encoding",
                "TXT 必须使用 UTF-8 或 UTF-8-SIG 编码。",
            ) from exc

        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        storage_key, target = self._allocate_target()
        with target.open("xb") as output:
            output.write(content)
        os.chmod(target, 0o600)
        return StoredUpload(
            original_filename=display_name,
            storage_key=storage_key,
            sha256=hashlib.sha256(content).hexdigest(),
            file_size_bytes=len(content),
        )

    def read(self, storage_key: str) -> bytes:
        return self.path_for(storage_key).read_bytes()

    def delete(self, storage_key: str) -> None:
        self.path_for(storage_key).unlink(missing_ok=True)

    def path_for(self, storage_key: str) -> Path:
        if not STORAGE_KEY_PATTERN.fullmatch(storage_key):
            raise ValueError("invalid generated storage key")
        target = (self.root / storage_key).resolve()
        if target.parent != self.root:
            raise ValueError("storage key escaped upload root")
        return target

    @staticmethod
    def _safe_display_name(original_filename: str | None) -> str:
        candidate = (original_filename or "upload.txt").replace("\\", "/")
        basename = candidate.rsplit("/", maxsplit=1)[-1].strip()
        if not basename:
            basename = "upload.txt"
        return basename[:255]

    def _allocate_target(self) -> tuple[str, Path]:
        for _ in range(5):
            storage_key = f"{secrets.token_hex(32)}.txt"
            target = self.path_for(storage_key)
            if not target.exists():
                return storage_key, target
        raise RuntimeError("could not allocate upload storage key")
