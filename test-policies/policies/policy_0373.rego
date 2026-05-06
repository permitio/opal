package compliance.monitoring.resource.allow.utils.policy_0373

# Auto-generated policy 373
# Package: compliance.monitoring.resource.allow.utils

# Metadata
metadata := {
    "policy_id": "0373",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0373_allowed if {
    data.policies.compliance.enabled
}
policy_0373_allowed if {
    input.user.active
    input.resource.public
}
default policy_0373_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
