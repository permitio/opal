package governance.monitoring.resource.deny.core.policy_0518

# Auto-generated policy 518
# Package: governance.monitoring.resource.deny.core

# Metadata
metadata := {
    "policy_id": "0518",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0518_allowed if {
    input.user.role == "admin"
}
default policy_0518_allowed = false
policy_0518_denied if {
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
