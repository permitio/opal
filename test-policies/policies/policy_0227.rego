package access.authentication.resource.deny.policy_0227

# Auto-generated policy 227
# Package: access.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0227",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0227_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0227_approved if {
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
