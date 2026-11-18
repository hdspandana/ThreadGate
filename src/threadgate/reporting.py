"""Privacy-minimised case exports. Raw emails and destination values excluded."""
from datetime import datetime, timezone


def case_report(result, verification_status=None):
    return {
        'format': 'threadgate.case-report.v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'case_id': result.case_id,
        'vendor_id': result.vendor_id,
        'gate_decision': result.decision.decision,
        'workflow_status': verification_status or result.decision.attestation_status,
        'reference_version': result.decision.reference_version,
        'reference_state': result.decision.reference_state,
        'extractor': result.extractor,
        'model_error': bool(result.error),
        'elapsed_ms': round(result.elapsed_ms, 2),
        'controls': [{'code': f.code, 'severity': f.severity,
                      'model_independent': f.independent_of_model}
                     for f in result.decision.findings],
        'changed_fields': [d.field for d in result.decision.diffs if d.changed],
        'privacy': 'Raw email, evidence quotes, contacts and destination values omitted.',
        'limitations': 'Prototype. No payment execution. Demo attestations do not establish identity.',
    }
