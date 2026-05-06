package governance.authorization.policy.verify.policy_0993

# Auto-generated policy 993
# Package: governance.authorization.policy.verify

# Metadata
metadata := {
    "policy_id": "0993",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0993_allowed if {
    input.user.role == "admin"
}
policy_0993_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0993_denied if {
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
