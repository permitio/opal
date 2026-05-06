package access.validation.user.deny.policy_0539

# Auto-generated policy 539
# Package: access.validation.user.deny

# Metadata
metadata := {
    "policy_id": "0539",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0539_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0539_allowed = false
policy_0539_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0539_allowed if {
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
