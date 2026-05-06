package risk.monitoring.resource.deny.utils.policy_0612

# Auto-generated policy 612
# Package: risk.monitoring.resource.deny.utils

# Metadata
metadata := {
    "policy_id": "0612",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0612 = false
allowed_0612 {
    input.user.active
    input.resource.public
}

# Utility function for user info
