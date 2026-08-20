#!/usr/bin/env python3
"""Report abbreviation candidates not yet curated in the Copper cheatsheet.

This is deliberately a reviewer aid, not a gate: unknown candidates are printed
and the command still exits successfully. Page/schema or source-reference errors
are validation failures and return a non-zero status.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


CHEATSHEET = Path(__file__).with_name("index.html")
SCANNED_SUFFIXES = {".rs", ".md", ".ron", ".toml"}
SCANNED_ROOTS = {"core", "components", "examples", "doc"}
SCANNED_ROOT_FILES = {"README.md", "Cargo.toml"}
EXCLUDED_PARTS = {"target", "generated", "vendor", "logs"}
EXCLUDED_FILES = {
    "components/payloads/cu_ros2_payloads/all_rihs.md",  # generated ROS interface-hash inventory
}
EXPECTED_COVERAGE = {
    "BMI088", "IMU", "ESC", "GNSS", "AHRS", "PID", "DShot", "BDShot",
    "CRSF", "ELRS", "MSP", "RRT*", "NED", "GPIO", "I2C", "SPI", "UART",
    "DAG", "RON", "SoA", "CopperList", "TOV",
}

UPPER_TOKEN = re.compile(r"(?<![A-Za-z0-9_])([A-Z][A-Z0-9]{1,7}(?:[-/][A-Z0-9]+)?)(?![A-Za-z0-9_])")
MODEL_TOKEN = re.compile(r"(?<![A-Za-z0-9_])([a-z]{2,}[0-9]{2,}[a-z0-9]*)(?![A-Za-z0-9_])")
TERM_DATA = re.compile(
    r'<script\s+id="term-data"\s+type="application/json">\s*(.*?)\s*</script>',
    re.DOTALL,
)

# Reviewed families of tokens that are meaningful to code, but not useful
# robotics/Copper glossary entries. Exact suppressions below handle the rest.
PATTERN_SUPPRESSIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^[A-Z]?[0-9]+$"), "numeric/test label"),
    (re.compile(r"^[CMTDRS][0-9]+$"), "fixture, channel, or register label"),
    (re.compile(r"^CL[0-9]+$"), "CopperList fixture label"),
    (re.compile(r"^(?:REQ|TEST|DET|CGC|CLM|SMON)(?:-[A-Z0-9]+)+$"), "safety-case identifier"),
    (re.compile(r"^(?:GPIO|UART|USART|SPI|I2C|PIO|PWM|SDMMC)[0-9]+$"), "numbered peripheral instance"),
    (re.compile(r"^[A-Z]{1,3}[0-9]{1,3}$"), "short register/pin/test identifier"),
)

SUPPRESSIONS: dict[str, str] = {
    # Rust scalar/type and numeric vocabulary.
    **{token: "Rust scalar or numeric type" for token in (
        "U8", "U16", "U32", "U64", "U128", "I8", "I16", "I32", "I64", "I128",
        "F16", "F32", "F64", "NAN", "INFINITY", "EPSILON", "PI", "TAU",
    )},
    # Generic code, test, and prose tokens.
    **{token: "generic code/prose token" for token in (
        "ABORT", "ADDED", "ALIGN", "ALL", "ALLOC", "ANONYMOUS", "AUTO", "BACKGROUND",
        "BAD", "BLACK", "BLK", "BLUE", "BOLD", "BUS", "COMPONENTS", "COUNT", "DEFAULT",
        "DESCRIPTOR", "ERROR", "FORMAT", "GREEN", "IDENTITY", "IGNORE", "INFINITY",
        "ITERATIONS", "LEFT", "LOCK", "MARGIN", "MAX", "METADATA", "MIN", "MODE", "MOTOR",
        "NAME", "NAMES", "NONE", "NORMAL", "NOTE", "NOT", "NUMERATOR", "OK", "PATH", "PING",
        "PRIME", "RED", "RESET", "RESETS", "SHUTDOWN", "SKYBOX", "STAGES", "TABLE", "TAG",
        "TEST", "THICK", "TODO", "UNITS", "WHITE", "WIDTH", "YELLOW", "ZERO",
    )},
    # Generic developer/tooling abbreviations outside the chosen scope.
    **{token: "generic software/tooling term" for token in (
        "API", "ASCII", "BSD", "CI", "CLI", "CPU", "CUDA", "DEV", "GIL", "GNU", "HTML",
        "HTTP", "HTTPS", "ID", "IO", "JSON", "JSON5", "MIT", "OS", "PTY", "README", "SDK",
        "SVG", "TLS", "TOML", "TUI", "UI", "URL", "UTF", "UTF-8", "WASM", "WASM32", "WASD", "XML", "YAML", "ZST",
    )},
    # Internal generic parameters and implementation labels.
    **{token: "internal type parameter or implementation shorthand" for token in (
        "AARCH64", "AF", "BI", "CB", "CGC", "CLM", "CLW", "CT", "DET", "KFW", "MI", "NBCL", "NC",
        "REQ", "RIHS01", "SAFETY", "SM", "SMON", "TD", "TI", "TLC", "TOVS", "TR",
        "RISCV32IMAC", "RISCV64", "STM32H7XX",
    )},
    # Concrete fixture data, numbered pins/channels, targets, and test names.
    **{token: "fixture, target, pin, channel, or test identifier" for token in (
        "ADVAPI32", "ANCH0001", "ANCH0002", "AVX512F", "BASE64", "CH1-CH8", "CH9-CH16",
        "GPIO10-13", "MOTOR1", "MOTOR2", "MOTOR3", "MOTOR4", "PE14/13", "PINIO1", "PINIO2",
        "PREINIT2", "REYAX123", "ROBOT001", "ROBOT17", "RP235XH", "SPLITMIX64", "TESTADS7883",
    )},
    # Register names and low-level protocol fields are intentionally outside
    # the user-facing robotics vocabulary scope.
    **{token: "register, bit-field, pin-bank, or low-level protocol label" for token in (
        "BSRR", "CFS", "CLK", "CMD", "CPIN", "CSR", "DM", "DP", "GPIOE", "HH", "MODER",
        "MSG", "PUPDR", "RCIN", "RSVD", "SA", "SB", "SC", "SCB", "SOP", "VDD", "ZID",
    )},
    # Reviewed words, brands, conference names, formats, and software concepts
    # that do not add useful abbreviation help for the selected scope.
    **{token: "reviewed non-glossary word or out-of-scope technical term" for token in (
        "ACTION", "ADS", "AFTER", "ALIGNED", "ANCHOR", "AND", "AUX", "BEEP", "BEEPER", "BF",
        "BF/INAV", "BY", "CDN", "CHECKSUM", "CI/CD", "CODE", "COLUMN", "COPYING", "DATA", "DEBUG",
        "DOA", "DRY", "ENODEV", "EOF", "FOO", "GAIN", "GB", "GEMM", "GLB", "GLTF", "HD", "HEAP",
        "HORIZON", "HORROR", "HW", "ICRA", "IF", "II", "INAV/BF", "IP", "LAST", "LAT", "LENGTH",
        "LLM", "LOG", "LR", "MESSAGE", "MIN/MAX", "ML", "MOST", "MPU", "NUL", "NVIDIA", "OF",
        "OFF", "OMG", "ON", "ONE", "PAIR", "PARAM", "PCI", "PINOUT", "POSITION", "POSIX", "PR",
        "PS", "READ", "RECENT", "REYAX", "RP", "RUN", "SIM", "SNAPSHOT", "START", "STREAM", "THIS",
        "TIME", "TTF", "TYPE", "USB-C", "WINDOW", "WOULD", "WRITE", "XX", "XY", "XYZ",
    )},
}


@dataclass
class Candidate:
    count: int = 0
    examples: list[str] = field(default_factory=list)

    def add(self, location: str) -> None:
        self.count += 1
        if len(self.examples) < 3 and location not in self.examples:
            self.examples.append(location)


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def load_terms() -> list[dict[str, object]]:
    try:
        html = CHEATSHEET.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"cannot read {CHEATSHEET}: {error}") from error
    match = TERM_DATA.search(html)
    if not match:
        raise ValueError("index.html has no term-data JSON block")
    try:
        terms = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid term-data JSON: {error}") from error
    if not isinstance(terms, list):
        raise ValueError("term-data must be a JSON array")
    return terms


def validate_terms(terms: list[dict[str, object]], repo: Path) -> list[str]:
    errors: list[str] = []
    seen_terms: dict[str, str] = {}
    valid_categories = {
        "hardware", "sensing", "control", "electrical", "comms",
        "navigation", "perception", "data", "copper",
    }
    required = ("term", "aliases", "expanded", "meaning", "copper", "category", "repo")
    for index, item in enumerate(terms, 1):
        if not isinstance(item, dict):
            errors.append(f"entry {index} is not an object")
            continue
        label = str(item.get("term", f"entry {index}"))
        for key in required:
            if key not in item or item[key] in (None, "", []):
                if key == "aliases" and item.get(key) == []:
                    continue
                errors.append(f"{label}: missing {key}")
        category = item.get("category")
        if category not in valid_categories:
            errors.append(f"{label}: invalid category {category!r}")
        aliases = item.get("aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(alias, str) for alias in aliases):
            errors.append(f"{label}: aliases must be a string array")
            aliases = []
        related = item.get("related", [])
        if not isinstance(related, list) or not all(isinstance(term, str) for term in related):
            errors.append(f"{label}: related must be a string array")
            related = []
        for name in [label, *aliases]:
            key = normalize(name)
            previous = seen_terms.get(key)
            if previous and previous != label:
                errors.append(f"{label}: name/alias {name!r} collides with {previous}")
            else:
                seen_terms[key] = label
        sources = item.get("repo", [])
        if not isinstance(sources, list) or not all(isinstance(path, str) for path in sources):
            errors.append(f"{label}: repo must be a string array")
        else:
            for source in sources:
                if not (repo / source).is_file():
                    errors.append(f"{label}: missing repo source {source}")
        official = item.get("official", [])
        if not isinstance(official, list):
            errors.append(f"{label}: official must be an array")
        else:
            for source in official:
                if not (
                    isinstance(source, list)
                    and len(source) == 2
                    and all(isinstance(value, str) and value for value in source)
                    and source[1].startswith("https://")
                ):
                    errors.append(f"{label}: malformed official source {source!r}")
    for expected in sorted(EXPECTED_COVERAGE):
        if normalize(expected) not in seen_terms:
            errors.append(f"missing representative coverage term/alias {expected}")
    return errors


def tracked_files(repo: Path) -> list[Path]:
    try:
        output = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(f"cannot list tracked files under {repo}: {error}") from error
    selected: list[Path] = []
    for raw in output.split(b"\0"):
        if not raw:
            continue
        relative = Path(raw.decode("utf-8", errors="surrogateescape"))
        if str(relative) in EXCLUDED_FILES or EXCLUDED_PARTS.intersection(relative.parts):
            continue
        in_scanned_root = relative.parts and relative.parts[0] in SCANNED_ROOTS
        if (in_scanned_root or str(relative) in SCANNED_ROOT_FILES) and relative.suffix in SCANNED_SUFFIXES:
            selected.append(relative)
    return selected


def suppression_reason(token: str) -> str | None:
    upper = token.upper()
    if upper in SUPPRESSIONS:
        return SUPPRESSIONS[upper]
    for pattern, reason in PATTERN_SUPPRESSIONS:
        if pattern.fullmatch(upper):
            return reason
    return None


def is_known(token: str, known: set[str]) -> bool:
    if normalize(token) in known:
        return True
    # The scanner may return a compound exactly as it appears in prose. If all
    # of its parts are curated independently, the compound is covered too.
    parts = [part for part in re.split(r"[/-]", token) if part]
    return len(parts) > 1 and all(normalize(part) in known for part in parts)


def scan(repo: Path, files: list[Path], known: set[str]) -> tuple[dict[str, Candidate], dict[str, Candidate], int]:
    candidates: dict[str, Candidate] = collections.defaultdict(Candidate)
    suppressed: dict[str, Candidate] = collections.defaultdict(Candidate)
    recognized = 0
    for relative in files:
        try:
            text = (repo / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            # Rust implementation bodies are saturated with constant/type names.
            # Acronyms remain useful when they are in Rust comments, while model
            # identifiers are useful anywhere. Markdown, RON, and Cargo metadata
            # are already user-facing enough to scan in full.
            patterns = [MODEL_TOKEN]
            if relative.suffix != ".rs" or line.lstrip().startswith(("//", "/*", "*")):
                patterns.append(UPPER_TOKEN)
            matches = {match.group(1) for pattern in patterns for match in pattern.finditer(line)}
            for token in matches:
                if is_known(token, known):
                    recognized += 1
                    continue
                location = f"{relative}:{line_number}"
                reason = suppression_reason(token)
                if reason:
                    suppressed[token].add(location)
                else:
                    candidates[token].add(location)
    return candidates, suppressed, recognized


def priority(item: tuple[str, Candidate]) -> tuple[int, int, str]:
    token, candidate = item
    model_bonus = 1 if re.search(r"[A-Za-z].*\d|\d.*[A-Za-z]", token) else 0
    return (-model_bonus, -candidate.count, token.casefold())


def print_group(title: str, values: dict[str, Candidate], limit: int, reasons: bool = False) -> None:
    print(f"\n{title} ({len(values)} distinct)")
    print("-" * 72)
    for token, candidate in sorted(values.items(), key=priority)[:limit]:
        reason = f" — {suppression_reason(token)}" if reasons else ""
        locations = ", ".join(candidate.examples)
        print(f"{token:<18} {candidate.count:>5}  {locations}{reason}")
    if len(values) > limit:
        print(f"… {len(values) - limit} more; rerun with --limit {len(values)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path, help="path to a copper-rs checkout")
    parser.add_argument("--limit", type=int, default=100, help="maximum rows per report group")
    parser.add_argument("--show-suppressed", action="store_true", help="show reviewed false-positive tokens")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.repo.expanduser().resolve()
    if not (repo / ".git").exists():
        print(f"error: {repo} is not a copper-rs Git checkout", file=sys.stderr)
        return 2
    try:
        terms = load_terms()
        errors = validate_terms(terms, repo)
        files = tracked_files(repo)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if errors:
        print("Cheatsheet validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 2

    known = {
        normalize(name)
        for item in terms
        for name in [
            str(item["term"]),
            *[str(alias) for alias in item.get("aliases", [])],
            *[str(term) for term in item.get("related", [])],
        ]
    }
    candidates, suppressed, recognized = scan(repo, files, known)
    aliases = sum(len(item.get("aliases", [])) for item in terms)
    related = sum(len(item.get("related", [])) for item in terms)
    print(
        f"Validated {len(terms)} entries, {aliases} aliases, and {related} related terms "
        f"against {len(files)} tracked source files."
    )
    print(f"Recognized {recognized} term occurrences; suppressed {sum(item.count for item in suppressed.values())} reviewed-noise occurrences.")
    print_group("Candidates needing human review", candidates, max(args.limit, 1))
    if args.show_suppressed:
        print_group("Suppressed candidates", suppressed, max(args.limit, 1), reasons=True)
    print("\nInformational audit complete (new candidates do not fail the command).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
