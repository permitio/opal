package access.authorization.user.validate.core.policy_0774

# Auto-generated policy 774
# Package: access.authorization.user.validate.core

# Metadata
metadata := {
    "policy_id": "0774",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0774_allowed = false
policy_0774_allowed if {
    input.user.active
    input.resource.public
}
policy_0774_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0774_approved if {
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
