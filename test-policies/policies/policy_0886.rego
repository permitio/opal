package risk.monitoring.action.check.policy_0886

# Auto-generated policy 886
# Package: risk.monitoring.action.check

# Metadata
metadata := {
    "policy_id": "0886",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0886_allowed if {
    input.user.role == "admin"
}
default policy_0886_allowed = false
policy_0886_allowed if {
    data.policies.risk.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
