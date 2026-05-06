package compliance.enforcement.policy.deny.core.policy_0250

# Auto-generated policy 250
# Package: compliance.enforcement.policy.deny.core

# Metadata
metadata := {
    "policy_id": "0250",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0250_allowed if {
    data.policies.compliance.enabled
}
policy_0250_allowed if {
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
