package compliance.authorization.user.check.policy_0917

# Auto-generated policy 917
# Package: compliance.authorization.user.check

# Metadata
metadata := {
    "policy_id": "0917",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0917_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0917_allowed if {
    data.policies.compliance.enabled
}
policy_0917_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
