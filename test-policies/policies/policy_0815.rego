package security.validation.resource.allow.policy_0815

# Auto-generated policy 815
# Package: security.validation.resource.allow

# Metadata
metadata := {
    "policy_id": "0815",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0815_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0815_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0815_allowed = false
policy_0815_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
