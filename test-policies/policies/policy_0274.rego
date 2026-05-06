package access.validation.policy.check.data.policy_0274

# Auto-generated policy 274 (Rego v1 syntax)
# Package: access.validation.policy.check.data

# Metadata
metadata := {
    "policy_id": "0274",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0274_allowed = false
policy_0274_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0274_allowed if {
    data.policies.access.enabled
}
