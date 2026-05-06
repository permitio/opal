package compliance.authorization.user.deny.policy_0302

# Auto-generated policy 302
# Package: compliance.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0302",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0302_allowed if {
    data.policies.compliance.enabled
}
policy_0302_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0302_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0302_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
