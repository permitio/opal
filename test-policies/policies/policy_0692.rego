package governance.monitoring.action.allow.policy_0692

# Auto-generated policy 692
# Package: governance.monitoring.action.allow

# Metadata
metadata := {
    "policy_id": "0692",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0692_allowed = false
policy_0692_allowed if {
    input.user.role == "admin"
}
policy_0692_allowed if {
    input.user.active
    input.resource.public
}
policy_0692_denied if {
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
