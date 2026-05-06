package governance.authorization.action.deny.policy_0957

# Auto-generated policy 957
# Package: governance.authorization.action.deny

# Metadata
metadata := {
    "policy_id": "0957",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0957_allowed if {
    input.user.role == "admin"
}
policy_0957_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0957_approved if {
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
