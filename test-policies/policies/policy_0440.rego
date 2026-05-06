package compliance.enforcement.user.check.policy_0440

# Auto-generated policy 440
# Package: compliance.enforcement.user.check

# Metadata
metadata := {
    "policy_id": "0440",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0440_allowed if {
    input.user.role == "admin"
}
policy_0440_allowed if {
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
