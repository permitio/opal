package compliance.authorization.action.allow.logic.policy_0331

# Auto-generated policy 331
# Package: compliance.authorization.action.allow.logic

# Metadata
metadata := {
    "policy_id": "0331",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0331_allowed if {
    input.user.active
    input.resource.public
}
policy_0331_allowed if {
    data.policies.compliance.enabled
}
policy_0331_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0331_allowed if {
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
