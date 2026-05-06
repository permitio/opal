package security.validation.action.validate.policy_0374

# Auto-generated policy 374 (Rego v1 syntax)
# Package: security.validation.action.validate

# Metadata
metadata := {
    "policy_id": "0374",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0374_allowed if {
    input.user.role == "admin"
}
default policy_0374_allowed = false
policy_0374_allowed if {
    input.user.active
    input.resource.public
}
