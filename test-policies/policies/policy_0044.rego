package access.monitoring.action.allow.policy_0044

# Auto-generated policy 44 (Rego v1 syntax)
# Package: access.monitoring.action.allow

# Metadata
metadata := {
    "policy_id": "0044",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0044_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0044_allowed if {
    data.policies.access.enabled
}
policy_0044_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
