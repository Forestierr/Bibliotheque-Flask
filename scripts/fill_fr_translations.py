"""
Regenerate clean FR .po from .pot, filling msgstr = msgid (source language).
Handles both single-line and multi-line msgid entries.
"""

import pathlib
import re

pot_path = pathlib.Path("project/translations/messages.pot")
fr_po_path = pathlib.Path("project/translations/fr/LC_MESSAGES/messages.po")

# Read the .pot template
content = pot_path.read_bytes().decode("utf-8-sig")  # handle BOM

# Fix header
content = content.replace(
    '"Content-Type: text/plain; charset=charset\\n"',
    '"Content-Type: text/plain; charset=UTF-8\\n"',
)
content = content.replace('"Language: \\n"', '"Language: fr\\n"')

# Remove fuzzy markers
content = content.replace("#, fuzzy\n", "")


def parse_po_string(raw: str) -> str:
    """
    Reconstruct the actual string value from a PO multi-line or single-line block.
    raw is everything after "msgid " up to the next directive.
    """
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
    return "".join(parts)


def build_po_string(value: str) -> str:
    """Serialize a string value back to a single-line PO-quoted string."""
    value = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{value}"'


# Pattern: captures the entire msgid block (one or more quoted lines),
# followed immediately by an empty msgstr line.
BLOCK_RE = re.compile(
    r'(msgid\s+(?:"(?:[^"\\]|\\.)*"\s*\n?)+)'  # msgid + quoted lines
    r'(msgstr\s+"")',  # empty msgstr
    re.MULTILINE,
)


def fill_msgstr(m: re.Match) -> str:
    msgid_block = m.group(1)

    # Extract raw content after "msgid "
    raw = msgid_block[len("msgid") :].strip()
    value = parse_po_string(raw)

    if not value:
        # Header entry — leave untouched
        return m.group(0)

    filled_msgstr = f"msgstr {build_po_string(value)}"
    return f"{msgid_block}{filled_msgstr}"


result = BLOCK_RE.sub(fill_msgstr, content)

# Write as plain UTF-8 with LF line endings
fr_po_path.write_text(result, encoding="utf-8", newline="\n")

lines = result.count("\n")
msgs = result.count("msgstr ")
empty = result.count('msgstr ""')
print(
    f"FR .po created: {lines} lines, {msgs} msgstr entries, {empty} still empty (header only)"
)
