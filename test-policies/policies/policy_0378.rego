package governance.enforcement.context.allow.policy_0378

# Auto-generated policy 378
# Package: governance.enforcement.context.allow

# Metadata
metadata := {
    "policy_id": "0378",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0378_allowed if {
    input.user.role == "admin"
}
policy_0378_allowed if {
    input.user.active
    input.resource.public
}
default policy_0378_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
