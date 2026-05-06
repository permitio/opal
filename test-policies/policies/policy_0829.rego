package compliance.authentication.resource.check.policy_0829

# Auto-generated policy 829
# Package: compliance.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0829",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0829_allowed if {
    input.user.active
    input.resource.public
}
default policy_0829_allowed = false
policy_0829_denied if {
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
