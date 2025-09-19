"""Helpers for decoding and applying Git binary patch hunks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

import zlib

try:  # pragma: no cover - optional typing import
    from typing import Literal
except ImportError:  # pragma: no cover - Python < 3.8 fallback
    Literal = str  # type: ignore[misc,assignment]

try:  # pragma: no cover - optional typing import
    from unidiff.patch import PatchedFile
except Exception:  # pragma: no cover - during docs builds
    PatchedFile = object  # type: ignore[misc,assignment]

from .localization import gettext as _

__all__ = [
    "BinaryPatchError",
    "attach_binary_patch_data",
    "get_attached_binary_patch",
    "apply_binary_patch",
]


class BinaryPatchError(Exception):
    """Raised when a Git binary patch cannot be decoded or applied."""


_BINARY_ATTR = "_patch_gui_binary_patch"

# Git's base85 alphabet used for binary patches. The order matters because each
# character maps to its numeric value directly by position.
_BASE85_ALPHABET = (
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "!#$%&()*+-;<=>?@^_`{|}~"
)
_BASE85_VALUES: Mapping[str, int] = {ch: idx for idx, ch in enumerate(_BASE85_ALPHABET)}


@dataclass(slots=True)
class _BinaryHunk:
    method: Literal["literal", "delta"]
    expected_size: int
    encoded_lines: Tuple[str, ...]

    def _decoded_bytes(self) -> bytes:
        if not self.encoded_lines:
            return b""

        chunks = bytearray()
        for line in self.encoded_lines:
            if not line:
                continue
            prefix = line[0]
            encoded = line[1:]
            if (len(encoded) % 5) != 0:
                raise BinaryPatchError(
                    _("Malformed binary patch line with length %d") % len(encoded)
                )
            if "A" <= prefix <= "Z":
                byte_length = ord(prefix) - ord("A") + 1
            elif "a" <= prefix <= "z":
                byte_length = ord(prefix) - ord("a") + 27
            else:
                raise BinaryPatchError(
                    _("Invalid binary patch length prefix: %s") % prefix
                )

            decoded_block = bytearray()
            for idx in range(0, len(encoded), 5):
                block = encoded[idx : idx + 5]
                acc = 0
                for ch in block:
                    try:
                        value = _BASE85_VALUES[ch]
                    except KeyError as exc:  # pragma: no cover - defensive
                        raise BinaryPatchError(
                            _("Invalid character %r in binary patch block") % ch
                        ) from exc
                    acc = acc * 85 + value
                decoded_block.extend(acc.to_bytes(4, "big"))

            if byte_length > len(decoded_block):
                raise BinaryPatchError(
                    _("Binary patch declared %d bytes but only %d available")
                    % (byte_length, len(decoded_block))
                )
            chunks.extend(decoded_block[:byte_length])

        return bytes(chunks)

    def inflate(self) -> bytes:
        raw = self._decoded_bytes()
        if not raw and self.expected_size == 0:
            return b""
        try:
            data = zlib.decompress(raw)
        except zlib.error as exc:  # pragma: no cover - defensive
            raise BinaryPatchError(
                _("Failed to decompress %s hunk: %s") % (self.method, exc)
            ) from exc
        if len(data) != self.expected_size:
            raise BinaryPatchError(
                _(
                    "Binary %s hunk expected %d bytes after decompressing but got %d"
                )
                % (self.method, self.expected_size, len(data))
            )
        return data

    def apply(self, base: bytes) -> bytes:
        data = self.inflate()
        if self.method == "literal":
            return data
        if self.method == "delta":
            return _apply_delta(base, data)
        raise BinaryPatchError(_("Unsupported binary patch method: %s") % self.method)


@dataclass(slots=True)
class BinaryPatchData:
    forward: _BinaryHunk
    reverse: Optional[_BinaryHunk] = None

    def apply(self, base: bytes) -> bytes:
        return self.forward.apply(base)


def attach_binary_patch_data(patch: Iterable[PatchedFile], raw_text: str) -> None:
    """Parse ``raw_text`` and attach binary patch metadata to ``patch`` files."""

    mapping = _parse_binary_blocks(raw_text)
    for pf in patch:
        if not getattr(pf, "is_binary_file", False):
            continue
        key = (_normalize(pf.source_file), _normalize(pf.target_file))
        data = mapping.get(key)
        if data is not None:
            setattr(pf, _BINARY_ATTR, data)


def get_attached_binary_patch(pf: PatchedFile) -> Optional[BinaryPatchData]:
    """Return the parsed binary patch data attached to ``pf`` if available."""

    data = getattr(pf, _BINARY_ATTR, None)
    return data if isinstance(data, BinaryPatchData) else None


def apply_binary_patch(pf: PatchedFile, base_bytes: bytes) -> bytes:
    """Return the new file contents by applying the attached binary patch."""

    data = get_attached_binary_patch(pf)
    if data is None:
        raise BinaryPatchError(
            _("Binary patch data missing for %s") % getattr(pf, "path", "<unknown>")
        )
    return data.apply(base_bytes)


def _normalize(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _parse_binary_blocks(raw_text: str) -> Dict[Tuple[Optional[str], Optional[str]], BinaryPatchData]:
    lines = raw_text.splitlines()
    mapping: Dict[Tuple[Optional[str], Optional[str]], BinaryPatchData] = {}
    current_key: Tuple[Optional[str], Optional[str]] | None = None
    idx = 0
    total = len(lines)

    while idx < total:
        line = lines[idx]
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                current_key = (_normalize(parts[2]), _normalize(parts[3]))
            else:  # pragma: no cover - defensive
                current_key = None
            idx += 1
            continue

        if line == "GIT binary patch":
            if current_key is None:
                idx += 1
                continue
            idx += 1
            hunks: List[_BinaryHunk] = []
            while idx < total:
                header = lines[idx]
                if not header:
                    idx += 1
                    continue
                if header.startswith("literal ") or header.startswith("delta "):
                    method, size_str = header.split(None, 1)
                    try:
                        expected_size = int(size_str.strip())
                    except ValueError as exc:
                        raise BinaryPatchError(
                            _("Invalid binary hunk header: %s") % header
                        ) from exc
                    idx += 1
                    encoded: List[str] = []
                    while idx < total and lines[idx]:
                        encoded.append(lines[idx])
                        idx += 1
                    hunks.append(
                        _BinaryHunk(method=method, expected_size=expected_size, encoded_lines=tuple(encoded))
                    )
                    while idx < total and not lines[idx]:
                        idx += 1
                    if idx < total and (
                        lines[idx].startswith("literal ")
                        or lines[idx].startswith("delta ")
                    ):
                        continue
                    break
                else:
                    break
            if hunks:
                mapping[current_key] = BinaryPatchData(
                    forward=hunks[0],
                    reverse=hunks[1] if len(hunks) > 1 else None,
                )
            continue

        idx += 1

    return mapping


def _read_varint(data: bytes, offset: int) -> Tuple[int, int]:
    value = 0
    shift = 0
    pos = offset
    while True:
        if pos >= len(data):
            raise BinaryPatchError(_("Unexpected end of delta stream"))
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
            continue
        return value, pos


def _apply_delta(base: bytes, delta: bytes) -> bytes:
    base_size, pos = _read_varint(delta, 0)
    if base_size != len(base):
        raise BinaryPatchError(
            _("Binary delta expects base of %d bytes but found %d")
            % (base_size, len(base))
        )
    result_size, pos = _read_varint(delta, pos)
    output = bytearray()

    while pos < len(delta):
        opcode = delta[pos]
        pos += 1
        if opcode & 0x80:
            copy_offset = 0
            copy_size = 0
            if opcode & 0x01:
                copy_offset |= delta[pos]
                pos += 1
            if opcode & 0x02:
                copy_offset |= delta[pos] << 8
                pos += 1
            if opcode & 0x04:
                copy_offset |= delta[pos] << 16
                pos += 1
            if opcode & 0x08:
                copy_offset |= delta[pos] << 24
                pos += 1
            if opcode & 0x10:
                copy_size |= delta[pos]
                pos += 1
            if opcode & 0x20:
                copy_size |= delta[pos] << 8
                pos += 1
            if opcode & 0x40:
                copy_size |= delta[pos] << 16
                pos += 1
            if copy_size == 0:
                copy_size = 0x10000
            end = copy_offset + copy_size
            if end > len(base):
                raise BinaryPatchError(
                    _("Binary delta copy exceeds source data (%d > %d)")
                    % (end, len(base))
                )
            output.extend(base[copy_offset:end])
        elif opcode:
            literal_size = opcode & 0x7F
            end = pos + literal_size
            if end > len(delta):
                raise BinaryPatchError(_("Binary delta literal overruns patch data"))
            output.extend(delta[pos:end])
            pos = end
        else:
            raise BinaryPatchError(_("Encountered reserved delta opcode"))

    if len(output) != result_size:
        raise BinaryPatchError(
            _("Binary delta produced %d bytes but expected %d")
            % (len(output), result_size)
        )
    return bytes(output)
