package access.authentication.policy.deny.policy_0271

# Auto-generated policy 271
# Package: access.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0271",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0271_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0271_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0271_allowed if {
    input.user.role == "admin"
}
policy_0271_allowed if {
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
