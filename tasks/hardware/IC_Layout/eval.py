"""Evaluation helpers for IC Layout Design benchmark."""

import re
import os
import tempfile
import logging

logger = logging.getLogger(__name__)


def check_required_layers(gds_bytes):
    """Check that the GDS contains geometries on all required Sky130 layers.

    Returns dict with:
        'layers_found': dict of layer_name -> bool
        'all_pass': bool
    """
    import klayout.db as db

    required_layers = {
        "nwell": (64, 20),
        "diff": (65, 20),
        "poly": (66, 20),
        "licon": (66, 44),
        "li1": (67, 20),
        "mcon": (67, 44),
        "met1": (68, 20),
        "nsdm": (93, 44),
        "psdm": (94, 20),
    }

    results = {
        "layers_found": {},
        "all_pass": False,
    }

    try:
        with tempfile.NamedTemporaryFile(suffix=".gds", delete=False) as f:
            f.write(gds_bytes)
            tmp_path = f.name

        layout = db.Layout()
        layout.read(tmp_path)
        top = layout.top_cell()

        if top is None:
            return results

        for name, (layer_num, datatype) in required_layers.items():
            idx = layout.find_layer(layer_num, datatype)
            if idx is not None and idx >= 0:
                region = db.Region(top.begin_shapes_rec(idx))
                results["layers_found"][name] = not region.is_empty()
            else:
                results["layers_found"][name] = False

        results["all_pass"] = all(results["layers_found"].values())

    except Exception as e:
        logger.info(f"Error reading GDS: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return results


def check_transistor_gates(gds_bytes):
    """Check for poly/diff overlap regions indicating transistor gates.

    Returns dict with:
        'gate_count': int
        'pass': bool
    """
    import klayout.db as db

    results = {
        "gate_count": 0,
        "pass": False,
    }

    try:
        with tempfile.NamedTemporaryFile(suffix=".gds", delete=False) as f:
            f.write(gds_bytes)
            tmp_path = f.name

        layout = db.Layout()
        layout.read(tmp_path)
        top = layout.top_cell()

        if top is None:
            return results

        poly_idx = layout.find_layer(66, 20)
        diff_idx = layout.find_layer(65, 20)

        if poly_idx is None or diff_idx is None or poly_idx < 0 or diff_idx < 0:
            return results

        poly = db.Region(top.begin_shapes_rec(poly_idx))
        diff = db.Region(top.begin_shapes_rec(diff_idx))

        gates = poly & diff
        gates.merge()

        results["gate_count"] = gates.count()
        results["pass"] = results["gate_count"] >= 2

    except Exception as e:
        logger.info(f"Error checking gates: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return results


def check_metal_and_contacts(gds_bytes):
    """Check for metal interconnects and contacts.

    Returns dict with:
        'contact_count': int
        'metal_count': int
        'pass': bool
    """
    import klayout.db as db

    results = {
        "contact_count": 0,
        "metal_count": 0,
        "pass": False,
    }

    try:
        with tempfile.NamedTemporaryFile(suffix=".gds", delete=False) as f:
            f.write(gds_bytes)
            tmp_path = f.name

        layout = db.Layout()
        layout.read(tmp_path)
        top = layout.top_cell()

        if top is None:
            return results

        contact_count = 0
        for layer_num, datatype in [(66, 44), (67, 44)]:
            idx = layout.find_layer(layer_num, datatype)
            if idx is not None and idx >= 0:
                r = db.Region(top.begin_shapes_rec(idx))
                r.merge()
                contact_count += r.count()

        metal_count = 0
        for layer_num, datatype in [(67, 20), (68, 20)]:
            idx = layout.find_layer(layer_num, datatype)
            if idx is not None and idx >= 0:
                r = db.Region(top.begin_shapes_rec(idx))
                r.merge()
                metal_count += r.count()

        results["contact_count"] = contact_count
        results["metal_count"] = metal_count
        results["pass"] = contact_count >= 4 and metal_count >= 3

    except Exception as e:
        logger.info(f"Error checking metal/contacts: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return results


def check_net_labels(gds_bytes):
    """Check that net labels IN, OUT, VDD, VSS are present.

    Returns dict with:
        'labels_found': dict of label -> bool
        'all_pass': bool
    """
    import klayout.db as db

    required_labels = ["IN", "OUT", "VDD", "VSS"]
    label_layers = [(68, 5), (67, 5), (68, 16), (67, 16), (66, 5)]

    results = {
        "labels_found": {label: False for label in required_labels},
        "all_pass": False,
    }

    try:
        with tempfile.NamedTemporaryFile(suffix=".gds", delete=False) as f:
            f.write(gds_bytes)
            tmp_path = f.name

        layout = db.Layout()
        layout.read(tmp_path)
        top = layout.top_cell()

        if top is None:
            return results

        found = set()
        for layer_num, datatype in label_layers:
            idx = layout.find_layer(layer_num, datatype)
            if idx is None or idx < 0:
                continue
            it = top.begin_shapes_rec(idx)
            while not it.at_end():
                shape = it.shape()
                if shape.is_text():
                    found.add(shape.text.string.strip().upper())
                it.next()

        for label in required_labels:
            results["labels_found"][label] = label in found

        results["all_pass"] = all(results["labels_found"].values())

    except Exception as e:
        logger.info(f"Error checking labels: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return results


def parse_drc_report(drc_text):
    """Parse KLayout DRC XML report for violation count.

    Returns dict with:
        'violation_count': int or None
        'report_valid': bool
        'parse_error': str or None
    """
    results = {
        "violation_count": None,
        "report_valid": False,
        "parse_error": None,
    }

    if not drc_text or len(drc_text) < 100:
        results["parse_error"] = "DRC report missing or too small"
        return results

    try:
        items = re.findall(r'<item>', drc_text)
        results["violation_count"] = len(items)
        results["report_valid"] = True
    except Exception as e:
        results["parse_error"] = f"Failed to parse DRC report: {e}"

    return results


def parse_lvs_report(lvs_text):
    """Parse KLayout .lvsdb report for match status.

    The .lvsdb file uses KLayout's own format with a Z() section
    containing cross-reference entries:
        N(layout_idx ref_idx status)  — net match
        D(layout_idx ref_idx status)  — device match
    Status 1 = matched, 0 = mismatched.

    Returns dict with:
        'all_matched': bool
        'net_matches': int
        'net_mismatches': int
        'device_matches': int
        'device_mismatches': int
        'report_valid': bool
        'parse_error': str or None
    """
    results = {
        "all_matched": False,
        "net_matches": 0,
        "net_mismatches": 0,
        "device_matches": 0,
        "device_mismatches": 0,
        "report_valid": False,
        "parse_error": None,
    }

    if not lvs_text or len(lvs_text) < 100:
        results["parse_error"] = "LVS report missing or too small"
        return results

    try:
        z_sections = list(re.finditer(r'Z\(\s*\n', lvs_text))
        if not z_sections:
            results["parse_error"] = "No Z() cross-reference section found"
            return results

        last_z_start = z_sections[-1].end()
        z_content = lvs_text[last_z_start:]

        net_entries = re.findall(r'N\(\s*(\d+)\s+(\d+)\s+(\d+)\s*\)', z_content)
        for layout_idx, ref_idx, status in net_entries:
            if int(status) == 1:
                results["net_matches"] += 1
            else:
                results["net_mismatches"] += 1

        device_entries = re.findall(r'D\(\s*(\d+)\s+(\d+)\s+(\d+)\s*\)', z_content)
        for layout_idx, ref_idx, status in device_entries:
            if int(status) == 1:
                results["device_matches"] += 1
            else:
                results["device_mismatches"] += 1

        total_entries = len(net_entries) + len(device_entries)
        if total_entries == 0:
            results["parse_error"] = "No match entries found in Z() section"
            return results

        results["report_valid"] = True
        results["all_matched"] = (
            results["net_mismatches"] == 0 and
            results["device_mismatches"] == 0 and
            total_entries > 0
        )

    except Exception as e:
        results["parse_error"] = f"Failed to parse LVS report: {e}"

    return results