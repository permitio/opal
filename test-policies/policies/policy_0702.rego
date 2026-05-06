package access.authorization.resource.verify.policy_0702

# Auto-generated policy 702 (Rego v1 syntax)
# Package: access.authorization.resource.verify

# Metadata
metadata := {
    "policy_id": "0702",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0702_allowed if {
    input.user.role == "admin"
}
default policy_0702_allowed = false
policy_0702_allowed if {
    input.user.active
    input.resource.public
}
