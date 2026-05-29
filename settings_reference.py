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
               "and protections; configured via EasyReg Advanced over USB/CAN.",
    "source": "Leroy-Somer / Nidec D550 Installation & Maintenance manual + "
              "EasyReg Advanced (verify against uploaded PDF).",
    "verified": False,
    "groups": {
        "Regulation Modes": [
            _s("Voltage Regulation (AVR)", "-", "on/off", "on",
               "Primary mode: holds generator output voltage at the setpoint by "
               "controlling field excitation.",
               "Core AVR function — closes the loop on measured stator voltage "
               "vs reference, driving the exciter field.",
               "Stable voltage regulation is the baseline; mode selection "
               "determines which quantity the PID controls."),
            _s("Power Factor (cos φ) Regulation", "-", "0.6 – 1.0", "0.8 ind",
               "Holds a target power factor — used when paralleled with the "
               "mains.",
               "In grid-parallel the bus sets voltage, so the AVR instead "
               "regulates reactive output to a PF target.",
               "Lower PF target → more reactive current/heating; must only be "
               "active in parallel, never in island (voltage would drift)."),
            _s("kVAR Regulation", "kVAr", "± rated", "0",
               "Holds a fixed reactive-power output in mains-parallel.",
               "Alternative to PF mode for grid codes that specify kVAr rather "
               "than cos φ.",
               "Sets reactive loading directly; affects alternator heating and "
               "grid voltage support."),
            _s("Field Current (Manual / Excitation)", "A", "0 – max field", "—",
               "Open-loop manual control of field current.",
               "Backup/commissioning mode and the fallback if voltage sensing "
               "is lost (so the machine does not collapse or over-excite).",
               "No automatic voltage correction — voltage follows load; used for "
               "diagnostics or controlled manual operation only."),
        ],
        "PID Tuning": [
            _s("Proportional Gain (P)", "-", "0 – 100 (%/scaled)", "site-tuned",
               "Immediate corrective action proportional to voltage error.",
               "Sets loop stiffness — how hard the AVR reacts to a deviation now.",
               "Higher P → faster response and better load-step recovery but "
               "risk of overshoot/oscillation; lower P → sluggish, larger "
               "voltage dips on load acceptance."),
            _s("Integral Gain (I)", "-", "0 – 100 (%/scaled)", "site-tuned",
               "Eliminates steady-state voltage error by accumulating it over "
               "time.",
               "Guarantees the voltage settles exactly on setpoint, not just "
               "near it.",
               "Higher I → faster removal of residual error but slow "
               "oscillation/overshoot if too high; lower I → persistent small "
               "voltage offset."),
            _s("Derivative Gain (D)", "-", "0 – 100 (%/scaled)", "site-tuned",
               "Reacts to the rate of change of voltage error (damping).",
               "Anticipates and damps fast transients, improving stability "
               "margin.",
               "Higher D → better damping of overshoot but amplifies measurement "
               "noise/jitter; too high → twitchy excitation."),
            _s("Overall Gain (G)", "-", "0 – 100", "site-tuned",
               "Master multiplier scaling the whole PID output (per machine "
               "size / exciter).",
               "Lets one PID profile be scaled to the alternator's excitation "
               "characteristics.",
               "Acts on P, I, D together — a global stability/response trade-off "
               "knob."),
        ],
        "Startup / Soft Start": [
            _s("Soft Start (Voltage Ramp) Time", "s", "0 – 60", "10",
               "Ramp time for output voltage to rise from residual to nominal at "
               "startup.",
               "Avoids voltage overshoot and limits inrush/torque on connected "
               "loads/transformers at build-up.",
               "Too short → voltage overshoot and breaker/transformer inrush; "
               "too long → slow availability after start."),
            _s("Voltage Setpoint / Reference", "V (or %)", "±10 % of nominal",
               "nominal",
               "Target regulated voltage (often trimmable ±5/±10 %).",
               "The reference the voltage PID drives toward; can be biased by "
               "the gen-set controller for matching/VAr sharing.",
               "Sets the operating voltage; offsets shift the whole compliance "
               "window and reactive sharing in parallel."),
        ],
        "Load Acceptance / Limits": [
            _s("LAM — Load Acceptance Module", "%", "voltage dip 0 – 20 %",
               "enabled, ~5–15 %",
               "Deliberately drops voltage on a large load impact to reduce "
               "active-power demand, helping the engine hold speed, then ramps "
               "voltage back.",
               "Trades a brief voltage dip for frequency stability — eases the "
               "engine through block-load steps (key for ISO 8528 transient "
               "performance).",
               "More aggressive LAM → better frequency recovery but deeper "
               "voltage dip; disabled → larger frequency dips/possible underspeed "
               "trips on big steps."),
            _s("Underspeed (U/f, Volts/Hz)", "Hz / %",
               "knee 47–49 Hz, slope adj.", "knee ~48 Hz",
               "Reduces voltage setpoint proportionally when frequency falls "
               "below a knee point.",
               "Volts-per-Hertz protection — prevents over-fluxing and excessive "
               "field demand when the engine bogs down under load.",
               "Higher knee/steeper slope → earlier voltage reduction, better "
               "engine recovery but more voltage sag; lower → risk of "
               "over-excitation and stalling on heavy steps."),
            _s("Over-Excitation Limit (max field)", "A", "set to alternator max",
               "machine-rated",
               "Caps maximum field current with a time characteristic.",
               "Protects the exciter and main field windings from thermal damage "
               "during sustained heavy reactive/transient demand.",
               "Too low → can't support voltage on load (dips/instability); too "
               "high → field overheating risk."),
            _s("Under-Excitation Limit (min field)", "A/kVAr",
               "set above pole-slip", "machine-rated",
               "Limits how far excitation can be reduced (leading PF region).",
               "Keeps the machine inside its stability/capability curve when "
               "absorbing reactive power in parallel.",
               "Too low a limit risks loss of synchronism/pole slip; too high "
               "prevents legitimate reactive absorption."),
            _s("Stator Current Limit", "A", "set to rated", "rated",
               "Limits regulated output by capping stator current.",
               "Protects the alternator windings during sustained overload by "
               "backing off excitation.",
               "Tight → voltage collapses early under overload; loose → winding "
               "thermal stress."),
        ],
        "Paralleling": [
            _s("Reactive Droop", "%", "0 – 10", "3 – 5",
               "Reduces voltage setpoint in proportion to reactive (lagging) "
               "load.",
               "Makes paralleled alternators share reactive load stably without "
               "fast inter-machine communication.",
               "More droop → better/robuster VAr sharing but more voltage sag "
               "with reactive load; zero droop → reactive load hunting between "
               "machines."),
            _s("Cross-Current Compensation", "-", "on/off + gain", "off",
               "Uses interconnected CTs so paralleled sets share reactive load "
               "with little/no voltage droop.",
               "Alternative to droop for tightly-coupled sets where voltage "
               "droop is undesirable.",
               "Mis-wired/over-gained → reactive hunting and instability; "
               "correctly set → flat voltage with good VAr sharing."),
            _s("Voltage Matching", "-", "on/off", "on (when paralleling)",
               "Adjusts the voltage setpoint to match the bus/mains before "
               "breaker close.",
               "Minimises the voltage difference across the synchronising "
               "breaker to avoid current/torque shock at close.",
               "Without it, a voltage mismatch at close causes a reactive "
               "current surge and mechanical shock."),
        ],
        "Protections / Monitoring": [
            _s("Generator Over-Voltage", "%", "105 – 130", "110–115, delayed",
               "Trips/alarms excitation on sustained over-voltage.",
               "Backstop against AVR/sensing faults that drive voltage up.",
               "Tight → nuisance trips on transients; loose → over-voltage "
               "stress on the load."),
            _s("Generator Under-Voltage", "%", "70 – 95", "85, delayed",
               "Trips/alarms on sustained under-voltage.",
               "Detects loss of excitation / overload voltage collapse.",
               "Tight → trips on normal dips; loose → prolonged low voltage."),
            _s("Loss of Sensing / Field-Forcing", "-", "on/off", "on",
               "Detects loss of the voltage-sensing input and switches to a safe "
               "field current; field forcing boosts excitation during faults to "
               "sustain fault current for protection coordination.",
               "Prevents runaway over-excitation when sensing fails and ensures "
               "enough fault current for downstream breakers to trip.",
               "Disabled → sensing loss can cause full-field over-voltage; "
               "forcing off → downstream protection may not see enough fault "
               "current."),
            _s("Diode / Exciter Fault Monitoring", "-", "on/off + threshold",
               "on",
               "Detects rotating-diode failures via field-current ripple "
               "signature.",
               "Early warning of exciter rectifier degradation before full "
               "failure.",
               "Catches a failing diode before it cascades to loss of excitation "
               "and a forced outage."),
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
