package risk.authorization.policy.check.policy_0508

# Auto-generated policy 508
# Package: risk.authorization.policy.check

# Metadata
metadata := {
    "policy_id": "0508",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0508_allowed if {
    input.user.role == "admin"
}
policy_0508_allowed if {
    data.policies.risk.enabled
}
policy_0508_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0508_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
