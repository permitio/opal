package governance.authentication.user.check.policy_0240

# Auto-generated policy 240
# Package: governance.authentication.user.check

# Metadata
metadata := {
    "policy_id": "0240",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0240_allowed if {
    input.user.active
    input.resource.public
}
policy_0240_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0240_allowed if {
    data.policies.governance.enabled
}
policy_0240_allowed if {
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
