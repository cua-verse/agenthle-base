"""Evaluation helpers for Buck Converter Design benchmark."""

import re
import os
import logging
import numpy as np

logger = logging.getLogger(__name__)


# ── L1: ASC File Parsing ──

def check_rload_value(asc_text, config):
    """Check that the pre-placed Rload resistor has the correct value (~0.15Ω)."""
    current_symbol = None
    current_instname = None

    for line in asc_text.split('\n'):
        line = line.strip()
        if line.startswith('SYMBOL'):
            parts = line.split()
            current_symbol = parts[1].lower() if len(parts) >= 2 else None
            current_instname = None
        elif line.startswith('SYMATTR InstName'):
            current_instname = line.replace('SYMATTR InstName', '').strip()
        elif line.startswith('SYMATTR Value') and current_instname == 'Rload':
            val = line.replace('SYMATTR Value', '').strip()
            try:
                parsed = float(val)
            except ValueError:
                return False
            load_min = config.LOAD_R_TARGET * (1 - config.LOAD_R_TOL)
            load_max = config.LOAD_R_TARGET * (1 + config.LOAD_R_TOL)
            return load_min <= parsed <= load_max

    return False


def check_tran_directive(asc_text, config):
    """Check that the ASC file contains a .tran directive with ~1ms duration and startup flag.

    Accepts common LTspice time formats for 1ms: '1m', '1ms', '0.001', '1e-3'.
    The 'startup' keyword must also be present on the directive line.
    """
    for line in asc_text.split('\n'):
        line = line.strip()
        if not line.upper().startswith('TEXT') and not line.upper().startswith('.TRAN'):
            continue

        # LTspice stores directives as: TEXT x y ... ;.tran 1m startup
        # or as raw directives: .tran 1m startup
        tran_match = re.search(r'\.tran\s+(.+)', line, re.IGNORECASE)
        if not tran_match:
            continue

        directive_body = tran_match.group(1).strip()

        # Check for 'startup' keyword
        if 'startup' not in directive_body.lower():
            continue

        # Check for ~1ms duration as first argument
        first_arg = directive_body.split()[0]

        # Parse the time value
        duration_s = None
        try:
            duration_s = float(first_arg)
        except ValueError:
            # Try suffix: "1m", "1ms"
            t_match = re.match(r'^(\d+\.?\d*)\s*(ms?|s)?$', first_arg, re.IGNORECASE)
            if t_match:
                val = float(t_match.group(1))
                suffix = (t_match.group(2) or '').lower()
                if suffix in ('m', 'ms'):
                    duration_s = val * 1e-3
                elif suffix == 's' or suffix == '':
                    duration_s = val

        if duration_s is not None and abs(duration_s - 1e-3) < 1e-4:
            return True

    return False


# ── L2: RAW File Analysis ──

def _parse_raw_binary(raw_path):
    """Parse LTspice .raw file using ltspice lib for header, manual binary read for data."""
    import ltspice as lt

    raw = lt.Ltspice(raw_path)
    # Don't call raw.parse() — it breaks with numpy 2.x
    # Instead read header metadata and parse binary ourselves

    with open(raw_path, 'rb') as f:
        data = f.read()[raw.header_size:]

    n_pts = raw._point_num
    n_vars = raw._variable_num
    var_names = raw._variables

    # Transient sim: time=float64, variables=float32
    y_dtype = np.float32 if 'double' not in raw.flags else np.float64

    record_dtype = np.dtype([('x', np.float64), ('y', y_dtype, (n_vars - 1,))])
    records = np.frombuffer(data, dtype=record_dtype, count=n_pts)

    traces = {var_names[0]: np.abs(records['x'])}
    for i in range(1, n_vars):
        traces[var_names[i]] = records['y'][:, i - 1]

    return traces


def analyze_raw_output(raw_bytes, config):
    """Parse .raw file and check output voltage, ripple, and load current."""
    results = {
        "output_voltage": {"value": None, "pass": False},
        "output_ripple": {"value_mv": None, "pass": False},
        "load_current": {"value": None, "pass": False},
    }

    import tempfile

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.raw', delete=False) as f:
            f.write(raw_bytes)
            tmp_path = f.name

        traces = _parse_raw_binary(tmp_path)

        time = traces.get('time')
        vout = traces.get('V(out)')
        if time is None or vout is None:
            logger.info(f"Missing traces. Available: {list(traces.keys())}")
            return results

        # Measurement window 0.7ms–1.0ms
        mask = (time >= config.MEAS_START_MS * 1e-3) & (time <= config.MEAS_END_MS * 1e-3)
        if np.sum(mask) < 10:
            return results

        v_meas = vout[mask].astype(np.float64)

        # Output voltage
        v_mean = float(np.mean(v_meas))
        results["output_voltage"]["value"] = v_mean
        results["output_voltage"]["pass"] = (
            config.OUTPUT_V_TARGET * (1 - config.OUTPUT_V_TOL) <= v_mean
            <= config.OUTPUT_V_TARGET * (1 + config.OUTPUT_V_TOL)
        )

        # Output ripple
        ripple_mv = float((np.max(v_meas) - np.min(v_meas)) * 1000)
        results["output_ripple"]["value_mv"] = ripple_mv
        results["output_ripple"]["pass"] = ripple_mv < config.RIPPLE_MAX_MV

        # Load current
        iload_data = traces.get('I(Rload)')
        if iload_data is None:
            logger.info("I(Rload) not found — Rload may have been removed")
            return results

        iload_mean = float(np.mean(np.abs(iload_data[mask])))

        results["load_current"]["value"] = iload_mean
        results["load_current"]["pass"] = (
            config.LOAD_I_TARGET * (1 - config.LOAD_I_TOL) <= iload_mean
            <= config.LOAD_I_TARGET * (1 + config.LOAD_I_TOL)
        )

    except Exception as e:
        logger.info(f"Failed to analyze .raw file: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    return results