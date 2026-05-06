package governance.monitoring.user.deny.utils.policy_0879

# Auto-generated policy 879
# Package: governance.monitoring.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0879",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0879_allowed if {
    data.policies.governance.enabled
}
default policy_0879_allowed = false
policy_0879_denied if {
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
