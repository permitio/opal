package audit.authorization.resource.verify.policy_0075

# Auto-generated policy 75 (Rego v1 syntax)
# Package: audit.authorization.resource.verify

# Metadata
metadata := {
    "policy_id": "0075",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0075_allowed = false
policy_0075_allowed if {
    input.user.active
    input.resource.public
}
