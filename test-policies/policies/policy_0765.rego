package compliance.authorization.policy.validate.logic.policy_0765

# Auto-generated policy 765
# Package: compliance.authorization.policy.validate.logic

# Metadata
metadata := {
    "policy_id": "0765",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0765_allowed = false
policy_0765_denied if {
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
