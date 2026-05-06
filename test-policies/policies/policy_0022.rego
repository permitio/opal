package security.monitoring.user.verify.policy_0022

# Auto-generated policy 22
# Package: security.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0022",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0022_allowed if {
    input.user.active
    input.resource.public
}
policy_0022_allowed if {
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
