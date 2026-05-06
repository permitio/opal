package access.monitoring.context.verify.policy_0782

# Auto-generated policy 782 (Rego v1 syntax)
# Package: access.monitoring.context.verify

# Metadata
metadata := {
    "policy_id": "0782",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0782_allowed if {
    input.user.role == "admin"
}
policy_0782_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0782_allowed if {
    data.policies.access.enabled
}
policy_0782_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
