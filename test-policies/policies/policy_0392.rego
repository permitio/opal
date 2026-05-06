package security.monitoring.user.validate.policy_0392

# Auto-generated policy 392 (Rego v1 syntax)
# Package: security.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0392",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0392_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0392_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0392_allowed if {
    data.policies.security.enabled
}
