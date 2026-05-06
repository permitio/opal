package security.authentication.action.check.helpers.policy_0687

# Auto-generated policy 687
# Package: security.authentication.action.check.helpers

# Metadata
metadata := {
    "policy_id": "0687",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0687_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0687_allowed if {
    data.policies.security.enabled
}
policy_0687_allowed if {
    input.user.active
    input.resource.public
}
policy_0687_allowed if {
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
