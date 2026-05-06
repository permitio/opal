package audit.enforcement.resource.deny.policy_0069

# Auto-generated policy 69
# Package: audit.enforcement.resource.deny

# Metadata
metadata := {
    "policy_id": "0069",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0069_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0069_allowed if {
    data.policies.audit.enabled
}
policy_0069_allowed if {
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
