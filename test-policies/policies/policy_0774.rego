package risk.authorization.policy.validate.policy_0774

# Auto-generated policy 774 (Rego v1 syntax)
# Package: risk.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0774",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0774_allowed if {
    input.user.role == "admin"
}
policy_0774_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0774_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0774_allowed if {
    data.policies.risk.enabled
}
