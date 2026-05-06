package audit.monitoring.policy.validate.data.policy_0569

# Auto-generated policy 569 (Rego v1 syntax)
# Package: audit.monitoring.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0569",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0569_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0569_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0569_allowed if {
    input.user.active
    input.resource.public
}
