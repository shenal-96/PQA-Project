"""
settings_reference.py — Curated settings/parameter knowledge base for the
generator control + excitation equipment used in backup-power compliance work.

Purpose
-------
Give engineers a fast, searchable reference for the settings they actually
change in the field, with plain-English descriptions of:
  * what the setting does,
  * the control philosophy behind it (why it exists / how the controller uses it),
  * how changing it affects gen-set / alternator performance.

This module is UI-free (no Streamlit imports) — it only exposes data and a
search helper, mirroring the project convention for analysis.py /
visualizations.py. The app.py "Settings Reference" tab renders it.

IMPORTANT — provenance / accuracy
---------------------------------
This is a *curated starting reference* built from the public ComAp InteliGen/
InteliSys NT global guides, the InteliConfig configuration tool, and the
Leroy-Somer (Nidec) D550 digital AVR installation & EasyReg Advanced
documentation, supplemented by domain knowledge. Web fetching of the source
PDFs was blocked at build time, so **ranges, defaults and exact setpoint names
must be verified against the manuals once they are uploaded** (drop them in
`uploads/manuals/`). Treat numeric ranges/defaults as typical/indicative until
confirmed. The structure is designed so entries can be corrected and expanded
in place.

Data model
----------
SETTINGS_DATA: dict[device_name, device_dict]
    device_dict = {
        "summary": str,            # one-line description of the device
        "source": str,             # which manual(s) this came from
        "verified": bool,          # True once checked against the real PDF
        "groups": { group_name: [ setting, ... ] }
    }
    setting = {
        "name":        str,        # setpoint / parameter name as shown on device
        "units":       str,        # "" if dimensionless
        "range":       str,        # typical adjustable range (verify)
        "default":     str,        # typical/factory default (verify)
        "description": str,        # what it does
        "philosophy":  str,        # control philosophy — why it exists / how used
        "performance": str,        # effect on performance if increased/decreased
    }
"""

from __future__ import annotations


def _s(name, units, rng, default, description, philosophy, performance):
    """Compact constructor for a setting dict."""
    return {
        "name": name,
        "units": units,
        "range": rng,
        "default": default,
        "description": description,
        "philosophy": philosophy,
        "performance": performance,
    }


