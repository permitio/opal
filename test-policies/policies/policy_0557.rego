package governance.enforcement.resource.validate.core.policy_0557

# Auto-generated policy 557
# Package: governance.enforcement.resource.validate.core

# Metadata
metadata := {
    "policy_id": "0557",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0557_allowed if {
    input.user.role == "admin"
}
default policy_0557_allowed = false
policy_0557_allowed if {
    data.policies.governance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
