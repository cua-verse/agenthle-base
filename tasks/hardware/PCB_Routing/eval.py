"""Evaluation helpers for PCB Routing Design benchmark."""

import re
import json
import logging

logger = logging.getLogger(__name__)


def count_trace_segments(pcb_text):
    """Count the number of trace segments in a .kicad_pcb file.

    Each routed trace is stored as a (segment ...) entry.
    Returns the count of segments found.
    """
    matches = re.findall(r'\(segment\s', pcb_text)
    return len(matches)


def count_filled_zone_polygons(pcb_text, net_name="GND"):
    """Count filled_polygon entries associated with a specific net.

    When a zone is filled, KiCad writes (filled_polygon ...) entries
    inside the zone definition. Returns the count found for the given net.
    """
    count = 0
    in_zone = False
    in_target_zone = False
    zone_depth = 0

    for line in pcb_text.split('\n'):
        stripped = line.strip()

        # Detect start of any zone block
        if stripped.startswith('(zone'):
            in_zone = True
            in_target_zone = False
            zone_depth = 0

        # Once inside a zone, check if it's for our target net
        if in_zone and f'(net_name "{net_name}")' in stripped:
            in_target_zone = True

        # Track paren depth within zone
        if in_zone:
            zone_depth += stripped.count('(') - stripped.count(')')

            if in_target_zone and '(filled_polygon' in stripped:
                count += 1

            # Zone block ended
            if zone_depth <= 0:
                in_zone = False
                in_target_zone = False
                zone_depth = 0

    return count


def parse_drc_json(drc_json_text):
    """Parse kicad-cli DRC JSON output for unconnected items.

    Returns dict with:
        'unconnected_count': int - number of unconnected items
        'violation_count': int - number of DRC violations
        'parse_error': str or None - error message if parsing failed
    """
    results = {
        "unconnected_count": None,
        "violation_count": None,
        "parse_error": None,
    }

    try:
        data = json.loads(drc_json_text)

        # Count unconnected items
        unconnected = data.get("unconnected_items", [])
        results["unconnected_count"] = len(unconnected)

        # Count violations
        violations = data.get("violations", [])
        results["violation_count"] = len(violations)

    except json.JSONDecodeError as e:
        results["parse_error"] = f"Failed to parse DRC JSON: {e}"
    except Exception as e:
        results["parse_error"] = f"Unexpected error parsing DRC: {e}"

    return results