package governance.monitoring.action.check.helpers.policy_0967

# Auto-generated policy 967
# Package: governance.monitoring.action.check.helpers

# Metadata
metadata := {
    "policy_id": "0967",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0967_allowed = false
policy_0967_allowed if {
    input.user.role == "admin"
}
policy_0967_denied if {
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
