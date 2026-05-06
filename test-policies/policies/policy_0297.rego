package security.validation.context.allow.policy_0297

# Auto-generated policy 297
# Package: security.validation.context.allow

# Metadata
metadata := {
    "policy_id": "0297",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0297_allowed if {
    input.user.active
    input.resource.public
}
policy_0297_allowed if {
    input.user.role == "admin"
}
policy_0297_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0297_denied if {
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
