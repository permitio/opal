package access.authorization.user.validate.policy_0114

# Auto-generated policy 114 (Rego v1 syntax)
# Package: access.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0114",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0114_allowed = false
policy_0114_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0114_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
