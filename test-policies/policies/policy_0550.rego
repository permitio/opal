package security.authentication.user.deny.policy_0550

# Auto-generated policy 550 (Rego v1 syntax)
# Package: security.authentication.user.deny

# Metadata
metadata := {
    "policy_id": "0550",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0550_allowed = false
policy_0550_allowed if {
    input.user.active
    input.resource.public
}
