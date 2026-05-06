package compliance.authentication.resource.validate.policy_0223

# Auto-generated policy 223
# Package: compliance.authentication.resource.validate

# Metadata
metadata := {
    "policy_id": "0223",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0223_allowed if {
    data.policies.compliance.enabled
}
policy_0223_denied if {
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
