# Thinkster Elevate – Worksheet Automation

A production-ready Selenium automation framework that logs into **Thinkster Elevate**, navigates the learning dashboard, and opens any worksheet using only its **Worksheet ID**.

---

## Requirements

- Python 3.12 or later
- Google Chrome (latest)
- Internet access

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure credentials

Open `config.py` and fill in your Thinkster Elevate login credentials:

```python
EMAIL    = "your.email@example.com"
PASSWORD = "your_password"
```

> ⚠️ **Never commit `config.py` to version control.**

### 3. Run the automation

To extract worksheet question screenshots sequentially under a topic, run:
```bash
python main.py
```
When prompted, enter the target Topic Name (e.g. `Complex Numbers`).

To automatically fill in answers and check correctness for a specific worksheet, first make sure the answers are defined in `worksheet_answers.json` under the Worksheet ID key (e.g. `AQCMXAL214`), then run:
```bash
python main_answering.py
```
When prompted, enter the Topic Name and the target Worksheet ID.

---

## Project Structure

```
project/
├── main.py               # Question Screenshots Extraction Tool – gets question screens
├── main_answering.py     # Worksheet Answering Tool – inputs answers and checks correctness
├── answering.py          # Form filler and submit logic for math worksheets
├── topic_worksheet_finder.py # Topic navigation, expansion, and card search
├── config.py             # Credentials and settings
├── login.py              # Browser launch + login logic
├── dashboard.py          # Student selection + Start Learning
├── utils.py              # Shared Selenium helpers and automation orchestrators
├── logger.py             # Console + rotating file logger
├── requirements.txt
├── README.md
├── worksheet_answers.json # Pre-defined answers for target worksheets
└── logs/
    └── thinkster_automation.log
```

---

## Configuration Options (`config.py`)

| Setting            | Default               | Description                                  |
|--------------------|-----------------------|----------------------------------------------|
| `EMAIL`            | `<YOUR_EMAIL>`        | Thinkster Elevate login email                |
| `PASSWORD`         | `<YOUR_PASSWORD>`     | Thinkster Elevate login password             |
| `HEADLESS`         | `False`               | Set `True` to run without a visible browser  |
| `TARGET_STUDENT`   | `Thomas D`            | Name of the student to select                |
| `DEFAULT_WAIT`     | `15`                  | Default explicit wait timeout (seconds)      |
| `LONG_WAIT`        | `30`                  | Extended wait for slow page loads            |
| `MAX_RETRIES`      | `3`                   | Click/element retry attempts                 |
| `INDEX_FILE`       | `worksheet_index.json`| Path to the worksheet index cache            |

---

## Performance

| Scenario                        | Speed          |
|---------------------------------|----------------|
| First run (no index)            | Full scan – slower |
| Subsequent runs (index present) | Direct navigation – fast |
| Index invalid / ID not found    | Auto-rebuild + retry |

---

## Logging

- **Console**: Coloured, INFO level and above.
- **File**: `logs/thinkster_automation.log` – DEBUG level, rotated at 5 MB.

---

## Troubleshooting

| Problem                         | Solution                                                  |
|---------------------------------|-----------------------------------------------------------|
| `Login failed`                  | Verify EMAIL and PASSWORD in `config.py`                  |
| `Student not found`             | Check `TARGET_STUDENT` in `config.py`                     |
| `Worksheet ID not found`        | Delete `worksheet_index.json` to force a full rescan      |
| ChromeDriver version mismatch   | `webdriver-manager` handles this automatically            |
| Stale element errors            | Built-in retry logic handles these transparently          |

---

## Notes

- The `worksheet_index.json` is rebuilt automatically whenever a worksheet ID is not found or the stored position is invalid.
- Anti-detection measures are applied to reduce the chance of bot-detection by the site.
- All waits use Selenium **Explicit Waits** – `time.sleep()` is only used where DOM animation delays are unavoidable.
