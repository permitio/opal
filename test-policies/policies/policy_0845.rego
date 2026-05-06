package audit.monitoring.context.validate.policy_0845

# Auto-generated policy 845 (Rego v1 syntax)
# Package: audit.monitoring.context.validate

# Metadata
metadata := {
    "policy_id": "0845",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0845_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0845_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
