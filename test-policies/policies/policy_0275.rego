package governance.validation.action.verify.helpers.policy_0275

# Auto-generated policy 275
# Package: governance.validation.action.verify.helpers

# Metadata
metadata := {
    "policy_id": "0275",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0275_allowed = false
policy_0275_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0275_allowed if {
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
