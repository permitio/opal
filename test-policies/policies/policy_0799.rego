package security.validation.action.allow.helpers.policy_0799

# Auto-generated policy 799
# Package: security.validation.action.allow.helpers

# Metadata
metadata := {
    "policy_id": "0799",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0799_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0799_allowed if {
    data.policies.security.enabled
}
policy_0799_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0799_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
