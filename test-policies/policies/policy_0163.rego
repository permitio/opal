package security.enforcement.resource.allow.data.policy_0163

# Auto-generated policy 163 (Rego v1 syntax)
# Package: security.enforcement.resource.allow.data

# Metadata
metadata := {
    "policy_id": "0163",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0163_allowed if {
    input.user.active
    input.resource.public
}
policy_0163_allowed if {
    data.policies.security.enabled
}
default policy_0163_allowed = false
policy_0163_allowed if {
    input.user.role == "admin"
}
