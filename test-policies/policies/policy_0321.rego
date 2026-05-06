package compliance.enforcement.user.validate.policy_0321

# Auto-generated policy 321
# Package: compliance.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0321",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0321_allowed if {
    input.user.active
    input.resource.public
}
policy_0321_allowed if {
    data.policies.compliance.enabled
}
policy_0321_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
