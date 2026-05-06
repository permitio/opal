package compliance.monitoring.context.check.policy_0904

# Auto-generated policy 904
# Package: compliance.monitoring.context.check

# Metadata
metadata := {
    "policy_id": "0904",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0904_allowed if {
    input.user.active
    input.resource.public
}
policy_0904_denied if {
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
