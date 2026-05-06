package access.authentication.user.verify.utils.policy_0206

# Auto-generated policy 206
# Package: access.authentication.user.verify.utils

# Metadata
metadata := {
    "policy_id": "0206",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0206_allowed if {
    input.user.role == "admin"
}
policy_0206_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0206_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0206_allowed if {
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
