package audit.authentication.action.verify.policy_0487

# Auto-generated policy 487
# Package: audit.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0487",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0487_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0487_allowed if {
    input.user.active
    input.resource.public
}
policy_0487_allowed if {
    data.policies.audit.enabled
}
policy_0487_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
