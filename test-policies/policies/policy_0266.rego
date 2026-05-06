package access.validation.user.validate.policy_0266

# Auto-generated policy 266 (Rego v1 syntax)
# Package: access.validation.user.validate

# Metadata
metadata := {
    "policy_id": "0266",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0266_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0266_allowed = false
policy_0266_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
