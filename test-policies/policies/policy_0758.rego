package compliance.authorization.action.check.data.policy_0758

# Auto-generated policy 758
# Package: compliance.authorization.action.check.data

# Metadata
metadata := {
    "policy_id": "0758",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0758_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0758_allowed = false
policy_0758_denied if {
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
