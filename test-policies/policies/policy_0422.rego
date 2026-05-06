package compliance.authorization.user.check.policy_0422

# Auto-generated policy 422 (Rego v1 syntax)
# Package: compliance.authorization.user.check

# Metadata
metadata := {
    "policy_id": "0422",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0422_allowed = false
policy_0422_allowed if {
    data.policies.compliance.enabled
}
policy_0422_allowed if {
    input.user.role == "admin"
}
policy_0422_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
