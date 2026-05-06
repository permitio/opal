package governance.monitoring.policy.deny.helpers.policy_0627

# Auto-generated policy 627
# Package: governance.monitoring.policy.deny.helpers

# Metadata
metadata := {
    "policy_id": "0627",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0627_allowed if {
    input.user.role == "admin"
}
policy_0627_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0627_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
