package audit.authorization.action.deny.core.policy_0598

# Auto-generated policy 598
# Package: audit.authorization.action.deny.core

# Metadata
metadata := {
    "policy_id": "0598",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0598_allowed if {
    data.policies.audit.enabled
}
policy_0598_allowed if {
    input.user.role == "admin"
}
policy_0598_denied if {
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
