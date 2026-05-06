package security.enforcement.user.verify.utils.policy_0197

# Auto-generated policy 197 (Rego v1 syntax)
# Package: security.enforcement.user.verify.utils

# Metadata
metadata := {
    "policy_id": "0197",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0197_allowed if {
    input.user.active
    input.resource.public
}
default policy_0197_allowed = false
