package access.monitoring.resource.deny.policy_0156

# Auto-generated policy 156
# Package: access.monitoring.resource.deny

# Metadata
metadata := {
    "policy_id": "0156",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0156_allowed if {
    input.user.active
    input.resource.public
}
policy_0156_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0156_denied if {
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