# =====================================================================
# ComAp InteliGen / InteliSys NT  — gen-set controller
# =====================================================================
_COMAP = {
    "summary": "Gen-set controller (engine + generator control, protections, "
               "synchronising, load/VAr sharing and power management).",
    "source": "ComAp InteliGen NT / InteliSys NT Global Guide + InteliConfig "
              "configuration tool (verify against uploaded PDF).",
    "verified": False,
    "groups": {
        "Basic Settings": [
            _s("Nominal Power", "kW", "1 – 5000", "site rated kW",
               "Rated real power of the gen-set. Reference (100 %) for all "
               "power-based protections and load control.",
               "Everything expressed in '%' of power (overload, load ramps, "
               "base load, peak shaving) is scaled to this value, so it must "
               "match the actual set rating.",
               "Set too high and overload protection trips late / load ramps "
               "push the engine past its real rating; too low and the set "
               "trips or de-rates before reaching genuine capacity."),
            _s("Nominal Current", "A", "1 – 5000", "rated stator current",
               "Rated generator current — reference for overcurrent / IDMT "
               "protections.",
               "Current protections (overcurrent, short circuit, unbalance) "
               "are scaled to this value.",
               "Mis-set value mis-scales every current protection — nuisance "
               "trips if low, missed faults if high."),
            _s("CT Ratio (prim/sec)", "A/A", "e.g. 5–10000 / 5 or /1", "per CT",
               "Primary-to-secondary ratio of the generator measuring current "
               "transformers.",
               "The controller scales raw CT secondary current up to real "
               "primary amps using this ratio; all current readings depend on it.",
               "Wrong ratio scales every current reading and power calc — kW/kVAr "
               "and protections all read wrong by the ratio error."),
            _s("PT Ratio", "V/V", "1.0 – 500", "1.0 (direct) / site VT ratio",
               "Voltage-transformer ratio for MV/HV measurement. 1.0 when the "
               "controller measures generator voltage directly (LV).",
               "Scales measured voltage to real busbar voltage on systems with "
               "metering VTs (e.g. 11 kV sets).",
               "Wrong ratio mis-scales voltage, frequency-independent V "
               "protections, and PF/kVAr."),
            _s("Nominal Voltage (Ph-Ph)", "V", "100 – 30000", "415 / 690 / 11000",
               "Rated line-to-line generator voltage. Reference for under/over "
               "voltage protection and the AVR voltage setpoint.",
               "100 % reference for voltage protection windows; aligns with the "
               "PQA tool's nominal-voltage compliance check.",
               "Defines where over/under-voltage windows sit; mis-set shifts "
               "the whole compliance window."),
            _s("Nominal Frequency", "Hz", "50 / 60", "50",
               "Rated system frequency. Reference for under/over frequency and "
               "the speed governor setpoint.",
               "Sets the governor speed target and the frequency protection "
               "centre; ties to ISO 8528 recovery bands.",
               "Mismatch with the engine governor causes a permanent frequency "
               "offset and failed recovery checks."),
            _s("Gear Teeth", "-", "10 – 500", "engine flywheel count",
               "Number of flywheel ring-gear teeth seen by the magnetic pickup "
               "(MPU) for RPM measurement.",
               "Controller derives RPM from pickup pulse rate ÷ gear teeth; "
               "underpins all speed-based logic (crank, idle, overspeed).",
               "Wrong count gives proportionally wrong RPM — overspeed trips or "
               "fails to detect crank/run states."),
            _s("Nominal RPM", "RPM", "750 – 3600", "1500 (50 Hz) / 1800 (60 Hz)",
               "Rated engine speed reference.",
               "Reference (100 %) for speed-percentage setpoints such as "
               "Starting RPM and overspeed.",
               "Defines the speed band; mis-set skews crank-disconnect and "
               "overspeed thresholds."),
        ],
        "Engine / Starting": [
            _s("Starting RPM", "%", "5 – 50", "25",
               "Speed (as % of nominal) above which the engine is considered "
               "'running' and the starter is disengaged.",
               "Crank-disconnect logic — stops cranking once the engine fires "
               "and accelerates on its own.",
               "Too low → starter stays engaged into a firing engine (gear "
               "damage); too high → starter disengages before the engine can "
               "sustain itself (stall / repeated cranks)."),
            _s("Prestart Time", "s", "0 – 600", "2",
               "Pre-lubrication / glow-plug / fuel-prime time before cranking.",
               "Lets oil pressure build or glow plugs heat before the starter "
               "engages, protecting bearings and aiding cold starts.",
               "Too short stresses a dry engine on cold starts; too long delays "
               "availability in AMF / black-start scenarios."),
            _s("MaxCrank Time", "s", "1 – 60", "8",
               "Maximum duration of a single crank attempt.",
               "Bounds starter motor energisation to avoid burning it out if "
               "the engine will not fire.",
               "Too short may abort before a sluggish cold engine fires; too "
               "long overheats the starter."),
            _s("CrankFail Pause", "s", "1 – 60", "8",
               "Rest time between failed crank attempts.",
               "Lets the starter motor and battery recover between attempts.",
               "Too short overheats/over-drains the starter and battery; too "
               "long delays a successful start sequence."),
            _s("Crank Attempts", "-", "1 – 10", "3",
               "Number of crank attempts before declaring a start failure.",
               "Balances persistence against protecting the starter/battery and "
               "raising a 'Start Fail' alarm.",
               "More attempts improve start reliability on marginal engines but "
               "risk flooding/draining; fewer give up quickly."),
            _s("Idle Time", "s", "0 – 600", "10",
               "Low-speed warm-up period after start before ramping to nominal "
               "(diesels with idle control).",
               "Warms oil and components at low load to reduce wear before "
               "accepting load.",
               "Too short loads a cold engine (wear/smoke); too long delays "
               "readiness."),
            _s("Min/Max Stab Time", "s", "0 – 300", "Min 1 / Max 30",
               "Minimum and maximum time to wait for voltage & frequency to "
               "stabilise after reaching nominal speed before closing the "
               "breaker / allowing synchronising.",
               "Ensures the set is electrically stable before it is connected; "
               "Max acts as a timeout that raises an alarm if stability is "
               "never reached.",
               "Min too short risks closing onto an unstable set; Max too short "
               "nuisance-alarms a slow-stabilising set."),
            _s("Cooling Speed", "-", "IDLE / NOMINAL", "NOMINAL",
               "Engine speed used during the unloaded cool-down period.",
               "Lets turbo/temperatures settle before shutdown.",
               "Cooling at idle saves fuel but cools turbos slower; nominal "
               "cools faster but uses more fuel."),
            _s("Cooling Time", "s", "0 – 3600", "60",
               "Unloaded run time after the breaker opens, before the engine "
               "stops.",
               "Allows turbocharger and coolant temperatures to fall gradually, "
               "extending turbo life.",
               "Too short risks turbo coking / thermal shock; too long wastes "
               "fuel and run-hours."),
        ],
        "Generator Protection": [
            _s("Overload (BOC/Wrn)", "%", "0 – 200", "110",
               "Real-power overload threshold (% of Nominal Power) with a time "
               "delay.",
               "Protects the engine from sustained loading beyond its rating; "
               "usually a warning then a breaker-open/trip level.",
               "Lower = earlier protection but more nuisance trips on transient "
               "peaks; higher = risk of engine overload/overheat."),
            _s("Overcurrent (IDMT)", "%", "100 – 500", "Pickup ~110, time-graded",
               "Inverse-time generator overcurrent protection scaled to Nominal "
               "Current.",
               "Time-current curve protects windings while allowing brief inrush "
               "/ motor-start surges.",
               "Tight settings trip on legitimate inrush; loose settings allow "
               "thermal damage during sustained faults."),
            _s("Short Circuit", "%", "100 – 1000", "set-dependent, short delay",
               "Instantaneous high-current trip.",
               "Fast clearing of bolted faults to limit damage.",
               "Too sensitive trips on inrush; too high delays fault clearing."),
            _s("Voltage Unbalance", "%", "0 – 50", "10",
               "Maximum allowed phase voltage imbalance, with delay.",
               "Detects lost-phase / unbalanced load conditions that overheat "
               "the alternator.",
               "Lower catches imbalance sooner but nuisance-trips on naturally "
               "unbalanced single-phase loads."),
            _s("Gen >V / Gen <V", "%", "0 – 150", ">115 / <85",
               "Generator over/under voltage trip levels (% of nominal) with "
               "delays.",
               "Disconnects the set when AVR/excitation faults push voltage out "
               "of a safe window.",
               "Narrow window improves load protection but risks tripping during "
               "normal transient dips/rises; wide window can let damaging "
               "voltage reach the load."),
            _s("Gen >f / Gen <f", "Hz", "±0 – 10 of nom", ">52 / <48",
               "Generator over/under frequency trip levels with delays.",
               "Protects against governor runaway (overspeed) and prolonged "
               "underspeed/overload.",
               "Tight bands fail ISO recovery transients; loose bands allow "
               "off-frequency operation of sensitive loads."),
            _s("Reverse Power", "%", "-50 – 0", "-5 to -10",
               "Reverse (motoring) power trip when the alternator draws power "
               "from the bus.",
               "Protects the engine when, in parallel, it loses prime mover "
               "power and is motored by other sets.",
               "Too sensitive trips on small reverse swings during load steps; "
               "too loose allows prolonged motoring (engine damage)."),
        ],
        "Speed / Load Control (Sync)": [
            _s("Speed Gov Bias / Char", "-", "RELAY / PWM / ANALOG", "analog ±10 V",
               "Output type/characteristic driving the engine speed governor.",
               "Defines how the controller biases engine speed for "
               "synchronising and load control.",
               "Wrong type/polarity makes the set chase frequency the wrong way "
               "— failure to sync / runaway."),
            _s("Freq Gain", "%", "0 – 200", "site-tuned (e.g. 40)",
               "Proportional gain of the frequency/speed control loop.",
               "Determines how aggressively the controller corrects frequency "
               "error toward nominal before/while synchronising.",
               "Too high → frequency hunting/oscillation; too low → slow "
               "frequency recovery, longer ISO recovery times."),
            _s("Freq Int", "%", "0 – 200", "site-tuned",
               "Integral term of the frequency loop.",
               "Removes steady-state frequency offset so the set settles exactly "
               "on nominal.",
               "Too high → slow oscillation / overshoot; too low → lingering "
               "frequency error."),
            _s("Angle Gain", "%", "0 – 200", "site-tuned",
               "Phase-angle matching gain during synchronising.",
               "Pulls generator phase angle into the synchroniser window before "
               "breaker close.",
               "Too high → angle hunting and missed close windows; too low → "
               "very slow synchronising."),
            _s("Load Ramp", "s", "1 – 600", "10 – 60",
               "Time to ramp load up after breaker close (and down before open).",
               "Soft loading/unloading to avoid frequency dips and mechanical "
               "shock on the engine.",
               "Fast ramp causes large frequency/voltage transients (ISO "
               "recovery failures); slow ramp delays reaching base/peak load."),
            _s("LS Gain / LS Int", "%", "0 – 200", "site-tuned",
               "Load-sharing proportional / integral gains in parallel "
               "operation.",
               "Make multiple sets share real power proportionally to their "
               "rating on a common bus.",
               "Too high → power hunting between sets; too low → uneven sharing / "
               "slow balancing."),
        ],
        "Voltage / PF Control (AVR interface)": [
            _s("Voltage Gain / Int", "%", "0 – 200", "site-tuned",
               "Gains of the controller's voltage-bias loop to the AVR (when the "
               "controller trims the AVR setpoint).",
               "Lets the gen-set controller adjust generator voltage for "
               "matching and VAr sharing via the AVR's external bias input.",
               "Too high → voltage hunting; too low → slow voltage matching "
               "before paralleling."),
            _s("PF Gain / PF Int", "%", "0 – 200", "site-tuned",
               "Power-factor control loop gains when paralleled to the mains "
               "(import/export PF regulation).",
               "Holds a target PF / kVAr when running in parallel with the grid.",
               "Too high → reactive-power hunting; too low → slow PF correction, "
               "poor reactive sharing."),
            _s("Base PF / VAr", "-", "0.0 – 1.0 / kVAr", "0.8 – 1.0",
               "Target power factor (or kVAr) setpoint in mains-parallel mode.",
               "Defines the reactive operating point when exporting/importing "
               "with the grid.",
               "Lower PF target raises reactive current and heating; near-unity "
               "minimises reactive loading."),
        ],
        "AMF / Mains (where fitted)": [
            _s("Mains >V / <V", "%", "0 – 150", ">110 / <85",
               "Mains over/under voltage detection for auto mains-failure start.",
               "Decides when utility supply is unhealthy and the gen-set should "
               "start and take the load.",
               "Tight bands cause frequent unnecessary gen starts; loose bands "
               "delay backup during a real dip."),
            _s("Mains >f / <f", "Hz", "±0 – 10 of nom", ">52 / <48",
               "Mains over/under frequency detection for AMF.",
               "Frequency half of the mains-health decision.",
               "As above — trade nuisance starts against slow backup response."),
            _s("Return Delay", "s", "0 – 3600", "60 – 600",
               "Time mains must stay healthy before transferring back and "
               "stopping the set.",
               "Avoids ping-ponging on an unstable utility supply.",
               "Short → repeated transfers on flickering mains; long → runs the "
               "set (and burns fuel) after mains recovers."),
        ],
    },
}


