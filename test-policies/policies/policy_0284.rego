package audit.enforcement.resource.allow.policy_0284

# Auto-generated policy 284
# Package: audit.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0284",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0284_allowed if {
    data.policies.audit.enabled
}
policy_0284_allowed if {
    input.user.active
    input.resource.public
}
policy_0284_allowed if {
    input.user.role == "admin"
}
policy_0284_denied if {
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
