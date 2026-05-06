package security.authentication.user.verify.data.policy_0777

# Auto-generated policy 777 (Rego v1 syntax)
# Package: security.authentication.user.verify.data

# Metadata
metadata := {
    "policy_id": "0777",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0777_allowed if {
    input.user.active
    input.resource.public
}
default policy_0777_allowed = false
