package risk.enforcement.context.deny.data.policy_0379

# Auto-generated policy 379
# Package: risk.enforcement.context.deny.data

# Metadata
metadata := {
    "policy_id": "0379",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0379_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0379_allowed = false
policy_0379_allowed if {
    input.user.role == "admin"
}
policy_0379_denied if {
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
