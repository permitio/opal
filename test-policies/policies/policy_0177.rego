package risk.validation.action.check.helpers.policy_0177

# Auto-generated policy 177
# Package: risk.validation.action.check.helpers

# Metadata
metadata := {
    "policy_id": "0177",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0177_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0177_allowed if {
    data.policies.risk.enabled
}
policy_0177_allowed if {
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
