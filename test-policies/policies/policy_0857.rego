package security.authorization.context.deny.helpers.policy_0857

# Auto-generated policy 857 (Rego v1 syntax)
# Package: security.authorization.context.deny.helpers

# Metadata
metadata := {
    "policy_id": "0857",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0857_allowed if {
    data.policies.security.enabled
}
policy_0857_allowed if {
    input.user.role == "admin"
}
policy_0857_allowed if {
    input.user.active
    input.resource.public
}
