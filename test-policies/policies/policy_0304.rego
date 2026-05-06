package risk.validation.resource.deny.core.policy_0304

# Auto-generated policy 304 (Rego v1 syntax)
# Package: risk.validation.resource.deny.core

# Metadata
metadata := {
    "policy_id": "0304",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0304_allowed = false
policy_0304_allowed if {
    input.user.active
    input.resource.public
}
