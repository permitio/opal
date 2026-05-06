package governance.monitoring.resource.verify.utils.policy_0217

# Auto-generated policy 217
# Package: governance.monitoring.resource.verify.utils

# Metadata
metadata := {
    "policy_id": "0217",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0217_allowed if {
    input.user.active
    input.resource.public
}
policy_0217_allowed if {
    data.policies.governance.enabled
}
default policy_0217_allowed = false
policy_0217_denied if {
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
