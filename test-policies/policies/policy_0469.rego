package risk.authentication.context.allow.logic.policy_0469

# Auto-generated policy 469
# Package: risk.authentication.context.allow.logic

# Metadata
metadata := {
    "policy_id": "0469",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0469_allowed if {
    data.policies.risk.enabled
}
policy_0469_denied if {
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
