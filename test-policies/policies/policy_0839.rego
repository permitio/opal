package access.authorization.action.allow.policy_0839

# Auto-generated policy 839 (Rego v1 syntax)
# Package: access.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0839",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0839_allowed = false
policy_0839_allowed if {
    data.policies.access.enabled
}
policy_0839_allowed if {
    input.user.active
    input.resource.public
}
policy_0839_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
