package risk.authorization.action.check.policy_0092

# Auto-generated policy 92
# Package: risk.authorization.action.check

# Metadata
metadata := {
    "policy_id": "0092",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0092_allowed if {
    input.user.role == "admin"
}
default policy_0092_allowed = false
policy_0092_allowed if {
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
