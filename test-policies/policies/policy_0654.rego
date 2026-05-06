package compliance.authorization.policy.allow.data.policy_0654

# Auto-generated policy 654
# Package: compliance.authorization.policy.allow.data

# Metadata
metadata := {
    "policy_id": "0654",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0654_allowed = false
policy_0654_allowed if {
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
