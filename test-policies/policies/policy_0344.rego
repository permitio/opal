package access.enforcement.policy.deny.policy_0344

# Auto-generated policy 344
# Package: access.enforcement.policy.deny

# Metadata
metadata := {
    "policy_id": "0344",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0344_allowed if {
    data.policies.access.enabled
}
policy_0344_allowed if {
    input.user.role == "admin"
}
default policy_0344_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
