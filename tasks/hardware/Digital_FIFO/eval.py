"""Evaluation helpers for Synchronous FIFO Design benchmark."""

import logging

logger = logging.getLogger(__name__)


def parse_simulation_output(sim_output):
    """Parse iverilog/vvp simulation output for pass/fail markers.

    Returns dict with:
        'basic_passed': bool - "All the basic tests passed!" found
        'hard_passed': bool - "All the hard tests passed!" found
        'errors': list of str - any $error messages
    """
    results = {
        "basic_passed": False,
        "hard_passed": False,
        "errors": [],
    }

    if sim_output is None:
        return results

    for line in sim_output.split('\n'):
        line = line.strip()

        if "All the basic tests passed!" in line:
            results["basic_passed"] = True
        elif "All the hard tests passed!" in line:
            results["hard_passed"] = True

        if "Failure:" in line or "$error" in line.lower():
            results["errors"].append(line)

    return results