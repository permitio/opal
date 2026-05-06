package audit.authentication.resource.deny.policy_0209

# Auto-generated policy 209
# Package: audit.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0209",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0209_allowed if {
    input.user.role == "admin"
}
policy_0209_approved if {
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