# =====================================================================
# Leroy-Somer (Nidec) D550 — digital AVR / excitation
# =====================================================================
_D550 = {
    "summary": "Digital automatic voltage regulator (excitation control) — "
               "voltage / PF / kVAr / manual field regulation with PID, limits "
               "and protections; 7A continuous excitation (15A SCC) with USB/CAN "
               "configuration via EasyReg Advanced.",
    "source": "Leroy-Somer D550 Installation & Maintenance manual "
              "(5744 en - 2021.02 / c, ref. S.A.R.L. Moteurs Leroy-Somer). "
              "Configuration via EasyReg Advanced software.",
    "verified": True,
    "groups": {
        "Regulation Modes": [
            _s("Voltage Regulation (AVR)", "-", "on/off", "default mode",
               "Primary mode: closed-loop control of generator output voltage at "
               "setpoint by modulating field excitation.",
               "Core AVR function — measures stator voltage vs reference and "
               "drives the PID to adjust exciter field. Baseline for all other modes.",
               "Single regulation mode active at any time; bumpless mode switching "
               "when conditions change (e.g., load → paralleling)."),
            _s("Voltage Regulation + Quadrature Droop", "-", "on/off + droop %",
               "droop 3–5 %",
               "Voltage mode with reactive droop — reduces voltage setpoint "
               "proportional to reactive (lagging) current.",
               "For parallel generator operation: makes multiple machines share "
               "reactive load stably without fast communication. Each machine "
               "naturally backs off voltage as it carries more VAr.",
               "More droop → better VAr sharing but lower voltage with reactive "
               "load; zero droop → VAr hunting."),
            _s("Voltage Regulation + Cross-Current Compensation", "-",
               "on/off + gain", "off (requires CTs)",
               "Voltage mode with interconnected CT feedback — senses reactive "
               "current on adjacent phase and adjusts setpoint.",
               "Alternative to droop for tightly-coupled sets: achieves flat "
               "voltage with good VAr sharing via direct current feedback.",
               "Requires correct CT wiring (phase V standard). Mis-wired or "
               "over-gained → reactive hunting / instability."),
            _s("Voltage Regulation + Load Compensation", "-", "on/off", "off",
               "Voltage mode with load-current feed-forward — anticipates voltage "
               "dip from stator current.",
               "Faster voltage response to load changes by predicting the IV "
               "voltage drop before it happens.",
               "Improves transient response; rarely used in modern generators "
               "(PID already handles it)."),
            _s("Voltage Matching (U=U)", "-", "on/off + tolerance %", "on",
               "Holds generator voltage = grid/bus voltage before synchronizing "
               "(breaker close).",
               "Minimises voltage difference across the closing breaker to avoid "
               "reactive inrush current surge and mechanical/electrical shock. "
               "Typical tolerance: ±3–5% of nominal.",
               "Without it, close-on-mismatch → high current spike, torque shock, "
               "and breaker/mechanism stress. Automatic mode-switch after close "
               "to PF/kVAr regulation."),
            _s("Generator Power Factor (PF) Regulation", "-", "target 0.6–1.0",
               "0.8 leading (typical)",
               "Closed-loop regulation of generator reactive output to hold a "
               "target PF when paralleled with mains.",
               "In grid-coupled operation, the bus voltage is stiff, so the AVR "
               "instead regulates reactive current (and thus PF) to a setpoint. "
               "Typical: 0.8–0.95 leading (absorbing reactive from grid).",
               "Lower PF → more reactive current & field heating; must be "
               "disabled in standalone mode (would cause voltage drift)."),
            _s("Generator kVAr Regulation", "kVAr", "±rated capability", "0",
               "Closed-loop regulation of generator reactive power output to a "
               "kVAr setpoint when paralleled with mains.",
               "Alternative to PF mode for grid codes specifying reactive power "
               "directly. Useful for voltage support and dynamic stability "
               "requirements (LVRT, FRT).",
               "Sets reactive loading directly; affects alternator heating and "
               "grid interaction. Sign determines lead/lag."),
            _s("Grid Point Power Factor Regulation", "-", "target 0.6–1.0",
               "grid-code-dependent",
               "Regulates reactive power at the grid connection point (not just "
               "at the alternator) using grid voltage measurement feedback.",
               "Used in grid-code scenarios (e.g., wind, solar) where reactive "
               "support at the point of interconnection is required.",
               "Requires grid voltage measurement wiring and grid-code option "
               "module."),
            _s("Field Current (Manual / Excitation) Mode", "A",
               "0 – 7 (continuous) / 15 (SCC)", "—",
               "Open-loop direct field current control — user sets desired field "
               "amp directly.",
               "Fallback mode on sensing loss (safety); commissioning/diagnostics "
               "mode. No closed-loop voltage control — voltage follows load & "
               "alternator impedance.",
               "Used only for troubleshooting or controlled manual operation. "
               "Prolonged use without load monitoring risks over-excitation."),
        ],
        "PID Tuning": [
            _s("Proportional Gain (P)", "-", "0 – 100 (% / scaled)", "site-tuned",
               "Immediate corrective action proportional to voltage error "
               "(measurement - setpoint).",
               "Sets loop stiffness: how hard the AVR reacts to a deviation "
               "right now. P alone cannot eliminate steady-state error.",
               "Higher P → faster step response but risk of overshoot & "
               "oscillation; lower P → sluggish, larger voltage dips on load "
               "acceptance."),
            _s("Integral Gain (I)", "-", "0 – 100 (% / scaled)", "site-tuned",
               "Cumulative corrective action removing steady-state voltage error "
               "over time.",
               "Guarantees voltage settles exactly on setpoint, not persistently "
               "offset. I alone is slow (lag in step response).",
               "Higher I → faster offset removal but slow oscillation/overshoot; "
               "lower I → persistent voltage offset after transient."),
            _s("Derivative Gain (D)", "-", "0 – 100 (% / scaled)", "site-tuned",
               "Damping action proportional to rate of change of voltage error "
               "(dV/dt).",
               "Anticipates fast transients and damps overshoot, improving "
               "stability margin. D amplifies measurement noise.",
               "Higher D → better transient damping but twitchy excitation on "
               "noisy signals; too high → control chatter."),
            _s("Overall Gain (G)", "-", "0 – 100 (% / scaled)", "site-tuned",
               "Master gain multiplier applied to PID output (P + I + D terms).",
               "Scales PID response to the alternator's excitation rate "
               "sensitivity. One PID profile can suit multiple machine sizes if "
               "G is tuned per machine.",
               "Low G → slow response, poor recovery; high G → fast response but "
               "risk of instability. Critical for load-step transient performance."),
        ],
        "Startup / Soft Start": [
            _s("Soft Start (Voltage Ramp) Time", "s", "0 – 60", "10 (typical)",
               "Duration for generator output voltage to ramp from residual "
               "(~5% retained) to nominal setpoint after the machine reaches "
               "rated speed.",
               "Avoids inrush transients on loads & transformers at startup by "
               "limiting dV/dt. Too short → voltage overshoot, transformer inrush "
               "current, nuisance trips.",
               "Too short (< 5s) → large inrush on transformer-fed loads; too "
               "long (> 30s) → slow availability when set is needed fast (AMF, "
               "black-start)."),
            _s("Voltage Setpoint / Reference", "V (or % nominal)", "50 – 150 % "
               "(adjustable range)", "100 % nominal",
               "Target voltage the PID drives toward. Often ±5–10% trimmable for "
               "load matching and VAr sharing tuning.",
               "The 100% reference for all voltage-dependent protections and "
               "compliance checks. Offset affects overall system voltage and "
               "reactive sharing with parallel machines.",
               "Lower setpoint → smaller voltage excursions on load steps but "
               "risking under-voltage trips; higher → larger dips."),
        ],
        "Load Acceptance / Limits": [
            _s("LAM — Load Acceptance Module (voltage dip)", "%",
               "dip 0–20 %, delay 0–20 s", "dip ~10–12 %, hold ~5–8 s",
               "Temporary voltage reduction on sudden large load step to reduce "
               "active-power demand and ease engine speed recovery.",
               "Key feature for ISO 8528 transient performance: trades brief "
               "voltage dip for frequency stability, helping the governor hold "
               "speed during block loads.",
               "More aggressive LAM → better frequency recovery but deeper "
               "voltage dip (sensitive loads may drop out); disabled → larger "
               "frequency dips, possible underspeed trips."),
            _s("Underspeed Volts-per-Hertz (U/f) Protection", "Hz / %",
               "knee 40–52 Hz (adj.), slope 0–20 % / Hz (adj.)",
               "knee ~48 Hz, slope ~3–5 % / Hz",
               "Reduces voltage setpoint proportionally when generator frequency "
               "falls below a knee point, preventing over-fluxing when engine "
               "bogs down.",
               "Protects alternator core from saturation and excessive field "
               "demand during underspeed transients. Characteristic: V = Vnom × "
               "(f / f_knee) when f < f_knee.",
               "Higher knee → earlier voltage reduction (better engine recovery, "
               "less field stress) but more voltage sag; lower → risk of "
               "over-excitation saturation."),
            _s("Over-Excitation Limit (max field current)", "A",
               "4–15 A (per machine)", "alternator rated field (e.g. 7 A)",
               "Ceiling on field current to protect exciter and field windings "
               "from thermal damage during sustained high-VAr demand or transients.",
               "Typically time-characteristic (e.g., allow 15 A for 10 s, then "
               "drop to 7 A sustained). Soft limiter that gradually reduces "
               "voltage setpoint as limit is approached.",
               "Too low a limit → voltage cannot be sustained on heavy reactive "
               "load (large dips, instability); too high → field winding risk."),
            _s("Under-Excitation Limit (min field current)", "A / kVAr",
               "typically > pole-slip threshold (per capability curve)",
               "machine pole-slip boundary",
               "Minimum excitation level to keep the alternator within its "
               "stability/capability curve when absorbing large reactive currents "
               "(leading PF in grid parallel).",
               "Prevents loss of synchronism / pole slip when the machine is "
               "forced to operate at leading power factor (e.g., by grid code "
               "reactive requirement).",
               "Too low → loss of synchronism / pole slip catastrophe; too high "
               "→ limits grid-code reactive support capability."),
            _s("Stator Current Limit", "A", "1.0–1.5 × rated stator current",
               "rated current",
               "Limits voltage output by capping stator current to protect "
               "alternator windings from sustained thermal overload.",
               "Soft limiter that backs off voltage setpoint if stator current "
               "approaches limit. Protects against sustained overload or "
               "short-circuit conditions.",
               "Too tight → voltage collapses before reaching full output; too "
               "loose → winding thermal stress risk."),
            _s("Field Forcing on Loss of Sensing", "-", "on/off + value",
               "on (auto-switch to safe value)",
               "Automatic switch to a pre-set safe field current value if the "
               "voltage-sensing input is lost (measurement wire break, VT failure).",
               "Prevents runaway over-excitation (and resulting over-voltage) "
               "when the controller cannot see the voltage. Allows fault current "
               "to sustain if a downstream short occurs.",
               "Must be enabled for safety. Field-forcing value should be chosen "
               "to maintain safe voltage while supporting grid faults."),
        ],
        "Protections & Faults": [
            _s("Over-Voltage Protection", "%", "105–130 % (threshold + delay)",
               "110–115 % (typical)",
               "Detects and responds to sustained over-voltage (excitation/AVR "
               "fault, loss of load, voltage transformer fault).",
               "Typical actions: alarm → stop regulation (switch to field current "
               "mode) or trip. Prevents voltage stress on connected equipment.",
               "Threshold too low → nuisance trips on legitimate transients; too "
               "high → over-voltage damage to loads."),
            _s("Under-Voltage Protection", "%", "70–95 % (threshold + delay)",
               "85 % (typical)",
               "Detects sustained under-voltage (loss of excitation, exciter "
               "failure, overload voltage collapse).",
               "Typical actions: alarm → stop regulation or trigger load "
               "disconnect logic. Protects motors from stalling.",
               "Threshold too low → prolonged low voltage damages motors; too "
               "high → nuisance trips on normal load-step dips."),
            _s("Under-Frequency Protection", "Hz", "47–49 Hz (threshold + delay)",
               "~48 Hz (typical)",
               "Detects prolonged underspeed (engine governor unable to catch up "
               "with load demand, fuel system issue, or coupling loss).",
               "Triggers alarm and/or load-shed logic. Works with U/f slope to "
               "ease engine recovery.",
               "Too high → over-sensitive (nuisance); too low → delayed detection "
               "of genuine engine problem."),
            _s("Over-Frequency Protection", "Hz", "51–52 Hz (threshold + delay)",
               "~52 Hz (typical)",
               "Detects sustained overspeed (governor hunting, sudden load drop, "
               "fuel system malfunction).",
               "Triggers alarm and/or frequency-limiting action. ISO 8528 "
               "recovery bands define acceptable temporary overshoot.",
               "Too low → trip on transient recovery (common fault); too high → "
               "runaway overspeed damage."),
            _s("Open Diode Fault", "-", "detect via ripple signature", "auto",
               "Detects open/failed diode in the rotating exciter rectifier by "
               "analyzing field-current ripple waveform.",
               "Early warning of exciter degradation before catastrophic "
               "excitation loss. Allows planned maintenance vs emergency outage.",
               "Catch early for orderly decommission; late detection → sudden "
               "loss of excitation during load."),
            _s("Shorted Diode Fault", "-", "detect via ripple signature", "auto",
               "Detects short-circuited diode in the rotating exciter by ripple "
               "analysis.",
               "Indicates exciter component degradation. Can lead to partial or "
               "full excitation loss.",
               "Early detection allows troubleshooting; late detection → reduced "
               "voltage support capability."),
            _s("Reverse Power / Active Reverse Power", "%", "-5 to -20 (threshold)",
               "~-10 % (typical)",
               "Detects alternator motoring (power flowing backward into the "
               "prime mover), protecting the engine from being driven.",
               "Critical in parallel operation: if a set loses prime-mover power, "
               "it is motored by other machines, causing engine damage.",
               "Threshold too tight → trips on transient power swings; too loose "
               "→ prolonged motoring damage."),
            _s("Reactive Reverse Power", "kVAr", "threshold + delay", "auto",
               "Detects reverse reactive power flow (capacitive generator "
               "feeding reactive into the grid).",
               "Less critical than active reverse power; can indicate grid "
               "disturbance or islanding risk.",
               "Configuration-dependent; used in grid-code scenarios."),
            _s("Synchro-Check", "-", "frequency/voltage/angle tolerance",
               "enabled when paralleling",
               "Verifies that grid/bus conditions are synchronized before "
               "allowing breaker close (frequency within ±0.5 Hz, voltage within "
               "±10%, angle within ~10°).",
               "Prevents closing onto an out-of-sync bus, which would cause "
               "severe current surge and mechanical shock.",
               "Typical ranges: Δf < ±1 Hz, ΔV < ±10 %, Δθ < ±20° (configurable)."),
            _s("Loss of Sensing Alarm", "-", "auto-detect on VT input",
               "auto-enable",
               "Detects broken voltage-sensing wire or VT failure by monitoring "
               "sensor plausibility.",
               "Triggers field forcing to a safe value to prevent runaway "
               "excitation and over-voltage.",
               "Essential for safety; should trigger alarm and/or field forcing "
               "immediately."),
            _s("Voltage Unbalance Protection", "%", "0–50 % phase mismatch",
               "~10 % (typical)",
               "Detects unbalanced 3-phase voltage (single-phase loss, asymmetric "
               "load).",
               "Protects alternator from unbalanced current heating. Typical "
               "action: alarm → stop regulation.",
               "Threshold too low → nuisance trips (natural single-phase load); "
               "too high → heating risk."),
            _s("Current Unbalance Protection", "%", "0–50 % phase mismatch",
               "~15 % (typical)",
               "Detects unbalanced 3-phase stator current (winding asymmetry, "
               "load unbalance).",
               "Similar to voltage unbalance; protects windings from asymmetric "
               "heating.",
               "Configuration and threshold per machine."),
            _s("Short-Circuit Detection", "-", "instantaneous high current",
               "auto-enable",
               "Detects bolted 3-phase short (stator fault) by sudden current "
               "rise.",
               "Immediate action: typically switches to field current mode to "
               "sustain fault current for downstream protective devices to clear.",
               "Allows coordination with switchgear; without it, AVR may reduce "
               "field and starve fault current."),
            _s("Power Supply Fault (auxiliary 8–35 VDC)", "-", "voltage detect",
               "auto-enable",
               "Detects loss or degradation of the DC auxiliary supply powering "
               "the AVR.",
               "Triggers alarm and/or field-forcing action. Loss of auxiliary "
               "power → loss of control.",
               "Essential monitoring; auxiliary must be properly fused (1 A "
               "fast-acting typical)."),
            _s("IGBT Fault (power stage)", "-", "temperature / over-current",
               "auto-enable",
               "Detects power semiconductor (IGBT) over-temperature or over-stress "
               "in the field-drive bridge.",
               "Triggers thermal shutdown or power limiting to protect the bridge. "
               "Indicates cooling or load issue.",
               "Heatsink blockage, high ambient, or sustained heavy transients "
               "can trigger this."),
            _s("Temperature Alarms & Trips", "°C",
               "0 to +70 °C (operating), configurable limits",
               "alarm ~60 °C, trip ~70 °C (typical)",
               "Monitors D550 PCB temperature (1–5 external Pt100 sensors can be "
               "added for field/stator temperature).",
               "Prevents thermal damage to the AVR and alternator. External "
               "sensor limits protect the machine itself.",
               "Low limits → nuisance alarms in hot climates; high limits → "
               "thermal risk."),
        ],
        "Parallel Operation & Synchronization": [
            _s("Quadrature Droop Characteristic", "%", "0–10 % (adj.)",
               "3–5 % (typical)",
               "Voltage droop proportional to reactive current: V_out = V_set - "
               "droop% × (I_q / I_rated).",
               "Makes paralleled machines share VAr load stably. Each machine "
               "naturally backs off voltage as it carries more reactive current, "
               "preventing one machine from hogging the load.",
               "Higher droop → more voltage sag but better VAr sharing; zero "
               "droop → VAr hunting oscillation."),
            _s("Cross-Current Compensation (CCC)", "-", "on/off + gain %",
               "off (requires dual CT setup)",
               "Uses interconnected phase-V current transformers to feed "
               "cross-current signal directly into voltage setpoint adjustment.",
               "Direct feedback of inter-machine reactive current allows flat "
               "voltage + stable VAr sharing. No voltage droop needed.",
               "Correct wiring/gain → smooth parallel operation; wrong polarity "
               "→ reactive hunting / instability."),
            _s("Voltage Matching (U=U) Tolerance", "%", "±1 to ±20 % "
               "(configurable)", "±3–5 % (typical)",
               "Before breaker close, the AVR adjusts its voltage setpoint to "
               "match the grid/bus voltage within tolerance.",
               "Minimizes voltage difference across the breaker, reducing inrush "
               "current and mechanical shock at close.",
               "Tight tolerance → slow matching, may miss close window; loose "
               "tolerance → large inrush on mismatch close."),
            _s("Breaker Status Input (closing confirmation)", "-",
               "contact / pulse input", "required",
               "Discrete input confirming the breaker has actually closed, "
               "triggering the mode switch (e.g., from voltage matching to PF "
               "regulation).",
               "Safety interlock: prevents regulating in parallel mode before the "
               "breaker is really closed (risk of over-voltage if mains is lost "
               "before close).",
               "Must be wired from the breaker auxiliary contact, not assumed "
               "from breaker command."),
        ],
        "Advanced Features": [
            _s("Curve Functions (5-point)", "-", "up to 4 curves", "typically 0",
               "Defines one parameter as a 5-point function of another (e.g., "
               "kVAr reference vs voltage, field limit vs temperature).",
               "Allows sophisticated control logic without external PLC (e.g., "
               "voltage support curve matching grid code requirements).",
               "Used for dynamic characteristics & non-linear compensation. "
               "Linear segments between points."),
            _s("Logic / Analog Gates", "-", "up to 20 gates (2-input)", "0 active",
               "Configurable function blocks: AND/OR/XOR, comparators, "
               "set-reset, addition/subtraction/multiplication/division, "
               "temporization.",
               "Allows local decision-making without external PLC (e.g., load "
               "shedding logic, frequency-dependent actions).",
               "Chain gates together for complex control sequences. Useful for "
               "AMF and grid-code adaptive control."),
            _s("Event Logging & Counters", "-", "up to 8 counters", "as configured",
               "Records occurrence of user-defined events (e.g., over-voltage "
               "occurrence count) with optional field-current snapshot.",
               "Enables remote monitoring and maintenance trending (e.g., how "
               "many times has over-voltage been triggered?).",
               "Useful for diagnostics and predictive maintenance planning."),
            _s("Oscilloscope Function (with USB)", "-", "8-parameter plot", "on demand",
               "Real-time waveform capture and replay of up to 8 signals "
               "(voltage, current, frequency, field, etc.) via EasyReg software.",
               "Commissioning & troubleshooting tool: visualizes AVR response to "
               "load steps, transients, and faults in real-time.",
               "Requires USB connection to EasyReg Advanced; essential for "
               "tuning PID and validating behavior."),
            _s("Monitor Window (dashboard)", "-", "numeric/gauges/curves",
               "on demand",
               "Configurable real-time display dashboard showing voltage, current, "
               "PF, frequency, temperature, synchronization status, and fault "
               "flags.",
               "Remote monitoring window when connected via USB/CAN. Shows "
               "current regulation state & performance.",
               "Useful for commissioning, operation, and diagnostics."),
            _s("Second Configuration / 50–60 Hz Switching", "-",
               "on/off + select via input", "off",
               "Stores a second full parameter set that can be switched in via "
               "digital input (e.g., for 50 Hz ↔ 60 Hz operation).",
               "Useful for dual-frequency sets or for selecting alternate "
               "regulation modes on demand.",
               "Allows up to 16 parameters to differ between Config A and Config B."),
            _s("Synchronization Logic Module", "-", "on/off + settings",
               "off (requires grid voltage input)",
               "Evaluates grid voltage frequency, magnitude, angle, and breaker "
               "timing to determine synchronization readiness.",
               "Part of breaker-closing safety logic; ensures conditions are safe "
               "before initiating close command.",
               "Typical thresholds: Δf < ±1 Hz, ΔV < ±10%, Δθ < ±20°."),
            _s("Grid Code Functions (option module)", "-", "LVRT / FRT / "
               "voltage support", "off",
               "Optional modules for grid-code compliance (wind, solar, DG "
               "integration): LVRT (low-voltage ride-through), FRT (fault ride-through), "
               "reactive power / voltage support curves.",
               "Helps manage transient behavior during grid disturbances per "
               "local grid codes.",
               "Requires option license and additional external inputs (grid "
               "voltage, frequency, phase).",
            ),
        ],
        "Electrical Specifications": [
            _s("Field Current Rating", "A", "7 A @ 70 °C, 8 A @ 55 °C",
               "7 A (continuous)",
               "Maximum sustained excitation current the D550 can supply without "
               "exceeding temperature limits.",
               "Sets the upper limit on field power delivery and the "
               "over-excitation protection threshold.",
               "Short-circuit current (10 s max) is 15 A. Exceeding sustained "
               "limit risks heatsink overtemp fault."),
            _s("Voltage Measurement Range", "VAC", "2-phase or 3-phase, "
               "0–530 VAC rms", "site-dependent (e.g. 0–480 for LV)",
               "Input voltage range for alternator voltage feedback. VT required "
               "if alternator voltage exceeds 480 VAC.",
               "Measures stator voltage for closed-loop regulation. Over-range "
               "can damage measurement circuit.",
               "Configure input type (Y/Δ) and VT ratio (1:1 for direct, up to "
               "500:1 for MV/HV)."),
            _s("Frequency Measurement Range", "Hz", "30–400 Hz", "50 or 60 Hz "
               "(nominal)",
               "Bandwidth for frequency detection from AC measurement inputs. "
               "Covers wide range to support variable-speed generators.",
               "Allows transient frequency measurement and synchronization logic. "
               "Zero-crossing detection.",
               "Narrow range (e.g. ±5 Hz) improves noise immunity; wide range "
               "helps during major disturbances."),
            _s("Current Measurement (CT)", "A/A", "1–5 A secondary, "
               "0–300% overload for 30 s", "per CT spec",
               "Generator stator current input via current transformer for power "
               "and PF calculations, load sharing, and limits.",
               "CT secondary is 1–5 A (range-configurable). Overload capability "
               "for short-circuit recording.",
               "CT ratio & burden must be entered in configuration; wrong ratio "
               "scales all current-dependent functions."),
            _s("Auxiliary DC Power Supply", "VDC", "8–35 VDC (nominal ~24)",
               "site-dependent (typically 24 VDC)",
               "Powers the D550 PCB logic and field-drive circuits. Must be "
               "protected by a 1 A fast-acting fuse.",
               "Loss of auxiliary → loss of AVR control. Low voltage → control "
               "malfunction.",
               "Must be a regulated supply within ±10% of nominal. Transient "
               "dropout > 50 ms triggers fault."),
            _s("AC Power Supply Inputs (PMG/AREP/SHUNT)", "VAC",
               "50–277 VAC, 10 VA typical draw", "PMG (permanent magnet "
               "alternator) @ 50–100 VAC typical",
               "Powers the exciter field circuit or provides input to rectification. "
               "Options: PMG (permanent-magnet exciter output), AREP (main stator "
               "auxiliary winding), SHUNT (external AC source).",
               "Selection depends on alternator architecture. PMG is most robust "
               "(doesn't depend on main AVR).",
               "AC supply must be protected by Class CC fuse (15 A max) or 10 A "
               "breaker. Loss of AC input → loss of field power."),
            _s("Operating Temperature Range", "°C", "-40 to +70 °C (operating)",
               "-40 to +70 °C",
               "D550 PCB ambient temperature limits. Exceeding +70 °C triggers "
               "thermal shutdown.",
               "Heatsink design and cabinet cooling must ensure operating "
               "condition within range.",
               "Derate output in high-ambient locations (e.g., tropical climates "
               "may need >55 °C derating to protect field windings)."),
            _s("EMC / Standards", "-", "IEC 61000-6-2 (industrial immunity), "
               "IEC 61000-6-4 (industrial emissions)",
               "compliant",
               "Electromagnetic compatibility: industrial immunity to transients, "
               "RF, harmonics; emissions controlled.",
               "Shielded cables required outside terminal box (>5 m runs or heavy "
               "EMI environment).",
               "Proper grounding and bonding essential for compliance; loosely "
               "wired systems may see nuisance trips."),
        ],
        "Measurement & Wiring": [
            _s("Voltage Transformer (VT) Requirement", "-",
               "required if V > 480 VAC L-L", "not required < 480 VAC",
               "Voltage step-down transformer required for MV/HV generators to "
               "safely measure at 0–480 VAC secondary.",
               "PT (potential transformer) / VT rated for measurement (typically "
               "burden class 0.2 or better).",
               "Burden (VA) must be low to avoid voltage drop on the VT secondary "
               "affecting measurement accuracy."),
            _s("Current Transformer (CT) Placement", "-",
               "phase U: parallel output, phase V: cross-current & grid, "
               "phase W: spare", "per regulation mode needed",
               "CT placement is fixed per function: U-phase for standard parallel "
               "sharing, V-phase for cross-current compensation & grid current, "
               "W-phase optional.",
               "Wrong placement → VAr sharing failure, incorrect power "
               "measurements. Cross-current CT must see inter-machine reactive "
               "current.",
               "Ensure all CTs have same ratio and burden. Mismatch causes "
               "imbalance in sharing logic."),
            _s("Cable Length & EMC Shielding", "m", "max 100 m total, "
               "shielded if > 5 m outside terminal box", "< 5 m in terminal box "
               "okay unshielded",
               "Long/unshielded cables pick up EMI and can cause nuisance trips "
               "or measurement errors.",
               "Recommend shielded twisted pair for all analog inputs (voltage, "
               "current) outside the terminal box. Ground shield at one end only.",
               "Poor shielding → random faults, frequency/voltage measurement "
               "noise, false protection trips."),
            _s("Field Winding Resistance", "Ω", "> 4 Ω (minimum safe)", "machine-dependent "
               "(typical 5–50 Ω)",
               "Exciter field coil DC resistance. Must be measured during "
               "commissioning and confirmed against the exciter nameplate.",
               "Low resistance indicates winding short; very high resistance "
               "indicates open circuit. Both prevent proper excitation.",
               "Used by EasyReg to estimate field time-constant and for "
               "over-current detection thresholds."),
            _s("Earth (Ground) Connection", "-", "dedicated earth terminal",
               "essential",
               "The D550 must be earthed via the dedicated M5 terminal to the "
               "machine frame / cabinet earth.",
               "All control signals, analog inputs, and the heatsink reference to "
               "this earth. Poor earth → nuisance trips, measurement errors.",
               "Must be low impedance (< 1 Ω). Use substantial cable, not a small "
               "wire. Test resistance at commissioning."),
        ],
        "Configuration & Commissioning": [
            _s("Quick Configuration", "-", "select machine from database",
               "default / fastest",
               "EasyReg database includes pre-tuned parameters for common "
               "alternator models. User selects machine, downloads parameters.",
               "Fast path for straightforward setups where alternator is from a "
               "known OEM with test data.",
               "Can be refined in Advanced mode later. Good starting point for "
               "tuning."),
            _s("Advanced Configuration", "-", "full manual parameter entry",
               "required for custom machines",
               "Manual definition of alternator ratings, excitation curve, "
               "measurement configuration, capability limits, protection thresholds, "
               "PID gains, I/O mapping.",
               "Needed for bespoke or unusual alternators. Requires detailed "
               "machine nameplate and test/commissioning data.",
               "Allows complete customization for grid codes, voltage matching, "
               "synchronization, and advanced modes."),
            _s("Overcurrent Protection (AC supply)", "-",
               "Class CC fast-blow fuse (15 A max) or circuit breaker (10 A max)",
               "per supply source",
               "Protects AC power input from overcurrent (short, fault). Must be "
               "rated fast-acting to protect control circuits.",
               "Slow fuses (Class T) are insufficient and may not clear in time to "
               "prevent damage.",
               "Check fuse rating at commissioning; wrong fuse type → may not "
               "protect the AVR on internal faults."),
            _s("DC Auxiliary Protection", "-", "1 A fast-acting fuse (or DCCT)",
               "required",
               "Protects the 8–35 VDC auxiliary supply from overcurrent (short "
               "circuit, battery fault).",
               "Loss of auxiliary → loss of control; must be protected to prevent "
               "extended short. 1 A is standard for 24 VDC logic circuits.",
               "Use ceramic cartridge fuses (fast-acting). Auto-reset breakers "
               "risk repeated shutdown cycles on transient faults."),
            _s("Mounting & Heatsink Cooling", "-",
               "vertical heatsink orientation, ≥ 50 mm clearance all sides",
               "standard cabinet mount",
               "Heatsink (rear aluminum fin structure) must have free airflow for "
               "thermal dissipation. Vertical orientation is best (convection).",
               "Blocked heatsink → over-temperature fault, reduced field output.",
               "In high-ambient cabinets, consider duct cooling or forced-air "
               "fan."),
        ],
        "Maintenance & Troubleshooting": [
            _s("Preventive Maintenance Schedule", "-",
               "visual inspection annually, connector tightness check yearly",
               "annually",
               "Remove dust (dry air), verify connector tightness (0.6–0.8 Nm "
               "terminal torque), ensure heatsink airflow is unobstructed.",
               "Running hour meter available via parameter 254.008. Replacement "
               "advised after 40,000 hours of operation.",
               "Early maintenance prevents failure-mode surprises during critical "
               "operation."),
            _s("Typical Anomalies & Remedies", "-",
               "voltage drift, loss of excitation, over-temperature, frozen "
               "display, no USB communication", "per symptom",
               "Manual lists common failure modes and recommended troubleshooting "
               "steps (check VT, CT wiring; verify exciter field continuity; "
               "inspect cooling; replace AVR if internal fault confirmed).",
               "Structured troubleshooting methodology to isolate external vs "
               "internal faults.",
               "Most failures are external (broken wiring, exciter fault, cooling "
               "blockage). Only replace AVR if internal diagnostics confirm "
               "malfunction."),
        ],
    },
}



