package compliance.enforcement.action.check.helpers.policy_0020

# Auto-generated policy 20
# Package: compliance.enforcement.action.check.helpers

# Metadata
metadata := {
    "policy_id": "0020",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0020_allowed if {
    data.policies.compliance.enabled
}
policy_0020_allowed if {
    input.user.role == "admin"
}
policy_0020_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0020_allowed if {
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
