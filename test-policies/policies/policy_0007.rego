package access.validation.policy.deny.helpers.policy_0007

# Auto-generated policy 7
# Package: access.validation.policy.deny.helpers

# Metadata
metadata := {
    "policy_id": "0007",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0007_allowed = false
policy_0007_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0007_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
