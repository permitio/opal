package access.enforcement.user.allow.helpers.policy_0981

# Auto-generated policy 981 (Rego v1 syntax)
# Package: access.enforcement.user.allow.helpers

# Metadata
metadata := {
    "policy_id": "0981",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0981_allowed if {
    data.policies.access.enabled
}
default policy_0981_allowed = false
policy_0981_allowed if {
    input.user.role == "admin"
}
policy_0981_allowed if {
    input.user.active
    input.resource.public
}
