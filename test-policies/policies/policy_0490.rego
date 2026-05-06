package compliance.monitoring.policy.validate.logic.policy_0490

# Auto-generated policy 490 (Rego v1 syntax)
# Package: compliance.monitoring.policy.validate.logic

# Metadata
metadata := {
    "policy_id": "0490",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0490_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0490_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
