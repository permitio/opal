package governance.authorization.policy.validate.helpers.policy_0281

# Auto-generated policy 281
# Package: governance.authorization.policy.validate.helpers

# Metadata
metadata := {
    "policy_id": "0281",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0281_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0281_allowed if {
    input.user.active
    input.resource.public
}
default policy_0281_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
