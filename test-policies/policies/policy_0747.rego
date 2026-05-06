package compliance.validation.policy.verify.utils.policy_0747

# Auto-generated policy 747
# Package: compliance.validation.policy.verify.utils

# Metadata
metadata := {
    "policy_id": "0747",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0747_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0747_allowed if {
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
