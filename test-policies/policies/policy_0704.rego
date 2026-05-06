package compliance.authentication.user.check.data.policy_0704

# Auto-generated policy 704
# Package: compliance.authentication.user.check.data

# Metadata
metadata := {
    "policy_id": "0704",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0704_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0704_allowed = false
policy_0704_allowed if {
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
