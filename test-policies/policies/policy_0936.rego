package compliance.authorization.policy.check.logic.policy_0936

# Auto-generated policy 936
# Package: compliance.authorization.policy.check.logic

# Metadata
metadata := {
    "policy_id": "0936",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0936_allowed if {
    input.user.active
    input.resource.public
}
policy_0936_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0936_allowed if {
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
