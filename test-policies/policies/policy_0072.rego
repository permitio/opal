package compliance.authorization.action.check.data.policy_0072

# Auto-generated policy 72 (Rego v1 syntax)
# Package: compliance.authorization.action.check.data

# Metadata
metadata := {
    "policy_id": "0072",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0072_allowed = false
policy_0072_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0072_allowed if {
    data.policies.compliance.enabled
}
