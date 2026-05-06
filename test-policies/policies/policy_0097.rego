package audit.validation.user.verify.utils.policy_0097

# Auto-generated policy 97 (Rego v1 syntax)
# Package: audit.validation.user.verify.utils

# Metadata
metadata := {
    "policy_id": "0097",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0097_allowed = false
policy_0097_allowed if {
    input.user.active
    input.resource.public
}
