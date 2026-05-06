package governance.authorization.action.check.helpers.policy_0100

# Auto-generated policy 100 (Rego v1 syntax)
# Package: governance.authorization.action.check.helpers

# Metadata
metadata := {
    "policy_id": "0100",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0100_allowed if {
    input.user.role == "admin"
}
policy_0100_allowed if {
    data.policies.governance.enabled
}
policy_0100_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
