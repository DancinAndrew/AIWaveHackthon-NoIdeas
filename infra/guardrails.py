"""Fail-closed checks for the hackathon AWS account restrictions.

The checks in this module run before any deploy or upload command.  They only
inspect local files and synthesized CloudFormation; they never call AWS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


PUBLIC_ACCESS_BLOCK_KEYS = (
    "BlockPublicAcls",
    "BlockPublicPolicy",
    "IgnorePublicAcls",
    "RestrictPublicBuckets",
)
PROHIBITED_RESOURCE_TYPES = frozenset(
    {
        "AWS::EC2::Instance",
        "AWS::EMR::Cluster",
        "AWS::SageMaker::TrainingJob",
    }
)
RDS_RESOURCE_TYPES = frozenset(
    {"AWS::RDS::DBInstance", "AWS::RDS::DBCluster"}
)
APPROVED_BEDROCK_MODELS = frozenset(
    {
        "amazon.nova-2-lite-v1:0",
        "amazon.titan-embed-text-v2:0",
    }
)
UTILITY_KB_ROOT = Path("data/mock/knowledge_base/utility_repair")
APPROVED_UPLOAD_FILES = frozenset(
    str(UTILITY_KB_ROOT / f"{stem}{suffix}")
    for stem in ("01-safety", "02-sop", "03-notice", "04-terms", "05-faq")
    for suffix in (".md", ".md.metadata.json")
)
MAX_UPLOAD_BYTES = 1_000_000

EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])",
    re.IGNORECASE,
)
TAIWAN_MOBILE_PATTERN = re.compile(r"(?<!\d)09\d{2}[- ]?\d{3}[- ]?\d{3}(?!\d)")
TAIWAN_ID_PATTERN = re.compile(r"(?<![A-Z0-9])[A-Z][12]\d{8}(?!\d)")
PAYMENT_NUMBER_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
EXECUTABLE_MAGICS = (
    b"\x7fELF",
    b"MZ",
    b"\xfe\xed\xfa\xce",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
)


class GuardrailViolation(ValueError):
    """Raised when local deployment inputs violate an account restriction."""

    def __init__(self, violations: str | Iterable[str]) -> None:
        if isinstance(violations, str):
            self.violations = (violations,)
        else:
            self.violations = tuple(violations)
        super().__init__("AWS deployment guardrail failed: " + "; ".join(self.violations))


def validate_cloudformation(template: Mapping[str, Any]) -> None:
    """Validate a synthesized CloudFormation template without calling AWS."""

    violations: list[str] = []
    resources = template.get("Resources")
    if not isinstance(resources, Mapping):
        raise GuardrailViolation("template Resources must be an object")

    for logical_id, resource in resources.items():
        if not isinstance(resource, Mapping):
            violations.append(f"{logical_id}: resource must be an object")
            continue
        resource_type = resource.get("Type")
        properties = resource.get("Properties", {})
        if not isinstance(properties, Mapping):
            violations.append(f"{logical_id}: Properties must be an object")
            continue

        if resource_type in PROHIBITED_RESOURCE_TYPES:
            violations.append(f"{logical_id}: {resource_type} is prohibited")
        if resource_type == "AWS::S3::Bucket":
            _validate_s3_bucket(str(logical_id), properties, violations)
        if resource_type in RDS_RESOURCE_TYPES:
            if properties.get("PubliclyAccessible") is not False:
                violations.append(
                    f"{logical_id}: PubliclyAccessible must be explicitly false"
                )
        if resource_type == "AWS::EC2::SecurityGroup":
            ingress = properties.get("SecurityGroupIngress", [])
            _validate_ingress(str(logical_id), ingress, violations)
        if resource_type == "AWS::EC2::SecurityGroupIngress":
            _validate_ingress(str(logical_id), [properties], violations)

        _validate_model_references(str(logical_id), properties, violations)

    if violations:
        raise GuardrailViolation(violations)


def _validate_s3_bucket(
    logical_id: str,
    properties: Mapping[str, Any],
    violations: list[str],
) -> None:
    block = properties.get("PublicAccessBlockConfiguration")
    if not isinstance(block, Mapping):
        violations.append(f"{logical_id}: PublicAccessBlockConfiguration is required")
        return
    for key in PUBLIC_ACCESS_BLOCK_KEYS:
        if block.get(key) is not True:
            violations.append(f"{logical_id}: {key} must be explicitly true")


def _validate_ingress(
    logical_id: str,
    ingress: object,
    violations: list[str],
) -> None:
    if not isinstance(ingress, list):
        violations.append(f"{logical_id}: SecurityGroupIngress must be a list")
        return
    for index, rule in enumerate(ingress):
        if not isinstance(rule, Mapping):
            violations.append(f"{logical_id}: ingress rule {index} must be an object")
            continue
        for key, world_cidr in (("CidrIp", "0.0.0.0/0"), ("CidrIpv6", "::/0")):
            if rule.get(key) == world_cidr:
                violations.append(
                    f"{logical_id}: ingress rule {index} permits {world_cidr}"
                )


def _validate_model_references(
    logical_id: str,
    value: object,
    violations: list[str],
    path: str = "Properties",
) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            normalized_key = re.sub(r"[^A-Z0-9]", "", str(key).upper())
            is_model_reference = (
                "MODELID" in normalized_key
                or normalized_key in {"FOUNDATIONMODEL", "EMBEDDINGMODELARN"}
            )
            if is_model_reference:
                if not _is_approved_model_reference(child):
                    violations.append(
                        f"{logical_id}: {child_path} references unapproved model {child!r}"
                    )
            else:
                _validate_model_references(
                    logical_id,
                    child,
                    violations,
                    child_path,
                )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_model_references(
                logical_id,
                child,
                violations,
                f"{path}[{index}]",
            )


def _is_approved_model_reference(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return value in APPROVED_BEDROCK_MODELS or any(
        value.endswith(f"/{model_id}") for model_id in APPROVED_BEDROCK_MODELS
    )


def validate_upload_manifest(
    repository_root: Path,
    manifest: Mapping[str, Any],
) -> tuple[Path, ...]:
    """Return verified upload paths or fail before an S3 API can be called."""

    files = manifest.get("files")
    if not isinstance(files, list) or not all(isinstance(item, str) for item in files):
        raise GuardrailViolation("upload manifest files must be a list of paths")

    requested = set(files)
    hashes = manifest.get("sha256")
    unexpected = sorted(requested - APPROVED_UPLOAD_FILES)
    missing = sorted(APPROVED_UPLOAD_FILES - requested)
    violations: list[str] = []
    if unexpected:
        violations.append(f"paths are not approved for upload: {', '.join(unexpected)}")
    if missing:
        violations.append(f"curated upload files are missing: {', '.join(missing)}")
    if len(files) != len(requested):
        violations.append("upload manifest contains duplicate paths")
    if not isinstance(hashes, Mapping):
        violations.append("upload manifest SHA-256 map is required")
    else:
        hash_paths = set(hashes)
        if hash_paths != requested:
            violations.append("upload manifest SHA-256 paths must match files exactly")
        for relative_path, digest in hashes.items():
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                violations.append(
                    f"{relative_path}: SHA-256 must be 64 lowercase hexadecimal characters"
                )
    if violations:
        raise GuardrailViolation(violations)

    root = repository_root.resolve()
    verified: list[Path] = []
    for relative_path in sorted(requested):
        unresolved = root / relative_path
        if unresolved.is_symlink():
            violations.append(f"{relative_path}: symbolic links are not allowed")
            continue
        resolved = unresolved.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            violations.append(f"{relative_path}: path escapes the repository")
            continue
        try:
            scan_allowed_file(resolved)
        except GuardrailViolation as error:
            violations.extend(f"{relative_path}: {item}" for item in error.violations)
        else:
            expected_digest = hashes.get(relative_path) if isinstance(hashes, Mapping) else None
            actual_digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
            if actual_digest != expected_digest:
                violations.append(f"{relative_path}: SHA-256 does not match reviewed content")
            else:
                verified.append(resolved)

    if violations:
        raise GuardrailViolation(violations)
    return tuple(verified)


def scan_allowed_file(path: Path) -> None:
    """Scan a curated text object for identifiers and executable content."""

    if not path.is_file():
        raise GuardrailViolation("file does not exist or is not a regular file")
    if path.suffix != ".md" and not path.name.endswith(".md.metadata.json"):
        raise GuardrailViolation("file extension is not approved")

    size = path.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise GuardrailViolation(f"file exceeds {MAX_UPLOAD_BYTES} bytes")
    content = path.read_bytes()
    if any(content.startswith(magic) for magic in EXECUTABLE_MAGICS):
        raise GuardrailViolation("executable content is prohibited")
    if b"\x00" in content:
        raise GuardrailViolation("binary content is prohibited")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise GuardrailViolation("file must be valid UTF-8 text") from error

    findings: list[str] = []
    if EMAIL_PATTERN.search(text):
        findings.append("email address detected")
    if TAIWAN_MOBILE_PATTERN.search(text):
        findings.append("Taiwan mobile number detected")
    if TAIWAN_ID_PATTERN.search(text):
        findings.append("Taiwan national identifier detected")
    if any(_passes_luhn(candidate) for candidate in PAYMENT_NUMBER_PATTERN.findall(text)):
        findings.append("payment-card-like identifier detected")
    if findings:
        raise GuardrailViolation(findings)


def _passes_luhn(candidate: str) -> bool:
    digits = [int(character) for character in candidate if character.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise GuardrailViolation(f"{path}: top-level JSON value must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("infra/upload-manifest.json"),
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    arguments = parser.parse_args()

    validate_cloudformation(_load_json(arguments.template))
    verified = validate_upload_manifest(
        arguments.repository_root,
        _load_json(arguments.manifest),
    )
    print(f"AWS deployment guardrails passed; {len(verified)} upload files verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
