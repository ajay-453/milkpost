"""Stale guard for the committed coverage report (TestForge-fix arc F4.3).

coverage.xml (Cobertura) is committed so scanners that read the repo, such as
testforge.run, see the measured figure instead of guessing. CI regenerates it
and fails here if the committed copy has drifted more than one point.

Run:  python check_coverage.py coverage.xml /tmp/fresh.xml
Refresh after changing tests or code:
      python -m pytest -q --cov=app --cov-report=xml:coverage.xml
"""
import sys
import xml.etree.ElementTree as ET

TOLERANCE = 1.0  # percentage points


class ReportError(Exception):
    pass


def line_rate(path: str) -> float:
    try:
        rate = ET.parse(path).getroot().get("line-rate")
    except FileNotFoundError:
        raise ReportError(f"{path}: file not found")
    except ET.ParseError as e:
        raise ReportError(f"{path}: not valid XML ({e})")
    try:
        return float(rate) * 100
    except (TypeError, ValueError):
        raise ReportError(f"{path}: root element has no numeric line-rate")


def main(committed: str, fresh: str) -> int:
    try:
        old, new = line_rate(committed), line_rate(fresh)
    except ReportError as e:
        print(f"coverage check: {e}", file=sys.stderr)
        return 1
    print(f"coverage.xml: committed {old:.1f}%, fresh run {new:.1f}%")
    if abs(old - new) > TOLERANCE:
        print(f"stale: differs by more than {TOLERANCE:g} point; refresh with\n"
              "  python -m pytest -q --cov=app --cov-report=xml:coverage.xml", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: check_coverage.py committed.xml fresh.xml")
    sys.exit(main(sys.argv[1], sys.argv[2]))
