package audit.authentication.policy.validate.data.policy_0124

# Auto-generated policy 124
# Package: audit.authentication.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0124",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0124_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0124_allowed if {
    input.user.active
    input.resource.public
}
policy_0124_denied if {
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
