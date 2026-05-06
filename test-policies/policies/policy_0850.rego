package governance.monitoring.policy.verify.policy_0850

# Auto-generated policy 850
# Package: governance.monitoring.policy.verify

# Metadata
metadata := {
    "policy_id": "0850",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0850_allowed = false
policy_0850_denied if {
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
