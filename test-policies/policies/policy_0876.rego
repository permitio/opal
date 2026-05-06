package governance.enforcement.action.validate.policy_0876

# Auto-generated policy 876
# Package: governance.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0876",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0876_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0876_allowed if {
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
