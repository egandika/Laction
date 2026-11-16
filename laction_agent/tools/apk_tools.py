"""Read-only Android APK inspection/extraction using Python stdlib only.

APK files are ZIP containers, but the analyzer never installs or executes them.
It recognizes both text XML and Android's binary AXML manifest format, scans a
bounded amount of DEX/text content, and reports only secret types/locations (never
secret values). This is lightweight triage, not a replacement for apktool/jadx or
an expert mobile security review.
"""
from __future__ import annotations

import re
import struct
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

from . import file_tools
from .registry import get_registry

ANDROID_NS = "http://schemas.android.com/apk/res/android"
MAX_APK_BYTES = 200 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 25_000
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_SCAN_BYTES = 64 * 1024 * 1024
MAX_SCAN_PER_ENTRY = 8 * 1024 * 1024
MAX_EXTRACT_BYTES = 64 * 1024 * 1024
NO_INDEX = 0xFFFFFFFF

_DANGEROUS_PERMISSIONS = {
    "android.permission.READ_SMS", "android.permission.RECEIVE_SMS", "android.permission.SEND_SMS",
    "android.permission.READ_CALL_LOG", "android.permission.WRITE_CALL_LOG",
    "android.permission.READ_CONTACTS", "android.permission.WRITE_CONTACTS",
    "android.permission.ACCESS_FINE_LOCATION", "android.permission.ACCESS_COARSE_LOCATION",
    "android.permission.CAMERA", "android.permission.RECORD_AUDIO", "android.permission.CALL_PHONE",
    "android.permission.READ_PHONE_STATE", "android.permission.READ_PHONE_NUMBERS",
    "android.permission.READ_EXTERNAL_STORAGE", "android.permission.WRITE_EXTERNAL_STORAGE",
    "android.permission.MANAGE_EXTERNAL_STORAGE", "android.permission.READ_MEDIA_IMAGES",
    "android.permission.READ_MEDIA_VIDEO", "android.permission.READ_MEDIA_AUDIO",
    "android.permission.BODY_SENSORS", "android.permission.BLUETOOTH_CONNECT",
}
_COMPONENTS = {"activity", "activity-alias", "service", "receiver", "provider"}
_DEX_RE = re.compile(r"^classes(?:\d+)?\.dex$", re.IGNORECASE)
_PRINTABLE_RE = re.compile(rb"[\x20-\x7e]{6,}")
_URL_RE = re.compile(r"https?://[^\s\"'<>\\]+", re.IGNORECASE)
_SECRET_PATTERNS = (
    (re.compile(rb"\bAKIA[0-9A-Z]{16}\b"), "AWS access-key candidate"),
    (re.compile(rb"\bAIza[0-9A-Za-z_-]{20,}\b"), "Google API-key candidate"),
    (re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "GitHub token candidate"),
    (re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "Slack token candidate"),
    (re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private-key PEM marker"),
    (
        re.compile(rb"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\b\s*[:=]\s*[\"']?[A-Za-z0-9_./+=-]{12,}"),
        "credential-like assignment",
    ),
)

reg = get_registry()


def _read_len8(data: bytes, pos: int) -> tuple[int, int]:
    if pos >= len(data):
        raise ValueError("string length di luar batas")
    first = data[pos]
    if first & 0x80:
        if pos + 1 >= len(data):
            raise ValueError("string length UTF-8 terpotong")
        return ((first & 0x7F) << 8) | data[pos + 1], pos + 2
    return first, pos + 1


def _read_len16(data: bytes, pos: int) -> tuple[int, int]:
    if pos + 2 > len(data):
        raise ValueError("string length UTF-16 terpotong")
    first = struct.unpack_from("<H", data, pos)[0]
    if first & 0x8000:
        if pos + 4 > len(data):
            raise ValueError("string length UTF-16 terpotong")
        second = struct.unpack_from("<H", data, pos + 2)[0]
        return ((first & 0x7FFF) << 16) | second, pos + 4
    return first, pos + 2


def _parse_string_pool(data: bytes, offset: int, header_size: int, chunk_size: int) -> list[str]:
    end = offset + chunk_size
    if header_size < 28 or offset + header_size > end or offset + 28 > end:
        raise ValueError("header string pool tidak valid")
    string_count, style_count, flags, strings_start, _styles_start = struct.unpack_from("<IIIII", data, offset + 8)
    if string_count > 100_000 or style_count > 100_000:
        raise ValueError("string pool terlalu besar")
    offsets_start = offset + header_size
    if offsets_start + (string_count + style_count) * 4 > end:
        raise ValueError("tabel offset string pool terpotong")
    strings_base = offset + strings_start
    if strings_base < offsets_start or strings_base > end:
        raise ValueError("awal data string pool tidak valid")

    utf8 = bool(flags & 0x100)
    result: list[str] = []
    for i in range(string_count):
        relative = struct.unpack_from("<I", data, offsets_start + i * 4)[0]
        pos = strings_base + relative
        if pos < strings_base or pos >= end:
            raise ValueError("offset string pool di luar batas")
        if utf8:
            _utf16_len, pos = _read_len8(data, pos)
            byte_len, pos = _read_len8(data, pos)
            if byte_len > end - pos:
                raise ValueError("string UTF-8 terpotong")
            value = data[pos:pos + byte_len].decode("utf-8", errors="replace")
        else:
            char_len, pos = _read_len16(data, pos)
            byte_len = char_len * 2
            if byte_len > end - pos:
                raise ValueError("string UTF-16 terpotong")
            value = data[pos:pos + byte_len].decode("utf-16le", errors="replace")
        result.append(value)
    return result


def _typed_value(strings: list[str], data_type: int, value: int) -> str:
    if data_type == 0x03:  # TYPE_STRING
        return strings[value] if value < len(strings) else ""
    if data_type == 0x12:  # TYPE_INT_BOOLEAN
        return "true" if value else "false"
    if data_type == 0x10:  # TYPE_INT_DEC
        return str(value)
    if data_type == 0x11:  # TYPE_INT_HEX
        return f"0x{value:x}"
    if data_type in (0x01, 0x02):  # resource / attribute reference
        return f"@0x{value:08x}"
    return str(value)


def _parse_binary_axml(data: bytes) -> list[tuple[str, dict[str, str]]]:
    if len(data) < 8:
        raise ValueError("binary manifest terlalu pendek")
    root_type, root_header, root_size = struct.unpack_from("<HHI", data, 0)
    if root_type != 0x0003 or root_header < 8 or root_size > len(data) or root_size < root_header:
        raise ValueError("header Android binary XML tidak dikenal atau rusak")

    strings: list[str] = []
    events: list[tuple[str, dict[str, str]]] = []
    offset = root_header
    while offset + 8 <= root_size:
        chunk_type, header_size, chunk_size = struct.unpack_from("<HHI", data, offset)
        if header_size < 8 or chunk_size < header_size or offset + chunk_size > root_size:
            raise ValueError("chunk Android binary XML tidak valid")
        if chunk_type == 0x0001:  # RES_STRING_POOL_TYPE
            strings = _parse_string_pool(data, offset, header_size, chunk_size)
        elif chunk_type == 0x0102:  # RES_XML_START_ELEMENT_TYPE
            if not strings or header_size < 16 or chunk_size < 36:
                raise ValueError("elemen XML sebelum string pool atau header terpotong")
            namespace_i, name_i = struct.unpack_from("<II", data, offset + 16)
            attribute_start, attribute_size, attribute_count = struct.unpack_from("<HHH", data, offset + 24)
            if attribute_size < 20 or attribute_count > 4096:
                raise ValueError("tabel atribut Android XML tidak valid")
            attr_base = offset + 16 + attribute_start
            if attr_base < offset + 36 or attr_base + attribute_count * attribute_size > offset + chunk_size:
                raise ValueError("atribut Android XML di luar batas")

            def get_string(index: int) -> str:
                return strings[index] if index != NO_INDEX and index < len(strings) else ""

            tag = get_string(name_i)
            namespace = get_string(namespace_i)
            attrs: dict[str, str] = {}
            for i in range(attribute_count):
                pos = attr_base + i * attribute_size
                ns_i, attr_name_i, raw_i = struct.unpack_from("<III", data, pos)
                value_size = struct.unpack_from("<H", data, pos + 12)[0]
                data_type = data[pos + 15]
                typed_data = struct.unpack_from("<I", data, pos + 16)[0]
                if value_size < 8:
                    raise ValueError("nilai atribut Android XML tidak valid")
                attr_name = get_string(attr_name_i)
                raw_value = get_string(raw_i)
                value = raw_value if raw_i != NO_INDEX else _typed_value(strings, data_type, typed_data)
                attr_ns = get_string(ns_i)
                key = f"android:{attr_name}" if attr_ns == ANDROID_NS else attr_name
                if key:
                    attrs[key] = value
            if tag:
                events.append((tag, attrs))
        offset += chunk_size
    if not events:
        raise ValueError("tidak menemukan elemen di binary manifest")
    return events


def _parse_manifest(data: bytes) -> list[tuple[str, dict[str, str]]]:
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("deklarasi entity XML ditolak")
    if data.lstrip().startswith(b"<"):
        root = ET.fromstring(data)
        events: list[tuple[str, dict[str, str]]] = []
        for elem in root.iter():
            tag = elem.tag.rsplit("}", 1)[-1]
            attrs = {}
            for key, value in elem.attrib.items():
                if key.startswith("{" + ANDROID_NS + "}"):
                    key = "android:" + key.split("}", 1)[1]
                else:
                    key = key.rsplit("}", 1)[-1]
                attrs[key] = value
            events.append((tag, attrs))
        return events
    return _parse_binary_axml(data)


def _manifest_summary(events: list[tuple[str, dict[str, str]]]) -> dict:
    info: dict = {
        "package": "",
        "version_name": "",
        "version_code": "",
        "min_sdk": "",
        "target_sdk": "",
        "permissions": [],
        "application": {},
        "components": [],
    }
    for tag, attrs in events:
        if tag == "manifest":
            info["package"] = attrs.get("package", "")
            info["version_name"] = attrs.get("android:versionName", attrs.get("versionName", ""))
            info["version_code"] = attrs.get("android:versionCode", attrs.get("versionCode", ""))
        elif tag == "uses-sdk":
            info["min_sdk"] = attrs.get("android:minSdkVersion", attrs.get("minSdkVersion", ""))
            info["target_sdk"] = attrs.get("android:targetSdkVersion", attrs.get("targetSdkVersion", ""))
        elif tag.startswith("uses-permission"):
            permission = attrs.get("android:name", attrs.get("name", ""))
            if permission and permission not in info["permissions"]:
                info["permissions"].append(permission)
        elif tag == "application":
            info["application"] = attrs
    app_permission = info["application"].get("android:permission", "")
    for tag, attrs in events:
        if tag in _COMPONENTS and attrs.get("android:exported", attrs.get("exported", "")).lower() == "true":
            name = attrs.get("android:name", attrs.get("name", "(tanpa nama)"))
            permission = attrs.get("android:permission", attrs.get("permission", app_permission))
            info["components"].append({"type": tag, "name": name, "permission": permission})
    info["permissions"].sort()
    return info


def _read_prefix(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> tuple[bytes, bool]:
    if info.file_size < 0:
        raise ValueError("ukuran entry ZIP tidak valid")
    with archive.open(info, "r") as stream:
        data = stream.read(limit + 1)
    truncated = len(data) > limit or info.file_size > limit
    return data[:limit], truncated


def _one_line(value: str, limit: int = 240) -> str:
    return " ".join(str(value).split())[:limit]


def _scan_secrets(data: bytes, entry: str, findings: set[tuple[str, str]]) -> None:
    safe_entry = _one_line(entry)
    for pattern, label in _SECRET_PATTERNS:
        if pattern.search(data):
            findings.add((label, safe_entry))


def _scan_domains(data: bytes, domains: set[str]) -> None:
    for run in _PRINTABLE_RE.findall(data):
        for match in _URL_RE.findall(run.decode("ascii", errors="ignore")):
            try:
                parsed = urlsplit(match.rstrip(".,);]"))
                if parsed.hostname and not parsed.username and not parsed.password:
                    domains.add(_one_line(parsed.hostname.lower(), 253))
            except ValueError:
                continue


def _boolean(value: str) -> bool:
    return value.strip().lower() in {"true", "1"}


def _report(path: Path, infos: list[zipfile.ZipInfo], manifest: dict | None,
            manifest_error: str, secrets: set[tuple[str, str]], domains: set[str],
            bytes_scanned: int, scan_limited: bool) -> str:
    workspace = file_tools.WORKSPACE.resolve()
    try:
        label = _one_line(str(path.resolve().relative_to(workspace)))
    except ValueError:
        label = _one_line(path.name)
    dex = sorted(_one_line(i.filename) for i in infos if _DEX_RE.fullmatch(Path(i.filename).name))
    lines = [
        "APK STATIC ANALYSIS — read-only; APK tidak di-install/dijalankan.",
        f"File: {label}",
        f"ZIP entries: {len(infos)} | DEX: {len(dex)} ({', '.join(dex[:12]) or 'tidak ada'})",
        f"Konten yang dipindai: {bytes_scanned:,} byte" + (" (mencapai batas scan)" if scan_limited else ""),
    ]
    if manifest is None:
        lines.append(f"Manifest: tidak dapat dibaca ({_one_line(manifest_error or 'AndroidManifest.xml tidak ada')}).")
    else:
        lines.extend([
            f"Package: {_one_line(manifest['package']) or '(tidak diketahui)'}",
            f"Versi: {_one_line(manifest['version_name']) or '(n/a)'} (code {_one_line(manifest['version_code']) or 'n/a'})",
            f"SDK: min={_one_line(manifest['min_sdk']) or 'n/a'}, target={_one_line(manifest['target_sdk']) or 'n/a'}",
        ])
        app = manifest["application"]
        if _boolean(app.get("android:debuggable", app.get("debuggable", "false"))):
            lines.append("[HIGH] android:debuggable=true")
        if _boolean(app.get("android:usesCleartextTraffic", app.get("usesCleartextTraffic", "false"))):
            lines.append("[MEDIUM] android:usesCleartextTraffic=true")
        if _boolean(app.get("android:allowBackup", app.get("allowBackup", "false"))):
            lines.append("[REVIEW] android:allowBackup=true — periksa data yang dapat dicadangkan")
        permissions = manifest["permissions"]
        lines.append(f"Permissions ({len(permissions)}):")
        for permission in permissions[:40]:
            risk = " [sensitive]" if permission in _DANGEROUS_PERMISSIONS else ""
            lines.append(f"  - {_one_line(permission)}{risk}")
        if len(permissions) > 40:
            lines.append(f"  ... {len(permissions) - 40} permission lain")
        unprotected = [c for c in manifest["components"] if not c["permission"]]
        if unprotected:
            lines.append(f"[REVIEW] {len(unprotected)} exported component tanpa permission eksplisit:")
            for component in unprotected[:20]:
                lines.append(f"  - {_one_line(component['type'])} {_one_line(component['name'])}")
            if len(unprotected) > 20:
                lines.append(f"  ... {len(unprotected) - 20} component lain")
        elif manifest["components"]:
            lines.append(f"Exported components: {len(manifest['components'])}; semuanya menyatakan permission.")

    if secrets:
        lines.append(f"Credential-like strings ({len(secrets)} temuan; nilai tidak ditampilkan):")
        for label, entry in sorted(secrets)[:30]:
            lines.append(f"  - {label} di {entry}")
        if len(secrets) > 30:
            lines.append(f"  ... {len(secrets) - 30} temuan lain")
    else:
        lines.append("Credential patterns yang dikenal: tidak ditemukan pada konten yang dipindai (bukan jaminan bebas secret).")
    if domains:
        lines.append("Host dari URL string (maks 30): " + ", ".join(sorted(domains)[:30]))
    lines.append("Catatan: heuristic dapat false positive/negative; verifikasi manual dan gunakan jadx/apktool untuk dekompilasi lengkap.")
    return "\n".join(lines)


@reg.register(
    "apk_analyze",
    "Analisis statis APK Android lokal: metadata/AXML manifest, permission, exported components, DEX/text strings, URL host, dan pola secret. Tidak menjalankan APK; hanya APK milik/yang berhak kamu audit.",
    {"type": "object", "properties": {"path": {"type": "string", "description": "Path .apk relatif ke workspace"}}, "required": ["path"]},
)
def apk_analyze(path: str, context: dict | None = None) -> str:
    try:
        apk = file_tools._safe(path)
    except ValueError as exc:
        return f"DITOLAK: {exc}"
    if not apk.is_file() or apk.suffix.lower() != ".apk":
        return "ERROR: path harus file .apk di dalam workspace."
    try:
        if apk.stat().st_size > MAX_APK_BYTES:
            return f"ERROR: ukuran APK melampaui batas {MAX_APK_BYTES // (1024 * 1024)} MiB."
        with zipfile.ZipFile(apk, "r") as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                return f"ERROR: archive memiliki terlalu banyak entry (maks {MAX_ARCHIVE_ENTRIES})."
            manifest_info = next((i for i in infos if i.filename == "AndroidManifest.xml"), None)
            manifest = None
            manifest_error = ""
            if manifest_info is not None:
                try:
                    raw_manifest, cut = _read_prefix(archive, manifest_info, MAX_MANIFEST_BYTES)
                    if cut:
                        raise ValueError("manifest melebihi batas ukuran")
                    manifest = _manifest_summary(_parse_manifest(raw_manifest))
                except (ValueError, ET.ParseError, struct.error, OSError) as exc:
                    manifest_error = str(exc)

            secrets: set[tuple[str, str]] = set()
            domains: set[str] = set()
            scanned = 0
            scan_limited = False
            candidates = [
                i for i in infos
                if _DEX_RE.fullmatch(Path(i.filename).name)
                or Path(i.filename).suffix.lower() in {".xml", ".json", ".txt", ".properties", ".yaml", ".yml", ".ini", ".cfg", ".smali", ".js", ".html"}
            ]
            for info in candidates:
                remaining = MAX_SCAN_BYTES - scanned
                if remaining <= 0:
                    scan_limited = True
                    break
                limit = min(remaining, MAX_SCAN_PER_ENTRY)
                try:
                    content, cut = _read_prefix(archive, info, limit)
                except (OSError, RuntimeError, zipfile.BadZipFile, ValueError):
                    continue
                scanned += len(content)
                scan_limited = scan_limited or cut
                _scan_secrets(content, info.filename, secrets)
                if _DEX_RE.fullmatch(Path(info.filename).name) or Path(info.filename).suffix.lower() in {".xml", ".json", ".txt", ".properties", ".yaml", ".yml", ".ini", ".cfg", ".smali", ".js", ".html"}:
                    _scan_domains(content, domains)
            return _report(apk, infos, manifest, manifest_error, secrets, domains, scanned, scan_limited)
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError) as exc:
        return f"ERROR membaca APK: {type(exc).__name__}: {exc}"


@reg.register(
    "apk_extract",
    "Ekstrak satu entry tertentu dari APK ZIP ke file workspace (tanpa extract-all; path traversal/zip-slip dicegah; maksimum 64 MiB).",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path APK relatif ke workspace"},
            "member": {"type": "string", "description": "Nama entry di dalam APK, mis. classes.dex"},
            "output_path": {"type": "string", "description": "Tujuan relatif ke workspace"},
        },
        "required": ["path", "member", "output_path"],
    },
)
def apk_extract(path: str, member: str, output_path: str, context: dict | None = None) -> str:
    try:
        apk = file_tools._safe(path)
        target = file_tools._safe(output_path)
    except ValueError as exc:
        return f"DITOLAK: {exc}"
    if not apk.is_file() or apk.suffix.lower() != ".apk":
        return "ERROR: path harus file .apk di dalam workspace."
    if target.resolve() == apk.resolve():
        return "ERROR: output_path tidak boleh menimpa file APK sumber."
    if not member or "\x00" in member:
        return "ERROR: nama member tidak valid."
    try:
        if apk.stat().st_size > MAX_APK_BYTES:
            return f"ERROR: ukuran APK melampaui batas {MAX_APK_BYTES // (1024 * 1024)} MiB."
        with zipfile.ZipFile(apk, "r") as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                return f"ERROR: archive memiliki terlalu banyak entry (maks {MAX_ARCHIVE_ENTRIES})."
            matches = [info for info in infos if info.filename == member and not info.is_dir()]
            if not matches:
                return f"ERROR: entry tidak ditemukan: {member}"
            info = matches[0]
            if info.file_size > MAX_EXTRACT_BYTES:
                return f"ERROR: entry melebihi batas {MAX_EXTRACT_BYTES // (1024 * 1024)} MiB."
            content, cut = _read_prefix(archive, info, MAX_EXTRACT_BYTES)
            if cut:
                return "ERROR: entry terpotong karena batas ukuran; file tidak ditulis."
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        try:
            shown = str(target.resolve().relative_to(file_tools.WORKSPACE.resolve()))
        except ValueError:
            shown = output_path
        return f"Berhasil mengekstrak {_one_line(member)} ({len(content)} byte) ke {_one_line(shown)}. APK tidak dijalankan."
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError) as exc:
        return f"ERROR ekstraksi APK: {type(exc).__name__}: {exc}"
