package access.authentication.resource.verify.policy_0155

# Auto-generated policy 155
# Package: access.authentication.resource.verify

# Metadata
metadata := {
    "policy_id": "0155",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0155_allowed if {
    input.user.role == "admin"
}
default policy_0155_allowed = false
policy_0155_allowed if {
    data.policies.access.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
