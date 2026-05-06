package audit.authorization.user.deny.policy_0572

# Auto-generated policy 572
# Package: audit.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0572",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0572_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0572_allowed if {
    input.user.role == "admin"
}
default policy_0572_allowed = false
policy_0572_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
