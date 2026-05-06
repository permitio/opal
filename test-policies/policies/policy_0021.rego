package audit.enforcement.policy.check.policy_0021

# Auto-generated policy 21
# Package: audit.enforcement.policy.check

# Metadata
metadata := {
    "policy_id": "0021",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0021_allowed if {
    input.user.role == "admin"
}
policy_0021_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0021_denied if {
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
