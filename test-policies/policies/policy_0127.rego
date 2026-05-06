package governance.authentication.user.verify.policy_0127

# Auto-generated policy 127
# Package: governance.authentication.user.verify

# Metadata
metadata := {
    "policy_id": "0127",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0127_allowed if {
    data.policies.governance.enabled
}
policy_0127_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0127_allowed = false
policy_0127_denied if {
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
