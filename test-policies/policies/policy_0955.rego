package access.validation.context.validate.core.policy_0955

# Auto-generated policy 955
# Package: access.validation.context.validate.core

# Metadata
metadata := {
    "policy_id": "0955",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0955_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0955_denied if {
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
