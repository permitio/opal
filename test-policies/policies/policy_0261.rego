package compliance.enforcement.action.allow.logic.policy_0261

# Auto-generated policy 261
# Package: compliance.enforcement.action.allow.logic

# Metadata
metadata := {
    "policy_id": "0261",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0261_allowed if {
    input.user.role == "admin"
}
policy_0261_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0261_denied if {
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
