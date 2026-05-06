package compliance.monitoring.user.verify.data.policy_0352

# Auto-generated policy 352 (Rego v1 syntax)
# Package: compliance.monitoring.user.verify.data

# Metadata
metadata := {
    "policy_id": "0352",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0352_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0352_allowed = false
policy_0352_allowed if {
    data.policies.compliance.enabled
}
