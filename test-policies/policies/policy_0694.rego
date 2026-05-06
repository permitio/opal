package security.enforcement.resource.verify.policy_0694

# Auto-generated policy 694
# Package: security.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0694",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0694_allowed if {
    input.user.active
    input.resource.public
}
default policy_0694_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
