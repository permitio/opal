package security.monitoring.action.validate.policy_0223

# Auto-generated policy 223 (Rego v1 syntax)
# Package: security.monitoring.action.validate

# Metadata
metadata := {
    "policy_id": "0223",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0223_allowed = false
policy_0223_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0223_allowed if {
    input.user.role == "admin"
}
policy_0223_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
