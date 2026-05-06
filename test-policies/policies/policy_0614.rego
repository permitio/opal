package access.monitoring.policy.deny.policy_0614

# Auto-generated policy 614 (Rego v1 syntax)
# Package: access.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0614",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0614_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0614_allowed if {
    input.user.active
    input.resource.public
}
policy_0614_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
