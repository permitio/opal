package risk.authentication.context.check.policy_0489

# Auto-generated policy 489
# Package: risk.authentication.context.check

# Metadata
metadata := {
    "policy_id": "0489",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0489_allowed if {
    data.policies.risk.enabled
}
policy_0489_denied if {
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
