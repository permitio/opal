package compliance.enforcement.user.validate.data.policy_0099

# Auto-generated policy 99
# Package: compliance.enforcement.user.validate.data

# Metadata
metadata := {
    "policy_id": "0099",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0099_allowed = false
policy_0099_allowed if {
    input.user.active
    input.resource.public
}
policy_0099_allowed if {
    data.policies.compliance.enabled
}
policy_0099_denied if {
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
