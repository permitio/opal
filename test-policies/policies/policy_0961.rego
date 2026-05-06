package risk.authentication.policy.validate.policy_0961

# Auto-generated policy 961
# Package: risk.authentication.policy.validate

# Metadata
metadata := {
    "policy_id": "0961",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0961_allowed if {
    input.user.role == "admin"
}
policy_0961_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0961_allowed if {
    data.policies.risk.enabled
}
policy_0961_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
