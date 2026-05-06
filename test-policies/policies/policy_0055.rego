package audit.authorization.context.verify.policy_0055

# Auto-generated policy 55 (Rego v1 syntax)
# Package: audit.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0055",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0055_allowed if {
    input.user.role == "admin"
}
default policy_0055_allowed = false
policy_0055_allowed if {
    input.user.active
    input.resource.public
}
policy_0055_allowed if {
    data.policies.audit.enabled
}
