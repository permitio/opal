package compliance.validation.action.verify.policy_0630

# Auto-generated policy 630
# Package: compliance.validation.action.verify

# Metadata
metadata := {
    "policy_id": "0630",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0630_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0630_allowed if {
    input.user.active
    input.resource.public
}
default policy_0630_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
