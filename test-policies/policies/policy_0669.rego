package security.validation.action.allow.policy_0669

# Auto-generated policy 669
# Package: security.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0669",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0669_allowed if {
    input.user.role == "admin"
}
policy_0669_allowed if {
    input.user.active
    input.resource.public
}
policy_0669_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0669_denied if {
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
