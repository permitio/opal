package compliance.monitoring.resource.allow.utils.policy_0339

# Auto-generated policy 339
# Package: compliance.monitoring.resource.allow.utils

# Metadata
metadata := {
    "policy_id": "0339",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0339_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0339_allowed if {
    input.user.active
    input.resource.public
}
default policy_0339_allowed = false
policy_0339_approved if {
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
