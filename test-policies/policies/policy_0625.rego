package compliance.authentication.policy.validate.policy_0625

# Auto-generated policy 625
# Package: compliance.authentication.policy.validate

# Metadata
metadata := {
    "policy_id": "0625",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0625_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0625_allowed if {
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
