package access.enforcement.policy.deny.policy_0791

# Auto-generated policy 791
# Package: access.enforcement.policy.deny

# Metadata
metadata := {
    "policy_id": "0791",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0791_allowed if {
    input.user.role == "admin"
}
policy_0791_allowed if {
    data.policies.access.enabled
}
default policy_0791_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
