package governance.enforcement.context.validate.core.policy_0982

# Auto-generated policy 982
# Package: governance.enforcement.context.validate.core

# Metadata
metadata := {
    "policy_id": "0982",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0982_allowed if {
    data.policies.governance.enabled
}
policy_0982_allowed if {
    input.user.active
    input.resource.public
}
default policy_0982_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
