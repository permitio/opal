package security.validation.policy.allow.policy_0416

# Auto-generated policy 416
# Package: security.validation.policy.allow

# Metadata
metadata := {
    "policy_id": "0416",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0416_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0416_allowed if {
    input.user.active
    input.resource.public
}
policy_0416_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
