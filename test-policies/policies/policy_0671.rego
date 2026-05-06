package access.authorization.action.check.policy_0671

# Auto-generated policy 671
# Package: access.authorization.action.check

# Metadata
metadata := {
    "policy_id": "0671",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0671_allowed = false
policy_0671_allowed if {
    input.user.active
    input.resource.public
}
policy_0671_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0671_denied if {
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
