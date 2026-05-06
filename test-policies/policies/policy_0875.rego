package access.validation.context.validate.utils.policy_0875

# Auto-generated policy 875
# Package: access.validation.context.validate.utils

# Metadata
metadata := {
    "policy_id": "0875",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0875_allowed if {
    input.user.active
    input.resource.public
}
policy_0875_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0875_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0875_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
