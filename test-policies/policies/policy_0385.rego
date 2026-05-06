package governance.enforcement.policy.deny.policy_0385

# Auto-generated policy 385
# Package: governance.enforcement.policy.deny

# Metadata
metadata := {
    "policy_id": "0385",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0385_allowed if {
    input.user.role == "admin"
}
default policy_0385_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
