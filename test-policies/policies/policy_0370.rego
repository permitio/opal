package governance.authentication.resource.allow.policy_0370

# Auto-generated policy 370
# Package: governance.authentication.resource.allow

# Metadata
metadata := {
    "policy_id": "0370",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0370_allowed = false
policy_0370_allowed if {
    input.user.role == "admin"
}
policy_0370_allowed if {
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
