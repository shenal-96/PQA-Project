# Power Quality Analysis (PQA) - Streamlit App

A locally-installable web app for analyzing power quality data from CSV files.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the App

```bash
streamlit run app.py
```

The app will open automatically at `http://localhost:8501`

---

## What You Can Do

1. **Upload CSV** - drag & drop your power quality recorder CSV file
2. **Configure Standards** - set voltage/frequency tolerances, recovery times, or use ISO 8528 presets
3. **Run Analysis** - detects load events, calculates compliance (Pass/Fail)
4. **View Results**:
   - Summary metrics (events detected, pass/fail counts)
   - Time-series plots (Voltage, Power, Current, Frequency, THD, PF)
   - Event snapshots (±5 second windows around each event)
   - Interactive compliance table
5. **Generate Report** - upload a Word `.docx` template with placeholders like `{{Avg_Voltage_LL}}` and it injects your plots/data

---

## Files

- `app.py` - Streamlit UI (main entry point)
- `analysis.py` - Core engine (event detection, compliance)
- `visualizations.py` - All plotting functions
- `report.py` - Word/PDF report generation
- `requirements.txt` - Dependencies

---

## Available Placeholders for Word Templates

**Graphs:** `{{Avg_Voltage_LL}}`, `{{Avg_kW}}`, `{{Avg_Current}}`, `{{Avg_Frequency}}`, `{{Avg_THD_F}}`, `{{Avg_PF}}`

**Table:** `{{Compliance_Table}}`

**Snapshots:** `{{Snapshot_1}}`, `{{Snapshot_2}}`, ...

**Metadata:** `{{Report_Title}}`, `{{Gen_SN}}`, `{{Site_Address}}`, `{{Custom_Field}}`, `{{Date}}`, `{{Start Time}}`, `{{End Time}}`

---

## Status

✅ **Code Complete** - All functionality from your Colab notebook is preserved:
- ISO 8528 standard presets
- L-N to L-L voltage detection (√3 scaling)
- Event grouping (within 5 seconds)
- Recovery time calculation
- Compliance Pass/Fail logic
- 6 metric plots
- Event snapshots (4 subplots each)
- Styled compliance table
- Word template injection
- PDF conversion (if LibreOffice installed)

❌ **GitHub Push** - Due to platform permission issues, code is committed locally but not pushed to GitHub yet. You can push manually when ready:

```bash
git push -u origin claude/plan-app-development-OQvmL
```

---

## Next Steps

1. **Test the app locally** with your CSV data
2. **Create a Word template** with the placeholders above
3. **Generate your report** - app will inject all plots and data
4. **Push to GitHub** when you're ready (manual `git push` command above)

---

Built with Streamlit, pandas, matplotlib, python-docx
