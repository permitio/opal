package compliance.authentication.policy.deny.policy_0219

# Auto-generated policy 219
# Package: compliance.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0219",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0219_allowed = false
policy_0219_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
