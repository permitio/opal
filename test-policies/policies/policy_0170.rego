package risk.authorization.user.verify.policy_0170

# Auto-generated policy 170
# Package: risk.authorization.user.verify

# Metadata
metadata := {
    "policy_id": "0170",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0170_allowed if {
    data.policies.risk.enabled
}
policy_0170_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0170_allowed if {
    input.user.role == "admin"
}
policy_0170_denied if {
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
