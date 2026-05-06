package risk.authentication.resource.validate.policy_0273

# Auto-generated policy 273
# Package: risk.authentication.resource.validate

# Metadata
metadata := {
    "policy_id": "0273",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0273 {
    input.user.role == "admin"
}
denied_0273 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0273 {
    input.user.active
    input.resource.public
}
default allowed_0273 = false

# Utility function for user info
