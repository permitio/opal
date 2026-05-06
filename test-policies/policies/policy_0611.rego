package security.authentication.resource.check.policy_0611

# Auto-generated policy 611
# Package: security.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0611",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0611_allowed if {
    input.user.role == "admin"
}
policy_0611_allowed if {
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
