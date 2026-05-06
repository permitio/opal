package compliance.validation.user.allow.policy_0384

# Auto-generated policy 384 (Rego v1 syntax)
# Package: compliance.validation.user.allow

# Metadata
metadata := {
    "policy_id": "0384",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0384_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0384_allowed if {
    data.policies.compliance.enabled
}
