package compliance.authentication.action.check.policy_0646

# Auto-generated policy 646
# Package: compliance.authentication.action.check

# Metadata
metadata := {
    "policy_id": "0646",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0646_allowed if {
    input.user.active
    input.resource.public
}
default policy_0646_allowed = false
policy_0646_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0646_allowed if {
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
