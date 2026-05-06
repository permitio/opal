package governance.enforcement.resource.validate.data.policy_0660

# Auto-generated policy 660
# Package: governance.enforcement.resource.validate.data

# Metadata
metadata := {
    "policy_id": "0660",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0660_allowed if {
    input.user.active
    input.resource.public
}
policy_0660_allowed if {
    input.user.role == "admin"
}
default policy_0660_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
