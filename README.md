# FIDO Tools

Tools (scripts) for parsing FIDO data and logs.

---

## Scripts

### FIDOvacparsing.py

Parser for FIDO raw deployment logs. Extracts sample seal/clamp sequences, classifies outcomes, and exports vacuum confirmation data.

#### Overview

Reads a raw FIDO log file, filters to a user-defined date window, splits into per-sample blocks anchored on `fido.sample()` calls, and classifies each block as a success or failure. Produces three output files.

#### Outputs

| File | Description |
|------|-------------|
| `*_parse.txt` | Chronological text report of all sample events with selected log lines |
| `*_summary.csv` | One row per event: timestamp, sample label, status, reason |
| `*_vacconfirm_values.csv` | Every `vacconfirm` line with vacuum value, setpoint, and sample context |

#### Event Classification

Each sample block is classified by scanning retained lines for terminal markers:

- **success** — `DEBUG:Seal confirmed` or `DEBUG:Seal confirmed!`
- **failure: Closed Clamp failed to reach vacuum** — clamp never achieved target vacuum
- **failure: Clamp failed to hold vacuum** — vacuum achieved but not maintained
- **unknown** — no terminal marker found; excluded from outputs

#### Configuration

All user inputs are at the top of the script under `USER INPUTS`:
```python
log_file    # Path to raw FIDO log
output_txt  # Text report output path
output_csv  # Summary CSV output path
output_vac_csv  # Vacconfirm CSV output path
cutoff      # datetime — ignore lines before this date
```

#### Requirements

Python 3.6+ standard library only — no external dependencies (`re`, `csv`, `pathlib`, `datetime`).

#### Usage
```bash
python FIDOvacparsing.py
```

Update the paths and cutoff date in `USER INPUTS` before running. Output paths will be created or overwritten.

#### Notes

- Operates on the **raw log**, not a previously parsed text file
- Lines without a valid leading timestamp are skipped
- Blocks with no classifiable terminal marker are excluded from all outputs
- Line matching patterns are intentionally broad to accommodate minor log format variation across firmware versions
