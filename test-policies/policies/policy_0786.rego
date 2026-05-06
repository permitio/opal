package risk.authentication.context.verify.helpers.policy_0786

# Auto-generated policy 786
# Package: risk.authentication.context.verify.helpers

# Metadata
metadata := {
    "policy_id": "0786",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0786_allowed if {
    input.user.role == "admin"
}
default policy_0786_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
