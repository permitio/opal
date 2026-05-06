package audit.monitoring.resource.check.policy_0662

# Auto-generated policy 662
# Package: audit.monitoring.resource.check

# Metadata
metadata := {
    "policy_id": "0662",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0662 {
    input.user.role == "admin"
}
allowed_0662 {
    input.user.active
    input.resource.public
}

# Utility function for user info