SETTINGS_DATA = {
    "ComAp InteliGen / InteliSys NT": _COMAP,
    "Leroy-Somer D550 AVR": _D550,
}


def list_devices():
    """Return the device names available in the reference."""
    return list(SETTINGS_DATA.keys())


def get_device(device_name):
    """Return the device dict, or None."""
    return SETTINGS_DATA.get(device_name)


def search_settings(query, device_name=None):
    """
    Free-text search across setting name / description / philosophy /
    performance (and group name). Case-insensitive substring match on
    whitespace-split terms — every term must appear somewhere in the entry.

    Returns a list of dicts: {device, group, setting} ready to render.
    """
    query = (query or "").strip().lower()
    terms = [t for t in query.split() if t]
    results = []
    devices = [device_name] if device_name and device_name in SETTINGS_DATA \
        else list(SETTINGS_DATA.keys())
    for dev in devices:
        for group, settings in SETTINGS_DATA[dev]["groups"].items():
            for setting in settings:
                haystack = " ".join([
                    group,
                    setting["name"],
                    setting["description"],
                    setting["philosophy"],
                    setting["performance"],
                ]).lower()
                if all(t in haystack for t in terms):
                    results.append({"device": dev, "group": group,
                                    "setting": setting})
    return results


def count_settings(device_name=None):
    """Total number of settings (optionally for one device)."""
    devices = [device_name] if device_name else list(SETTINGS_DATA.keys())
    return sum(len(g) for d in devices
               for g in SETTINGS_DATA[d]["groups"].values())
