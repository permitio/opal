package audit.authentication.action.deny.data.policy_0249

# Auto-generated policy 249
# Package: audit.authentication.action.deny.data

# Metadata
metadata := {
    "policy_id": "0249",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0249_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0249_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
