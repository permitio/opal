package compliance.authentication.policy.allow.core.policy_0032

# Auto-generated policy 32
# Package: compliance.authentication.policy.allow.core

# Metadata
metadata := {
    "policy_id": "0032",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0032_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0032_allowed if {
    input.user.role == "admin"
}
policy_0032_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
