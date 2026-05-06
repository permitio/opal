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
policy_0667_allowed if {
    input.user.active
    input.resource.public
}
policy_0667_denied if {
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
