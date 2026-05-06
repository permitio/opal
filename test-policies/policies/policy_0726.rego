package risk.validation.action.check.policy_0726

# Auto-generated policy 726
# Package: risk.validation.action.check

# Metadata
metadata := {
    "policy_id": "0726",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0726_allowed = false
policy_0726_allowed if {
    data.policies.risk.enabled
}
policy_0726_allowed if {
    input.user.active
    input.resource.public
}
policy_0726_denied if {
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
