package audit.monitoring.resource.check.policy_0662

# Auto-generated policy 662
# Package: audit.monitoring.resource.check

# Metadata
metadata := {
    "policy_id": "0662",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0662_allowed if {
    input.user.role == "admin"
}
policy_0662_allowed if {
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
