package compliance.authentication.action.deny.data.policy_0520

# Auto-generated policy 520
# Package: compliance.authentication.action.deny.data

# Metadata
metadata := {
    "policy_id": "0520",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0520_allowed = false
policy_0520_allowed if {
    data.policies.compliance.enabled
}
policy_0520_allowed if {
    input.user.role == "admin"
}
policy_0520_denied if {
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
