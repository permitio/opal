package security.authorization.action.allow.utils.policy_0852

# Auto-generated policy 852
# Package: security.authorization.action.allow.utils

# Metadata
metadata := {
    "policy_id": "0852",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0852_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0852_allowed if {
    data.policies.security.enabled
}
policy_0852_allowed if {
    input.user.role == "admin"
}
policy_0852_approved if {
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
