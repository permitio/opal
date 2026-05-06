package risk.enforcement.action.validate.helpers.policy_0411

# Auto-generated policy 411
# Package: risk.enforcement.action.validate.helpers

# Metadata
metadata := {
    "policy_id": "0411",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0411_allowed if {
    data.policies.risk.enabled
}
policy_0411_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0411_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
