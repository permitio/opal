package security.enforcement.resource.deny.policy_0175

# Auto-generated policy 175 (Rego v1 syntax)
# Package: security.enforcement.resource.deny

# Metadata
metadata := {
    "policy_id": "0175",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0175_allowed = false
policy_0175_allowed if {
    input.user.active
    input.resource.public
}
