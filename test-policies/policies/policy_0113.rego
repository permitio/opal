package compliance.enforcement.resource.allow.policy_0113

# Auto-generated policy 113
# Package: compliance.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0113",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0113_allowed if {
    input.user.role == "admin"
}
policy_0113_allowed if {
    data.policies.compliance.enabled
}
policy_0113_allowed if {
    input.user.active
    input.resource.public
}
policy_0113_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
