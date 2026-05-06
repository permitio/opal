package security.enforcement.context.deny.core.policy_0399

# Auto-generated policy 399 (Rego v1 syntax)
# Package: security.enforcement.context.deny.core

# Metadata
metadata := {
    "policy_id": "0399",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0399_allowed if {
    input.user.role == "admin"
}
policy_0399_allowed if {
    input.user.active
    input.resource.public
}
policy_0399_allowed if {
    data.policies.security.enabled
}
