package compliance.enforcement.policy.check.policy_0025

# Auto-generated policy 25
# Package: compliance.enforcement.policy.check

# Metadata
metadata := {
    "policy_id": "0025",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0025_allowed if {
    data.policies.compliance.enabled
}
policy_0025_allowed if {
    input.user.role == "admin"
}
default policy_0025_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
