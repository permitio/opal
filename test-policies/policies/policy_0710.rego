package compliance.authorization.policy.check.policy_0710

# Auto-generated policy 710
# Package: compliance.authorization.policy.check

# Metadata
metadata := {
    "policy_id": "0710",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0710_allowed = false
policy_0710_allowed if {
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
