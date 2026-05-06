package audit.monitoring.context.verify.policy_0888

# Auto-generated policy 888
# Package: audit.monitoring.context.verify

# Metadata
metadata := {
    "policy_id": "0888",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0888_allowed = false
policy_0888_allowed if {
    input.user.active
    input.resource.public
}
policy_0888_denied if {
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
