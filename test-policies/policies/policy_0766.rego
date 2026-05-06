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
default allowed_0766 = false
allowed_0766 {
    input.user.active
    input.resource.public
}
denied_0766 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
