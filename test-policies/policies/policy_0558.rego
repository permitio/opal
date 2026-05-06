package access.authentication.action.allow.core.policy_0558

# Auto-generated policy 558
# Package: access.authentication.action.allow.core

# Metadata
metadata := {
    "policy_id": "0558",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0558_allowed if {
    input.user.active
    input.resource.public
}
policy_0558_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0558_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0558_allowed if {
    data.policies.access.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
