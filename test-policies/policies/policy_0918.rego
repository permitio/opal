package access.validation.policy.check.policy_0918

# Auto-generated policy 918
# Package: access.validation.policy.check

# Metadata
metadata := {
    "policy_id": "0918",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0918_allowed if {
    input.user.active
    input.resource.public
}
policy_0918_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0918_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0918_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
