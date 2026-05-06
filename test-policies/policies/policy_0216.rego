package access.validation.action.validate.policy_0216

# Auto-generated policy 216 (Rego v1 syntax)
# Package: access.validation.action.validate

# Metadata
metadata := {
    "policy_id": "0216",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0216_allowed if {
    input.user.active
    input.resource.public
}
default policy_0216_allowed = false
policy_0216_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0216_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
