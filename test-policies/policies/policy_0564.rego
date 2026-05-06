package security.enforcement.resource.verify.policy_0564

# Auto-generated policy 564
# Package: security.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0564",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0564_allowed if {
    input.user.role == "admin"
}
policy_0564_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0564_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
