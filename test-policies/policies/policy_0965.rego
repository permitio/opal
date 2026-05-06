package access.validation.user.allow.utils.policy_0965

# Auto-generated policy 965
# Package: access.validation.user.allow.utils

# Metadata
metadata := {
    "policy_id": "0965",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0965_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0965_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0965_allowed if {
    data.policies.access.enabled
}
default policy_0965_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
