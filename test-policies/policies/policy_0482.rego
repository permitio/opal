package access.authorization.policy.check.helpers.policy_0482

# Auto-generated policy 482 (Rego v1 syntax)
# Package: access.authorization.policy.check.helpers

# Metadata
metadata := {
    "policy_id": "0482",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0482_allowed if {
    data.policies.access.enabled
}
policy_0482_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0482_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0482_allowed if {
    input.user.role == "admin"
}
