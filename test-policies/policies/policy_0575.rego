package compliance.monitoring.context.allow.logic.policy_0575

# Auto-generated policy 575
# Package: compliance.monitoring.context.allow.logic

# Metadata
metadata := {
    "policy_id": "0575",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0575_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0575_allowed if {
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
