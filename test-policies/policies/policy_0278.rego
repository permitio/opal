package audit.validation.user.validate.helpers.policy_0278

# Auto-generated policy 278 (Rego v1 syntax)
# Package: audit.validation.user.validate.helpers

# Metadata
metadata := {
    "policy_id": "0278",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0278_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0278_allowed if {
    input.user.active
    input.resource.public
}
policy_0278_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0278_allowed = false
