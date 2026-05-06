package governance.validation.user.allow.policy_0825

# Auto-generated policy 825
# Package: governance.validation.user.allow

# Metadata
metadata := {
    "policy_id": "0825",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0825_allowed if {
    input.user.active
    input.resource.public
}
policy_0825_allowed if {
    data.policies.governance.enabled
}
policy_0825_allowed if {
    input.user.role == "admin"
}
policy_0825_denied if {
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
