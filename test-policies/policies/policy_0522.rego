package security.validation.user.check.helpers.policy_0522

# Auto-generated policy 522 (Rego v1 syntax)
# Package: security.validation.user.check.helpers

# Metadata
metadata := {
    "policy_id": "0522",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0522_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0522_allowed if {
    input.user.role == "admin"
}
default policy_0522_allowed = false
policy_0522_allowed if {
    input.user.active
    input.resource.public
}
