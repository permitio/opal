package access.enforcement.resource.allow.policy_0678

# Auto-generated policy 678 (Rego v1 syntax)
# Package: access.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0678",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0678_allowed if {
    input.user.role == "admin"
}
policy_0678_allowed if {
    input.user.active
    input.resource.public
}
default policy_0678_allowed = false
policy_0678_allowed if {
    data.policies.access.enabled
}
