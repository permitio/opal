package compliance.authentication.resource.verify.data.policy_0502

# Auto-generated policy 502
# Package: compliance.authentication.resource.verify.data

# Metadata
metadata := {
    "policy_id": "0502",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0502_allowed if {
    input.user.active
    input.resource.public
}
policy_0502_allowed if {
    input.user.role == "admin"
}
default policy_0502_allowed = false
policy_0502_allowed if {
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
