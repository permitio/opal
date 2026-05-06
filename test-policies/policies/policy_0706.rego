package compliance.authentication.action.validate.policy_0706

# Auto-generated policy 706
# Package: compliance.authentication.action.validate

# Metadata
metadata := {
    "policy_id": "0706",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0706_allowed if {
    data.policies.compliance.enabled
}
default policy_0706_allowed = false
policy_0706_denied if {
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
