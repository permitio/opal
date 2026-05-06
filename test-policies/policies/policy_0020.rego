package access.validation.action.allow.policy_0020

# Auto-generated policy 20 (Rego v1 syntax)
# Package: access.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0020",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0020_allowed = false
policy_0020_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0020_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
