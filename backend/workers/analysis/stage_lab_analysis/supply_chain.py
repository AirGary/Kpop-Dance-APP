from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


LOCK_PATTERN = re.compile(
    r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^ ]+) "
    r"--hash=sha256:(?P<sha256>[0-9a-f]{64})$"
)
PROHIBITED_LICENSE_MARKERS = ("unknown", "non-commercial", "noncommercial")


class SupplyChainError(RuntimeError):
    """Raised when the reviewed dependency evidence is incomplete."""


def _canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def load_hashed_lock(path: Path) -> dict[str, dict[str, str]]:
    packages: dict[str, dict[str, str]] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = LOCK_PATTERN.fullmatch(line)
        if match is None:
            raise SupplyChainError(f"invalid hashed lock line {line_number}")
        package = match.groupdict()
        canonical_name = _canonical_name(package["name"])
        if canonical_name in packages:
            raise SupplyChainError(f"duplicate locked package: {canonical_name}")
        packages[canonical_name] = package
    if not packages:
        raise SupplyChainError("hashed lock must not be empty")
    return packages


def validate_supply_chain(lock_path: Path, license_path: Path) -> None:
    locked = load_hashed_lock(lock_path)
    try:
        manifest = json.loads(license_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SupplyChainError("dependency license manifest is unreadable") from error

    if manifest.get("commercialDistributionApproved") is not False:
        raise SupplyChainError("commercial distribution must remain explicitly unapproved")
    entries = manifest.get("packages")
    if not isinstance(entries, list):
        raise SupplyChainError("dependency license manifest requires packages")

    reviewed: dict[str, dict[str, object]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise SupplyChainError("dependency license entry must be an object")
        name = _canonical_name(str(entry.get("name", "")))
        if not name or name in reviewed:
            raise SupplyChainError(f"invalid dependency license entry: {name}")
        license_name = str(entry.get("license", "")).strip()
        if not license_name or any(
            marker in license_name.lower() for marker in PROHIBITED_LICENSE_MARKERS
        ):
            raise SupplyChainError(f"unapproved dependency license: {name}")
        if entry.get("reviewStatus") != "approved-for-local-technical-demo":
            raise SupplyChainError(f"dependency is not reviewed: {name}")
        if not str(entry.get("sourceUrl", "")).startswith(
            "https://files.pythonhosted.org/"
        ):
            raise SupplyChainError(f"unapproved dependency source: {name}")
        evidence = entry.get("licenseEvidence")
        artifact_sha256 = entry.get("sha256")
        if not isinstance(evidence, list) or not any(
            isinstance(item, dict)
            and item.get("type") == "reviewed-artifact"
            and item.get("sha256") == artifact_sha256
            for item in evidence
        ):
            raise SupplyChainError(f"license evidence is not artifact-bound: {name}")
        reviewed[name] = entry

    if reviewed.keys() != locked.keys():
        missing = sorted(locked.keys() - reviewed.keys())
        extra = sorted(reviewed.keys() - locked.keys())
        raise SupplyChainError(f"dependency evidence mismatch: missing={missing}, extra={extra}")

    for name, package in locked.items():
        entry = reviewed[name]
        if entry.get("version") != package["version"]:
            raise SupplyChainError(f"dependency version mismatch: {name}")
        if entry.get("sha256") != package["sha256"]:
            raise SupplyChainError(f"dependency checksum mismatch: {name}")


def _main() -> int:
    parser = argparse.ArgumentParser(description="Validate reviewed AI dependencies")
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--licenses", type=Path, required=True)
    arguments = parser.parse_args()
    validate_supply_chain(arguments.lock, arguments.licenses)
    print("dependency_supply_chain=verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
