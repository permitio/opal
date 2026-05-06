package security.authentication.context.allow.data.policy_0702

# Auto-generated policy 702
# Package: security.authentication.context.allow.data

# Metadata
metadata := {
    "policy_id": "0702",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0702_allowed if {
    input.user.role == "admin"
}
policy_0702_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0702_approved if {
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
