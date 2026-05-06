package security.validation.policy.check.policy_0035

# Auto-generated policy 35
# Package: security.validation.policy.check

# Metadata
metadata := {
    "policy_id": "0035",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0035_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0035_allowed if {
    input.user.active
    input.resource.public
}
policy_0035_approved if {
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
