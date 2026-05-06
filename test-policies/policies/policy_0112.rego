package governance.enforcement.user.deny.data.policy_0112

# Auto-generated policy 112 (Rego v1 syntax)
# Package: governance.enforcement.user.deny.data

# Metadata
metadata := {
    "policy_id": "0112",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0112_allowed if {
    input.user.active
    input.resource.public
}
default policy_0112_allowed = false
