package risk.authorization.action.verify.policy_0507

# Auto-generated policy 507
# Package: risk.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0507",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0507_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0507_allowed if {
    input.user.role == "admin"
}
policy_0507_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
