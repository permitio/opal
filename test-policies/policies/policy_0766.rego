package audit.validation.resource.deny.policy_0766

# Auto-generated policy 766
# Package: audit.validation.resource.deny

# Metadata
metadata := {
    "policy_id": "0766",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0766_allowed = false
policy_0766_allowed if {
    input.user.active
    input.resource.public
}
policy_0766_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
