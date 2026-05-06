package audit.authorization.context.verify.policy_0490

# Auto-generated policy 490
# Package: audit.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0490",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0490_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0490_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0490_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
