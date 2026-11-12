"""DICOM TID 10011 tree walker retained from v1; dose units are UCUM codes."""
def _safe_str(x):
    return str(x).strip() if x is not None else ""
def _safe_float(x):
    try: return float(x)
    except (TypeError, ValueError): return 0.0

_DCM_CODES = {
    "113769": "event_uid",
    "113813": "dlp_total",
    "113830": "ctdivol",
    "113838": "dlp",
    "113835": "phantom_type",
    "113825": "scan_length",
    "113826": "collimation_single",
    "113827": "collimation_total",
    "113828": "pitch",
    "113824": "exposure_time",
    "113733": "kvp",
    "113734": "tube_current",
    "113833": "tube_current_max",
    "113834": "rotation_time",
    "113820": "acquisition_type",
    "125203": "acquisition_protocol",
    "123014": "target_region",
    "113809": "start_irradiation",
    "113810": "end_irradiation",
    "113812": "num_irradiation_events",
    "121106": "comment",
}

def _walk_sr(seq, results: list, current: dict):
    for item in seq:
        code_seq  = getattr(item, "ConceptNameCodeSequence", None)
        code      = _safe_str(code_seq[0].CodeValue) if code_seq else ""
        val_type  = _safe_str(getattr(item, "ValueType", ""))
        rel_type  = _safe_str(getattr(item, "RelationshipType", ""))

        scheme = _safe_str(getattr(code_seq[0], 'CodingSchemeDesignator', '')) if code_seq else ''
        key = _DCM_CODES.get(code, "") if scheme == 'DCM' else ''

        if val_type == "NUM" and key:
            mvs = getattr(item, "MeasuredValueSequence", None)
            if mvs:
                num_val  = _safe_float(getattr(mvs[0], "NumericValue", 0))
                unit_seq = getattr(mvs[0], "MeasurementUnitsCodeSequence", None)
                unit     = _safe_str(unit_seq[0].CodeValue) if unit_seq and _safe_str(getattr(unit_seq[0], 'CodingSchemeDesignator', '')) == 'UCUM' else ""
                current[key] = (num_val, unit)

        elif val_type in ("TEXT", "UIDREF") and key:
            current[key] = _safe_str(getattr(item, "UID", "") if val_type == "UIDREF" else getattr(item, "TextValue", ""))

        elif val_type == "CODE" and key:
            ccs = getattr(item, "ConceptCodeSequence", None)
            if ccs:
                current[key] = _safe_str(ccs[0].CodeMeaning)

        elif val_type == "DATETIME" and key:
            current[key] = _safe_str(getattr(item, "DateTime", ""))

        # Container: CT Acquisition → push new acquisition dict
        if val_type == "CONTAINER":
            cns = getattr(item, "ConceptNameCodeSequence", None)
            cname = _safe_str(cns[0].CodeValue if cns else "")
            child_content = getattr(item, "ContentSequence", None)
            if cname == "113819" and scheme == 'DCM':   # CT Acquisition
                acq = {}
                if child_content:
                    _walk_sr(child_content, results, acq)
                results.append(acq)
            elif child_content:
                _walk_sr(child_content, results, current)
        else:
            child_content = getattr(item, "ContentSequence", None)
            if child_content:
                _walk_sr(child_content, results, current)


def parse_dose_sr(ds) -> dict:
    content = getattr(ds, "ContentSequence", [])
    summary = {}
    acquisitions = []
    _walk_sr(content, acquisitions, summary)
    return {"summary": summary, "acquisitions": acquisitions}


