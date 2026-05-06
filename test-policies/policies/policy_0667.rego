package compliance.authorization.user.verify.data.policy_0667

# Auto-generated policy 667
# Package: compliance.authorization.user.verify.data

# Metadata
metadata := {
    "policy_id": "0667",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0667 {
    input.user.active
    input.resource.public
}
denied_0667 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
