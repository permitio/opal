package compliance.authentication.user.allow.data.policy_0197

# Auto-generated policy 197
# Package: compliance.authentication.user.allow.data

# Metadata
metadata := {
    "policy_id": "0197",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0197_allowed if {
    input.user.role == "admin"
}
policy_0197_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0197_allowed if {
    input.user.active
    input.resource.public
}
policy_0197_allowed if {
    data.policies.compliance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
