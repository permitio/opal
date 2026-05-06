package audit.monitoring.resource.check.helpers.policy_0651

# Auto-generated policy 651
# Package: audit.monitoring.resource.check.helpers

# Metadata
metadata := {
    "policy_id": "0651",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0651_allowed if {
    input.user.role == "admin"
}
default policy_0651_allowed = false
policy_0651_allowed if {
    input.user.active
    input.resource.public
}
policy_0651_denied if {
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
