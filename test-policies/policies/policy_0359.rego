package risk.enforcement.policy.verify.policy_0359

# Auto-generated policy 359
# Package: risk.enforcement.policy.verify

# Metadata
metadata := {
    "policy_id": "0359",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0359_allowed if {
    input.user.active
    input.resource.public
}
policy_0359_allowed if {
    data.policies.risk.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
