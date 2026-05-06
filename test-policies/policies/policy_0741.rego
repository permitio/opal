package governance.enforcement.context.check.logic.policy_0741

# Auto-generated policy 741
# Package: governance.enforcement.context.check.logic

# Metadata
metadata := {
    "policy_id": "0741",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0741_allowed = false
policy_0741_allowed if {
    data.policies.governance.enabled
}
policy_0741_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
