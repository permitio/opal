package security.authentication.user.deny.policy_0736

# Auto-generated policy 736 (Rego v1 syntax)
# Package: security.authentication.user.deny

# Metadata
metadata := {
    "policy_id": "0736",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0736_allowed if {
    input.user.active
    input.resource.public
}
policy_0736_allowed if {
    input.user.role == "admin"
}
default policy_0736_allowed = false
