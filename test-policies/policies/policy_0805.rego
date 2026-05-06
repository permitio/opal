package security.monitoring.action.check.policy_0805

# Auto-generated policy 805 (Rego v1 syntax)
# Package: security.monitoring.action.check

# Metadata
metadata := {
    "policy_id": "0805",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0805_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0805_allowed if {
    input.user.active
    input.resource.public
}
policy_0805_allowed if {
    data.policies.security.enabled
}
policy_0805_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
