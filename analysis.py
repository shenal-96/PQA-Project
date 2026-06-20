"""Backward-compatibility shim — DO NOT add logic here.

The analysis engine now lives in ``core/analysis.py`` (the canonical location
for the new desktop/web app). This shim simply re-exports it so the legacy
Streamlit app (``app.py``) and any existing ``import analysis`` keep working
**unchanged** during the migration.

Once the Streamlit app is retired, delete this file and import from
``core.analysis`` directly.
"""

from core.analysis import *  # noqa: F401,F403

# Explicit re-exports for the legacy app's `from analysis import ...` line.
from core.analysis import (  # noqa: F401
    AnalysisConfig,
    robust_to_datetime,
    detect_logger_format,
    load_miro_csv,
    load_and_prepare_csv,
    validate_csv_format,
    load_winscope_xls,
    calculate_recovery_time,
    calculate_exit_time,
    calculate_forward_exit_time,
    check_compliance,
    perform_analysis,
)
