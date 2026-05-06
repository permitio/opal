package security.monitoring.action.check.policy_0011

# Auto-generated policy 11 (Rego v1 syntax)
# Package: security.monitoring.action.check

# Metadata
metadata := {
    "policy_id": "0011",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0011_allowed if {
    input.user.role == "admin"
}
policy_0011_allowed if {
    input.user.active
    input.resource.public
}
policy_0011_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0011_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
