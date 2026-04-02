#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Parse a FIDO raw log into:
1. A chronological text report of sample seal/clamp sequences
2. A summary CSV of sample outcomes
3. A CSV of all vacconfirm vacuum values with sample context

Created for parsing FIDO sample events from the Montana log.

What this script does
---------------------
- Reads the raw log file line by line
- Ignores log lines before a user-defined cutoff date
- Splits the filtered log into blocks starting at each fido.sample(...) call
- Classifies each sample block as:
    * success
    * failure: Closed Clamp failed to reach vacuum
    * failure: Clamp failed to hold vacuum
- Keeps only the selected lines of interest for the text report
- Extracts all "vacconfirm vacuum value X, setpoint Y" lines into a CSV

Outputs
-------
1. output_txt
   Human-readable chronological report of parsed sample events

2. output_csv
   One row per parsed event:
   timestamp, sample_label, status, reason

3. output_vac_csv
   One row per vacconfirm line:
   sample_info, time, vacuum_value, setpoint

Notes
-----
- This script works from the RAW LOG, not the previously parsed text file.
- Matching for some sampling-related lines is intentionally broad so that
  slight changes in wording or values do not cause the lines to be missed.
"""

import re
import csv
from pathlib import Path
from datetime import datetime


# =============================================================================
# USER INPUTS
# =============================================================================

# Path to the raw FIDO log file
log_file = Path("/Users/kyamahara/Desktop/FIDO6-Log/mbari_readinet_FIDO-006_Montana.log")

# Output text report with chronological sample event sequences
output_txt = Path("/Users/kyamahara/Desktop/FIDO6-Log/mbari_readinet_FIDO-006_Montana_parse.txt")

# Output CSV summarizing one row per event
output_csv = Path("/Users/kyamahara/Desktop/FIDO6-Log/mbari_readinet_FIDO-006_Montana_summary.csv")

# Output CSV listing every vacconfirm line with its sample context
output_vac_csv = Path("/Users/kyamahara/Desktop/FIDO6-Log/mbari_readinet_FIDO-006_Montana_vacconfirm_values.csv")

# Ignore any lines before this date/time
cutoff = datetime(2026, 3, 21)


# =============================================================================
# REGEX PATTERNS
# =============================================================================

# Matches a timestamp at the beginning of a raw log line, e.g.:
# 2026-03-26T21:02:54|INFO|...
timestamp_re = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")

# Matches the start of a sample event block
sample_start_re = re.compile(r"\|\|fido\.sample\(")

# Extracts the sample label from a fido.sample(...) line, e.g.:
# fido.sample('FIDO-006, 20260326, 210021',0.1, 1.2, "sample-only")
sample_label_re = re.compile(r"fido\.sample\('([^']+)'")

# Extracts vacuum value and setpoint from lines like:
# DEBUG:vacconfirm vacuum value 36, setpoint 200
vacconfirm_re = re.compile(
    r"DEBUG:vacconfirm vacuum value\s+(-?\d+),\s+setpoint\s+(-?\d+)"
)


# =============================================================================
# CLASSIFICATION MARKERS
# =============================================================================

# Any of these lines indicate a successful seal event
success_markers = [
    "DEBUG:Seal confirmed",
    "DEBUG:Seal confirmed!"
]

# Any of these lines indicate a target failure event
failure_markers = [
    "ERROR:checkSeal, Closed Clamp failed to reach vacuum",
    "ERROR:checkSeal, Clamp failed to hold vacuum"
]


# =============================================================================
# LINE FILTERS FOR THE TEXT REPORT
# =============================================================================

# These are the main line fragments we want to preserve in the text report.
# These are intentionally somewhat broad for robustness.
context_patterns = [
    "Starting run with timeout=",
    "fido.sample(",
    "DEBUG:Waiting to see if clamp holds vacuum",
    "DEBUG:Clamp at CLOSE",
    "INFO:Puck ",
    "DEBUG:Seal confirmed",
    "DEBUG:Seal confirmed!",
    "DEBUG:vacconfirm vacuum value",
    "ERROR:checkSeal, Closed Clamp failed to reach vacuum",
    "ERROR:checkSeal, Clamp failed to hold vacuum",

    # Broadened sampling-event matches so exact values do not need to match
    "INFO:Pump started, setting pump pressure",
    "INFO:Waiting for ",
    "DEBUG:Setting sample pressure to ",
    "INFO:Sampling complete",
]

# These are additional lines that are often useful to keep for context
optional_context_patterns = [
    "INFO:**************** Start sample process",
    "DEBUG:Closing clamp for intake purge",
    "DEBUG:Confirming closed clamp seal",
    "DEBUG:Clamp already at Close",
    "DEBUG:atClose:",
    "INFO:Closing clamp and verifying seal",
    "INFO:Closing clamp and verifying seal for priming",
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def parse_timestamp(line):
    """
    Extract and parse the timestamp at the start of a log line.

    Parameters
    ----------
    line : str
        A raw log line.

    Returns
    -------
    datetime or None
        Parsed datetime if found, otherwise None.
    """
    match = timestamp_re.match(line)
    if not match:
        return None
    return datetime.fromisoformat(match.group(1))


def keep_line(line):
    """
    Decide whether a line should be retained in the text report.

    Parameters
    ----------
    line : str
        A log line.

    Returns
    -------
    bool
        True if the line contains one of the desired context fragments.
    """
    return any(pattern in line for pattern in (context_patterns + optional_context_patterns))


def get_sample_label(line):
    """
    Extract the sample label from a fido.sample(...) line.

    Parameters
    ----------
    line : str
        A line expected to contain fido.sample(...)

    Returns
    -------
    str
        Sample label if found, otherwise an empty string.
    """
    match = sample_label_re.search(line)
    return match.group(1) if match else ""


def classify_sequence(lines):
    """
    Classify a retained set of lines for one sample event.

    Parameters
    ----------
    lines : list[str]
        Selected lines kept from a sample block.

    Returns
    -------
    tuple[str, str]
        (status, reason)
        status is one of:
            - 'success'
            - 'failure'
            - 'unknown'
        reason explains the classification.
    """
    text = "\n".join(lines)

    if "ERROR:checkSeal, Closed Clamp failed to reach vacuum" in text:
        return "failure", "Closed Clamp failed to reach vacuum"

    if "ERROR:checkSeal, Clamp failed to hold vacuum" in text:
        return "failure", "Clamp failed to hold vacuum"

    if any(marker in text for marker in success_markers):
        return "success", "Seal confirmed"

    return "unknown", "No terminal seal/clamp marker found"


# =============================================================================
# READ RAW LOG
# =============================================================================

with log_file.open("r", encoding="utf-8", errors="replace") as f:
    raw_lines = [line.rstrip("\n") for line in f]


# =============================================================================
# FILTER TO LINES ON OR AFTER THE CUTOFF DATE
# =============================================================================

filtered_lines = []

for line in raw_lines:
    ts = parse_timestamp(line)

    # Skip anything that does not begin with a valid timestamp
    if ts is None:
        continue

    # Keep only lines on/after the cutoff
    if ts >= cutoff:
        filtered_lines.append(line)


# =============================================================================
# SPLIT INTO SAMPLE BLOCKS
# =============================================================================

# Each block starts at a fido.sample(...) line and continues until the next one.
sample_blocks = []
current_block = None

for line in filtered_lines:
    if sample_start_re.search(line):
        # Save the previous block before starting a new one
        if current_block is not None:
            sample_blocks.append(current_block)
        current_block = [line]
    else:
        if current_block is not None:
            current_block.append(line)

# Save the final block if one exists
if current_block is not None:
    sample_blocks.append(current_block)


# =============================================================================
# PARSE EVENTS AND VACCONFIRM ROWS
# =============================================================================

events = []
vac_rows = []

for block in sample_blocks:
    # The first line of the block should be the sample start line
    sample_label = get_sample_label(block[0])
    event_ts = parse_timestamp(block[0])

    # Keep only lines of interest for the text report
    kept_lines = [line for line in block if keep_line(line)]

    # If nothing relevant was found, skip this block
    if not kept_lines:
        continue

    # Determine whether this sample sequence was a success or target failure
    status, reason = classify_sequence(kept_lines)

    # Only keep successful or failure events
    if status not in ("success", "failure"):
        continue

    # Store the event summary for the text report and summary CSV
    events.append({
        "timestamp": event_ts,
        "sample_label": sample_label,
        "status": status,
        "reason": reason,
        "lines": kept_lines
    })

    # Extract all vacconfirm rows from the full sample block
    for line in block:
        vac_match = vacconfirm_re.search(line)
        line_ts = parse_timestamp(line)

        if vac_match and line_ts is not None:
            vac_rows.append({
                "sample_info": sample_label,
                "time": line_ts.isoformat(sep=" "),
                "vacuum_value": int(vac_match.group(1)),
                "setpoint": int(vac_match.group(2))
            })


# =============================================================================
# SORT OUTPUTS
# =============================================================================

# Sort events chronologically by sample event start
events.sort(key=lambda x: x["timestamp"])

# Sort vacconfirm rows chronologically
vac_rows.sort(key=lambda x: x["time"])


# =============================================================================
# WRITE CHRONOLOGICAL TEXT REPORT
# =============================================================================

with output_txt.open("w", encoding="utf-8") as out:
    out.write("FIDO-006 MONTANA LOG PARSE\n")
    out.write("Scope:\n")
    out.write("  - Includes sample sequences only\n")
    out.write("  - Chronological order\n")
    out.write(f"  - Filtered to log lines on or after {cutoff.strftime('%Y-%m-%d')}\n")
    out.write("  - Includes both successful seal sequences and target clamp/seal failures\n\n")

    success_count = sum(event["status"] == "success" for event in events)
    failure_count = sum(event["status"] == "failure" for event in events)

    closed_fail_count = sum(
        event["reason"] == "Closed Clamp failed to reach vacuum"
        for event in events
    )
    hold_fail_count = sum(
        event["reason"] == "Clamp failed to hold vacuum"
        for event in events
    )

    out.write("Included sequence types:\n")
    out.write(f"  Successful sample sequences: {success_count}\n")
    out.write(f"  Failure sample sequences: {failure_count}\n")
    out.write(f"    Closed Clamp failed to reach vacuum: {closed_fail_count}\n")
    out.write(f"    Clamp failed to hold vacuum: {hold_fail_count}\n")
    out.write(f"  Total sequences: {len(events)}\n\n")

    out.write("Selected lines retained within each sequence:\n")
    for pattern in context_patterns:
        out.write(f"  - {pattern}\n")
    for pattern in optional_context_patterns:
        out.write(f"  - {pattern}\n")
    out.write("\n")

    for i, event in enumerate(events, start=1):
        out.write("=" * 90 + "\n")
        out.write(
            f"  Event {i} | {event['status'].upper()} | "
            f"{event['timestamp'].isoformat()} | {event['sample_label']}\n"
        )
        out.write("=" * 90 + "\n")

        if event["status"] == "success":
            out.write("  Classification: Successful seal/sample sequence\n")
        else:
            out.write(f"  Classification: {event['reason']}\n")

        for line in event["lines"]:
            out.write(f"  {line}\n")

        out.write("\n")


# =============================================================================
# WRITE EVENT SUMMARY CSV
# =============================================================================

with output_csv.open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "sample_label", "status", "reason"])

    for event in events:
        writer.writerow([
            event["timestamp"].isoformat(sep=" "),
            event["sample_label"],
            event["status"],
            event["reason"]
        ])


# =============================================================================
# WRITE VACCONFIRM CSV
# =============================================================================

with output_vac_csv.open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["sample_info", "time", "vacuum_value", "setpoint"])

    for row in vac_rows:
        writer.writerow([
            row["sample_info"],
            row["time"],
            row["vacuum_value"],
            row["setpoint"]
        ])


# =============================================================================
# FINAL CONSOLE OUTPUT
# =============================================================================

print(f"Wrote text report to: {output_txt}")
print(f"Wrote summary CSV to: {output_csv}")
print(f"Wrote vacconfirm CSV to: {output_vac_csv}")
print(f"Parsed events: {len(events)}")
print(f"Vacconfirm rows: {len(vac_rows)}")