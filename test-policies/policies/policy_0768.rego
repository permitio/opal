package access.validation.resource.verify.policy_0768

# Auto-generated policy 768 (Rego v1 syntax)
# Package: access.validation.resource.verify

# Metadata
metadata := {
    "policy_id": "0768",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0768_allowed = false
policy_0768_allowed if {
    input.user.active
    input.resource.public
}
