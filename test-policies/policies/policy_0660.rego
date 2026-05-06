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
allowed_0660 {
    input.user.active
    input.resource.public
}
allowed_0660 {
    input.user.role == "admin"
}
default allowed_0660 = false

# Utility function for user info
