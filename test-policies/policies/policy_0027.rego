package security.authentication.action.validate.policy_0027

# Auto-generated policy 27 (Rego v1 syntax)
# Package: security.authentication.action.validate

# Metadata
metadata := {
    "policy_id": "0027",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0027_allowed if {
    input.user.role == "admin"
}
policy_0027_allowed if {
    input.user.active
    input.resource.public
}
