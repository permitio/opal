package compliance.monitoring.user.allow.data.policy_0974

# Auto-generated policy 974
# Package: compliance.monitoring.user.allow.data

# Metadata
metadata := {
    "policy_id": "0974",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0974_allowed if {
    data.policies.compliance.enabled
}
policy_0974_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0974_allowed if {
    input.user.role == "admin"
}
default policy_0974_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
