package access.authentication.user.validate.policy_0185

# Auto-generated policy 185 (Rego v1 syntax)
# Package: access.authentication.user.validate

# Metadata
metadata := {
    "policy_id": "0185",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0185_allowed = false
policy_0185_allowed if {
    input.user.role == "admin"
}
policy_0185_allowed if {
    input.user.active
    input.resource.public
}
policy_0185_allowed if {
    data.policies.access.enabled
}
