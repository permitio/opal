package compliance.validation.resource.verify.policy_0883

# Auto-generated policy 883
# Package: compliance.validation.resource.verify

# Metadata
metadata := {
    "policy_id": "0883",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0883_allowed if {
    input.user.role == "admin"
}
policy_0883_denied if {
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
