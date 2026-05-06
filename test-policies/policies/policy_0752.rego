package governance.enforcement.resource.check.helpers.policy_0752

# Auto-generated policy 752
# Package: governance.enforcement.resource.check.helpers

# Metadata
metadata := {
    "policy_id": "0752",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0752_allowed if {
    data.policies.governance.enabled
}
default policy_0752_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
