package security.authentication.context.validate.policy_0504

# Auto-generated policy 504 (Rego v1 syntax)
# Package: security.authentication.context.validate

# Metadata
metadata := {
    "policy_id": "0504",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0504_allowed if {
    input.user.active
    input.resource.public
}
policy_0504_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0504_allowed = false
policy_0504_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
