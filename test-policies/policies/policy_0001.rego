package compliance.enforcement.context.verify.policy_0001

# Auto-generated policy 1
# Package: compliance.enforcement.context.verify

# Metadata
metadata := {
    "policy_id": "0001",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0001_allowed = false
policy_0001_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0001_allowed if {
    data.policies.compliance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
