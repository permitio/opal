package audit.monitoring.user.check.policy_0132

# Auto-generated policy 132 (Rego v1 syntax)
# Package: audit.monitoring.user.check

# Metadata
metadata := {
    "policy_id": "0132",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0132_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0132_allowed if {
    input.user.active
    input.resource.public
}
policy_0132_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0132_allowed if {
    data.policies.audit.enabled
}
