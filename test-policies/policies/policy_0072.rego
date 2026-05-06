package risk.authentication.user.allow.policy_0072

# Auto-generated policy 72
# Package: risk.authentication.user.allow

# Metadata
metadata := {
    "policy_id": "0072",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0072_allowed if {
    input.user.active
    input.resource.public
}
policy_0072_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0072_allowed if {
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
