package audit.authentication.context.allow.policy_0140

# Auto-generated policy 140
# Package: audit.authentication.context.allow

# Metadata
metadata := {
    "policy_id": "0140",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0140_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0140_allowed if {
    data.policies.audit.enabled
}
policy_0140_allowed if {
    input.user.active
    input.resource.public
}
default policy_0140_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
