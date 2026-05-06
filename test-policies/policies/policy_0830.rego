package access.authorization.context.allow.core.policy_0830

# Auto-generated policy 830
# Package: access.authorization.context.allow.core

# Metadata
metadata := {
    "policy_id": "0830",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0830_allowed if {
    input.user.active
    input.resource.public
}
policy_0830_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0830_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0830_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
