package governance.enforcement.context.verify.policy_0848

# Auto-generated policy 848
# Package: governance.enforcement.context.verify

# Metadata
metadata := {
    "policy_id": "0848",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0848_allowed if {
    data.policies.governance.enabled
}
default policy_0848_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
