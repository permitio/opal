package access.enforcement.policy.validate.policy_0165

# Auto-generated policy 165 (Rego v1 syntax)
# Package: access.enforcement.policy.validate

# Metadata
metadata := {
    "policy_id": "0165",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0165_allowed = false
policy_0165_allowed if {
    input.user.active
    input.resource.public
}
policy_0165_allowed if {
    input.user.role == "admin"
}
