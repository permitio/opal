package governance.monitoring.action.check.logic.policy_0648

# Auto-generated policy 648
# Package: governance.monitoring.action.check.logic

# Metadata
metadata := {
    "policy_id": "0648",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0648_allowed if {
    data.policies.governance.enabled
}
default policy_0648_allowed = false
policy_0648_allowed if {
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
